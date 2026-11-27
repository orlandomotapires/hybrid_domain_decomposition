from libs.runtime import events
from libs.runtime.log import log
from libs.runtime.utils import matrix_to_graph
from libs.permutation import permute_matrix
from libs.graph_prep import default_max_node_weight, set_edge_weight_attr, set_node_vweight_diag
from libs.multilevel_scheme.coarsening.coarsening import coarsen_chain
from libs.multilevel_scheme.partitioning.capacity import local_capacity_error, qpu_workload
from libs.multilevel_scheme.partitioning.partitioning import (
    partition_graph_metis,
    recursive_kway_anneal,
    recursive_kway_qaoa,
)
from libs.multilevel_scheme.partitioning.qa import (
    get_qpu_dense_clique_capacity,
    get_qlm_qpu_api_summary,
    uses_dense_balance_qubo,
)
from libs.multilevel_scheme.uncoarsening.uncoarsening import uncoarsen_and_refine
import numpy as np
import time

from libs.multilevel_scheme.partitioning.utils.metrics import balance_violation, cut_value


def _clamp_partition_count(requested_k: int, available_nodes: int) -> int:
    if available_nodes <= 0:
        raise ValueError("Cannot partition an empty coarse graph")
    return max(1, min(int(requested_k), int(available_nodes)))

# Kept under their old names for callers of this module.
_set_edge_weight_attr = set_edge_weight_attr
_set_node_vweight_diag = set_node_vweight_diag


