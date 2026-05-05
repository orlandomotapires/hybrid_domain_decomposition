from libs.log import log
from libs.utils import *
from libs.permutation import *
from libs.multilevel_scheme.coarsening import *
from libs.multilevel_scheme.partitioning import *
from libs.multilevel_scheme.partitioning_backends import get_qpu_dense_clique_capacity, get_qlm_qpu_api_summary, uses_dense_balance_qubo
from libs.multilevel_scheme.uncoarsening import uncoarsen_and_refine
import numpy as np

def _set_edge_weight_attr(G, attr_name: str):
    if attr_name == 'weight':
        return
    for _, _, data in G.edges(data=True):
        data[attr_name] = data.get('weight', 1.0)

def _set_node_vweight_diag(G, diag: np.ndarray, dof_per_node: int):
    d = int(dof_per_node)
    node_diag = np.add.reduceat(np.asarray(diag).ravel(), np.arange(0, len(diag), d))
    for i in G.nodes():
        G.nodes[i]['vweight'] = float(node_diag[int(i)])

def decompose_matrices_m_k(matrix_m, matrix_k, general_parameters, coarsening_parameters, partitioning_parameters, uncoarsening_parameters):
    """Run the full pipeline: matrix-to-graph, coarsen, partition, uncoarsen, then permute K and M."""

    if matrix_k.shape != matrix_m.shape:
        raise ValueError(f"K and M must have the same shape. Got K={matrix_k.shape}, M={matrix_m.shape}")

    # General parameters
    dof_per_node = int(general_parameters.get("dof_per_node"))
    seed = int(general_parameters.get("seed"))

    # Coarsening parameters
    coarsen_limit = int(coarsening_parameters.get("coarsen_limit"))
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

    # Uncoarsening parameters
    refine_objective = str(uncoarsening_parameters.get("refine_objective"))
    refine_balance_lambda = float(uncoarsening_parameters.get("refine_balance_lambda"))
    refine_max_passes_per_level = int(uncoarsening_parameters.get("refine_max_passes_per_level"))
    refine_max_moves_per_pass = uncoarsening_parameters.get("refine_max_moves_per_pass")
    n_total = matrix_k.shape[0]

    if dof_per_node <= 0:
        raise ValueError("DOF_PER_NODE must be a positive integer")

    if n_total % dof_per_node != 0:
        raise ValueError(
            f"Global size {n_total} not divisible by DOF_PER_NODE={dof_per_node}. "
            "Adjust DOF_PER_NODE to match the assembled matrices."
        )

    # Build graphs from matrices
    diag_K = matrix_k.diagonal()
    diag_M = matrix_m.diagonal()
    log("INFO", "Converting matrices to graphs")
    G_K = matrix_to_graph(matrix_k, dof_per_node=dof_per_node)
    G_M = matrix_to_graph(matrix_m, dof_per_node=dof_per_node)

    _set_node_vweight_diag(G_K, diag_K, dof_per_node)
    _set_node_vweight_diag(G_M, diag_M, dof_per_node)
    _set_edge_weight_attr(G_K, weight)
    _set_edge_weight_attr(G_M, weight)

    # Common rule of thumb: ~1.5 * (total_node_weight / k_target)
    if max_node_weight is None and k_target is not None and int(k_target) > 1:
        total_vw = sum(float(G_K.nodes[u].get('vweight', 1.0)) for u in G_K.nodes())
        max_node_weight = 1.5 * (total_vw / float(int(k_target)))

    log("INFO", f"Graph G_K with {G_K.number_of_nodes()} nodes and {G_K.number_of_edges()} edges created from K matrix")

    log("INFO", "Coarsening Heavy Edge Matching")
    graphs, maps = coarsen_chain(
        G_K,
        trial_seed=seed,
        coarsen_limit=coarsen_limit,
        max_levels=max_levels,
        weight=weight,
        strategy=strategy,
        coarsen_ratio=coarsen_ratio,
        max_node_weight=max_node_weight
    )
    log("VERBOSE", f"Coarse graph has {graphs[-1].number_of_nodes()} nodes and {graphs[-1].number_of_edges()} edges with {len(graphs)} levels")

    Gc = graphs[-1]
    # Small inputs can stop before any contraction map is produced.
    if len(maps) < 1:
        log("VERBOSE", "Warning: No coarsening occurred (graph already small enough or the next level would fall below coarsen_limit)")

    part_k_coarse = 0
    if partitioning_strategy == 'metis_partitioning':
        log("INFO", "Multilevel Partitioning Scheme using METIS")
        part_k_coarse = partition_graph_metis(Gc, nparts=k_target)

    elif partitioning_strategy == 'quantum_annealing':

        balance_lambda = float(strategy_partitioning_parameters.get("qubo_balance_lambda"))
        num_reads = int(strategy_partitioning_parameters.get("num_reads"))
        num_starts = int(strategy_partitioning_parameters.get("num_starts"))
        balance_violation_lambda = float(strategy_partitioning_parameters.get("balance_violation_lambda"))
        simulated = bool(strategy_partitioning_parameters.get("simulated", True))
        qpu_solver_name = strategy_partitioning_parameters.get("qpu_solver_name")
        qpu_region = strategy_partitioning_parameters.get("qpu_region")
        qpu_problem_label = strategy_partitioning_parameters.get("qpu_problem_label")
        dense_qpu_too_large = False

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
                dense_qpu_too_large = coarse_size > clique_capacity
                if dense_qpu_too_large:
                    log(
                        "WARNING",
                        f"Coarse dense QUBO size {coarse_size} exceeds solver capacity {clique_capacity}; Leap submission will be skipped",
                    )

            if not dense_qpu_too_large:
                bipartitions_per_start = max(1, int(k_target) - 1)
                expected_submissions = max(1, num_starts) * bipartitions_per_start
                expected_reads = expected_submissions * max(1, num_reads)
                log(
                    "VERBOSE",
                    "Expected QPU problem submissions: "
                    f"{expected_submissions} (num_starts={num_starts} * bipartitions_per_start={bipartitions_per_start}); "
                    f"num_reads per submission: {num_reads}; total QPU reads: {expected_reads}",
                )
                if expected_submissions > 50:
                    log(
                        "WARNING",
                        "This run will submit many QPU problems. If Leap resets the connection, "
                        "reduce num_starts/num_reads or set simulated=True for a local run.",
                    )

        part_k_coarse = recursive_kway_anneal(
            Gc,
            k=k_target,
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
        adam_learning_rate = None if adam_learning_rate_raw is None else float(adam_learning_rate_raw)

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
            bipartitions_per_start = max(1, int(k_target) - 1)
            expected_remote_jobs = max(1, num_starts) * bipartitions_per_start * (max(1, num_steps) + 1)
            log(
                "VERBOSE",
                "Estimated QLM job count: "
                f"{expected_remote_jobs} (num_starts={num_starts} * bipartitions_per_start={bipartitions_per_start} * (num_steps + final_sample={max(1, num_steps) + 1}))",
            )
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
            k=k_target,
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
        )

    log("VERBOSE", f"Partitioning on coarse graph produced {len(set(part_k_coarse.values()))} parts")

    log("INFO", "Uncoarsening Kernighan-Lin")
    part_k = uncoarsen_and_refine(
        graphs,
        maps,
        part_k_coarse,
        k=k_target,
        balance_tolerance=balance_tolerance,
        weight_attr=weight,
        node_weight_attr='vweight',
        refine_objective=refine_objective,
        refine_balance_lambda=refine_balance_lambda,
        max_passes_per_level=refine_max_passes_per_level,
        max_moves_per_pass=refine_max_moves_per_pass,
        seed=seed,
    )

    log("INFO", "Permuting matrices")
    # Permute matrices
    permute_result = permute_matrices(
        matrix_k=matrix_k,
        matrix_m=matrix_m,
        partition=part_k,
        dof_per_node=dof_per_node,
    )

    permutation = permute_result['permutation']
    matrix_k_permuted = permute_result['matrix_k_permuted']
    matrix_m_permuted = permute_result['matrix_m_permuted']

    return matrix_m_permuted, matrix_k_permuted, permutation