def decompose_matrix(matrix, general_parameters, coarsening_parameters, partitioning_parameters, uncoarsening_parameters):
    """Run the full pipeline on one square sparse matrix: matrix-to-graph, coarsen, partition,
    uncoarsen, then permute it. Returns (matrix_permuted, permutation, artifacts)."""

    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"The input matrix must be square. Got shape {matrix.shape}")

    # General parameters
    dof_per_node = int(general_parameters.get("dof_per_node"))
    seed = int(general_parameters.get("seed"))

    # Coarsening parameters
    coarsen_inferior_limit = int(coarsening_parameters.get("coarsen_inferior_limit"))
    coarsen_superior_limit = coarsening_parameters.get("coarsen_superior_limit")
    if coarsen_superior_limit is not None:
        coarsen_superior_limit = int(coarsen_superior_limit)
    max_levels = int(coarsening_parameters.get("max_levels"))
    weight = str(coarsening_parameters.get("weight"))
    strategy = str(coarsening_parameters.get("strategy"))
    coarsen_ratio = float(coarsening_parameters.get("coarsen_ratio"))
    max_node_weight = coarsening_parameters.get("max_node_weight")
    if max_node_weight is not None:
        max_node_weight = float(max_node_weight)

    # Partitioning parameters
    partitioning_strategy = str(partitioning_parameters.get("partitioning_strategy")).strip().lower()
    common_partitioning_parameters = partitioning_parameters.get("common")
    strategies_partitioning_parameters = partitioning_parameters.get("strategies")
    strategy_partitioning_parameters = strategies_partitioning_parameters.get(partitioning_strategy)

    k_target = int(common_partitioning_parameters.get("k_target"))
    balance_tolerance = float(common_partitioning_parameters.get("balance_tolerance"))
    if 0.0 < balance_tolerance <= 1.0:
        log(
            "WARNING",
            f"balance_tolerance={balance_tolerance:g} means ±{balance_tolerance:g}%. Parameter files written "
            "before November 2026 used values up to 1.0 as fractions (0.1 = 10%); "
            f"if this file is one of them, use {balance_tolerance * 100:g} instead.",
        )

    # Uncoarsening parameters
    refine_objective = str(uncoarsening_parameters.get("refine_objective"))
    refine_balance_lambda = float(uncoarsening_parameters.get("refine_balance_lambda"))
    refine_max_passes_per_level = int(uncoarsening_parameters.get("refine_max_passes_per_level"))
    refine_max_moves_per_pass = uncoarsening_parameters.get("refine_max_moves_per_pass")
    n_total = matrix.shape[0]

    if dof_per_node <= 0:
        raise ValueError("DOF_PER_NODE must be a positive integer")

    if n_total % dof_per_node != 0:
        raise ValueError(
            f"Matrix size {n_total} not divisible by the block size DOF_PER_NODE={dof_per_node}. "
            "Use a block size that divides the number of rows (1 always works)."
        )

    # Build the graph from the matrix
    stage_durations_sec: dict[str, float] = {}
    t_stage = time.perf_counter()
    t_total = t_stage

    def _close_stage(name: str) -> None:
        nonlocal t_stage
        now = time.perf_counter()
        stage_durations_sec[name] = round(now - t_stage, 6)
        t_stage = now

    events.stage("initialization")
    log("INFO", "Converting matrix to graph")
    G = matrix_to_graph(matrix, dof_per_node=dof_per_node)

    if not _set_node_vweight_diag(G, matrix.diagonal(), dof_per_node):
        log("VERBOSE", "Matrix diagonal has zero blocks; using uniform node weights")
    _set_edge_weight_attr(G, weight)

    if max_node_weight is None:
        max_node_weight = default_max_node_weight(G, k_target)  # 1.5 x (total node weight / k)

    log("INFO", f"Graph G with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges created from the matrix")

    _close_stage("graph_build")

    events.stage("coarsening")
    log("INFO", "Coarsening Heavy Edge Matching")
    graphs, maps = coarsen_chain(
        G,
        trial_seed=seed,
        coarsen_inferior_limit=coarsen_inferior_limit,
        coarsen_superior_limit=coarsen_superior_limit,
        max_levels=max_levels,
        weight=weight,
        strategy=strategy,
        coarsen_ratio=coarsen_ratio,
        max_node_weight=max_node_weight
    )
    log("VERBOSE", f"Coarse graph has {graphs[-1].number_of_nodes()} nodes and {graphs[-1].number_of_edges()} edges with {len(graphs)} levels")

    _close_stage("coarsening")

    Gc = graphs[-1]
    # Fail fast with a clear reason instead of running a local quantum emulator out of memory.
    capacity_error = local_capacity_error(partitioning_parameters, Gc.number_of_nodes())
    if capacity_error:
        raise ValueError(capacity_error)
    effective_k_target = _clamp_partition_count(k_target, Gc.number_of_nodes())
    if effective_k_target != k_target:
        log(
            "WARNING",
            f"Requested k_target={k_target} exceeds the available coarse nodes {Gc.number_of_nodes()}; clamping to {effective_k_target}",
        )

    # Small inputs can stop before any contraction map is produced.
    if len(maps) < 1:
        log(
            "WARNING",
            "No coarsening occurred (graph already satisfied the requested range, or the next level would fall below the inferior coarsening limit)",
        )
    elif coarsen_superior_limit is not None and Gc.number_of_nodes() > coarsen_superior_limit:
        log(
            "WARNING",
            f"Coarsening stopped at {Gc.number_of_nodes()} nodes, above coarsen_superior_limit={coarsen_superior_limit}",
        )

    events.stage("partitioning")
    part_k_coarse = 0
    if partitioning_strategy == 'metis_partitioning':
        log("INFO", "Multilevel Partitioning Scheme using METIS")
        part_k_coarse = partition_graph_metis(Gc, nparts=effective_k_target, balance_tolerance=balance_tolerance)

    elif partitioning_strategy == 'quantum_annealing':

        balance_lambda = float(strategy_partitioning_parameters.get("qubo_balance_lambda"))
        num_reads = int(strategy_partitioning_parameters.get("num_reads"))
        num_starts = int(strategy_partitioning_parameters.get("num_starts"))
        balance_violation_lambda = float(strategy_partitioning_parameters.get("balance_violation_lambda"))
        simulated = bool(strategy_partitioning_parameters.get("simulated", True))
        qpu_solver_name = strategy_partitioning_parameters.get("qpu_solver_name")
        qpu_region = strategy_partitioning_parameters.get("qpu_region")
        qpu_problem_label = strategy_partitioning_parameters.get("qpu_problem_label")

        if simulated:
            log("INFO", "Running simulated quantum annealing for bipartitioning")
        else:
            qpu_target = qpu_solver_name or qpu_region or "default Leap configuration"
            log("INFO", f"Running quantum annealing for bipartitioning on {qpu_target}")
            log("VERBOSE", f"QPU problem label: {qpu_problem_label}")
            if uses_dense_balance_qubo(balance_lambda):
                solver_name, clique_capacity = get_qpu_dense_clique_capacity(qpu_solver_name, qpu_region)
                coarse_size = Gc.number_of_nodes()
                log("VERBOSE", f"Solver {solver_name} largest dense QUBO clique capacity: {clique_capacity}")
                log("VERBOSE", f"Current coarse dense QUBO size: {coarse_size}")
                if coarse_size > clique_capacity:
                    # Stop before any Leap submission: the dense QUBO cannot be embedded.
                    raise ValueError(
                        f"The coarse graph has {coarse_size} nodes, but solver {solver_name} can embed a dense "
                        f"QUBO of at most {clique_capacity}. Coarsen further (lower coarsen_superior_limit) "
                        "or set simulated=True. Nothing was submitted to Leap."
                    )

            bipartitions_per_start = max(1, int(effective_k_target) - 1)
            workload = qpu_workload("quantum_annealing", strategy_partitioning_parameters, effective_k_target)
            expected_submissions, expected_reads = workload["submissions"], workload["samples"]
            log(
                "VERBOSE",
                "Expected QPU problem submissions: "
                f"{expected_submissions} (num_starts={num_starts} * bipartitions_per_start={bipartitions_per_start}); "
                f"num_reads per submission: {num_reads}; total QPU reads: {expected_reads}",
            )
            if expected_submissions > 50:
                log(
                    "WARNING",
                    "This run will submit many QPU problems. Dropped connections are retried, but "
                    "reduce num_starts/num_reads or set simulated=True for a local run if Leap keeps failing.",
                )

        part_k_coarse = recursive_kway_anneal(
            Gc,
            k=effective_k_target,
            balance_lambda=balance_lambda,
            num_reads=num_reads,
            weight='vweight',
            balance_tolerance=balance_tolerance,
            seed=seed,
            num_starts=num_starts,
            balance_violation_lambda=balance_violation_lambda,
            simulated=simulated,
            qpu_solver_name=qpu_solver_name,
            qpu_region=qpu_region,
            qpu_problem_label=qpu_problem_label,
        )
    elif partitioning_strategy == 'quantum_approximation_optimizer':
        log("INFO", "Partitioning QAOA")

        # Parameters for QAOA
        balance_lambda = float(strategy_partitioning_parameters.get("qubo_balance_lambda"))
        num_starts = int(strategy_partitioning_parameters.get("num_starts"))
        balance_violation_lambda = float(strategy_partitioning_parameters.get("balance_violation_lambda"))
        circuit_depth = int(strategy_partitioning_parameters.get("circuit_depth"))
        num_steps = int(strategy_partitioning_parameters.get("num_steps"))
        adam_learning_rate_raw = strategy_partitioning_parameters.get("adam_learning_rate")
        num_shots = int(strategy_partitioning_parameters.get("num_shots"))
        simulated = bool(strategy_partitioning_parameters.get("simulated", True))
        qlm_qpu_name = strategy_partitioning_parameters.get("qlm_qpu_name")
        qlm_job_timeout_raw = strategy_partitioning_parameters.get("qlm_job_timeout_seconds")
        adam_learning_rate = None if adam_learning_rate_raw is None else float(adam_learning_rate_raw)
        qlm_job_timeout_seconds = None if qlm_job_timeout_raw is None else float(qlm_job_timeout_raw)

        if not simulated:
            log("INFO", f"Running QAOA on QLM backend {qlm_qpu_name or 'qat.qpus:QSolidQPU10'}")
            qlm_summary = get_qlm_qpu_api_summary(
                qlm_qpu_name=qlm_qpu_name,
            )
            if qlm_summary.get("inspection_error"):
                log("WARNING", f"QLM backend inspection failed: {qlm_summary['inspection_error']}")
            else:
                if "resolved_qpu_name" in qlm_summary:
                    log("VERBOSE", f"QLM backend resolved QPU name: {qlm_summary['resolved_qpu_name']}")
                if "service_type" in qlm_summary:
                    log("VERBOSE", f"QLM backend service type: {qlm_summary['service_type']}")
                if "reported_max_qubits" in qlm_summary:
                    log("VERBOSE", f"QLM backend reported max qubits: {qlm_summary['reported_max_qubits']}")
                if "specs_description" in qlm_summary:
                    log("VERBOSE", f"QLM backend specs description: {qlm_summary['specs_description']}")
                if "topology" in qlm_summary:
                    log("VERBOSE", f"QLM backend topology: {qlm_summary['topology']}")
            log("VERBOSE", f"Current coarse QAOA problem size: {Gc.number_of_nodes()}")
            bipartitions_per_start = max(1, int(effective_k_target) - 1)
            expected_remote_jobs = max(1, num_starts) * bipartitions_per_start * (max(1, num_steps) + 1)
            log(
                "VERBOSE",
                "Estimated QLM job count: "
                f"{expected_remote_jobs} (num_starts={num_starts} * bipartitions_per_start={bipartitions_per_start} * (num_steps + final_sample={max(1, num_steps) + 1}))",
            )
            if qlm_job_timeout_seconds is not None:
                log("VERBOSE", f"QLM job timeout: {qlm_job_timeout_seconds:.1f}s per submit/join step")
            if expected_remote_jobs > 100:
                log(
                    "WARNING",
                    "This QAOA run will create many remote QLM jobs. Reduce num_starts/num_steps, coarsen more aggressively, or use a local/emulated backend for pilot runs.",
                )
            if adam_learning_rate_raw is not None:
                log("VERBOSE", "adam_learning_rate is ignored on the QLM backend because the remote optimizer is COBYLA")
        else:
            log("INFO", "Running QAOA on local PennyLane backend")

        part_k_coarse = recursive_kway_qaoa(
            Gc,
            k=effective_k_target,
            balance_lambda=balance_lambda,
            weight='vweight',
            num_starts=num_starts,
            balance_violation_lambda=balance_violation_lambda,
            balance_tolerance=balance_tolerance,
            seed=seed,
            circuit_depth=circuit_depth,
            adam_learning_rate=adam_learning_rate,
            num_steps=num_steps,
            num_shots=num_shots,
            simulated=simulated,
            qlm_qpu_name=qlm_qpu_name,
            qlm_job_timeout_seconds=qlm_job_timeout_seconds,
        )

    log("VERBOSE", f"Partitioning on coarse graph produced {len(set(part_k_coarse.values()))} parts")

    _close_stage("partitioning")

    events.stage("uncoarsening")
    log("INFO", "Uncoarsening Kernighan-Lin")
    part_k = uncoarsen_and_refine(
        graphs,
        maps,
        part_k_coarse,
        k=effective_k_target,
        balance_tolerance=balance_tolerance,
        weight_attr=weight,
        node_weight_attr='vweight',
        refine_objective=refine_objective,
        refine_balance_lambda=refine_balance_lambda,
        max_passes_per_level=refine_max_passes_per_level,
        max_moves_per_pass=refine_max_moves_per_pass,
        seed=seed,
    )

    _close_stage("uncoarsening")

    events.stage("permutation")
    log("INFO", "Permuting matrix")
    permute_result = permute_matrix(
        matrix=matrix,
        partition=part_k,
        dof_per_node=dof_per_node,
    )

    _close_stage("permutation")
    total_sec = round(time.perf_counter() - t_total, 6)

    decomposition_metrics = compute_decomposition_metrics(
        G,
        Gc,
        part_k,
        part_k_coarse,
        k=effective_k_target,
        balance_tolerance=balance_tolerance,
        weight_attr=weight,
        levels=len(graphs),
    )
    decomposition_metrics["requested_k"] = int(k_target)
    decomposition_metrics["timing"] = {"total_sec": total_sec, "stage_durations_sec": stage_durations_sec}

    return permute_result['matrix_permuted'], permute_result['permutation'], {
        "decomposition_metrics": decomposition_metrics,
        "initial_graph": G,
        "coarse_graph": Gc,
        "coarsening_maps": list(maps),
        "coarse_partition": dict(part_k_coarse),
        "final_partition": dict(part_k),
    }

def compute_decomposition_metrics(G, Gc, part_k, part_k_coarse, *, k, balance_tolerance, weight_attr, levels) -> dict:
    """Quality numbers for a finished partition, used by run_metrics.json and the parameter tuner.

    ``imbalance`` is max part weight / ideal part weight - 1 (0 = perfectly balanced);
    ``edge_cut_fraction`` is the cut weight divided by the total edge weight of the fine graph.
    """
    k = int(k)
    total_edge_weight = sum(float(d.get(weight_attr, 1.0)) for _, _, d in G.edges(data=True))
    edge_cut = cut_value(G, part_k, edge_weight_attr=weight_attr)
    part_weights = np.zeros(max(k, 1), dtype=float)
    part_sizes = np.zeros(max(k, 1), dtype=int)
    for u in G.nodes():
        p = int(part_k.get(u, 0))
        if p < 0 or p >= len(part_weights):
            p = 0
        w = float(G.nodes[u].get("vweight", 1.0))
        part_weights[p] += w if np.isfinite(w) and w > 0 else 0.0
        part_sizes[p] += 1
    total_w = float(part_weights.sum())
    ideal = total_w / float(max(k, 1)) if total_w > 0 else 0.0
    imbalance = float(part_weights.max() / ideal - 1.0) if ideal > 0 else 0.0
    violation = balance_violation(G, part_k, k, balance_tolerance=balance_tolerance)
    interface_nodes = sum(
        1 for u in G.nodes() if any(part_k.get(v) != part_k.get(u) for v in G.neighbors(u))
    )
    return {
        "levels": int(levels),
        "fine_graph": {"nodes": int(G.number_of_nodes()), "edges": int(G.number_of_edges())},
        "coarse_graph": {"nodes": int(Gc.number_of_nodes()), "edges": int(Gc.number_of_edges())},
        "effective_k": k,
        "edge_cut": float(edge_cut),
        "edge_cut_fraction": float(edge_cut / total_edge_weight) if total_edge_weight > 0 else 0.0,
        "edge_cut_coarse": float(cut_value(Gc, part_k_coarse, edge_weight_attr=weight_attr)),
        "imbalance": imbalance,
        "balance_violation": float(violation),
        "balance_violation_fraction": float(violation / total_w) if total_w > 0 else 0.0,
        "part_sizes": [int(x) for x in part_sizes],
        "part_weights": [float(x) for x in part_weights],
        "interface_nodes": int(interface_nodes),
        "interface_fraction": float(interface_nodes / G.number_of_nodes()) if G.number_of_nodes() else 0.0,
    }
