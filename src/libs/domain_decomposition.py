from libs.utils import *
from libs.permutation import *
from libs.multilevel_scheme.coarsening import *
from libs.multilevel_scheme.partitioning import *
from libs.multilevel_scheme.uncoarsening import uncoarsen_and_refine, uncoarsening
from libs.multilevel_scheme.metis_partitioning import partition_graph_metis

import numpy as np

def decompose_matrices_m_k(matrix_m, matrix_k, 
               dof_per_node, 
               coarsen_limit=300, 
               max_levels=10, 
               weight='weight', 
               strategy='sorted',
               coarsen_ratio=0.85, 
               max_node_weight=None, 
               k_target=2, 
               balance_lambda=2.0, 
               num_reads=1000, 
               balance_tolerance=2.0,
               permuting_strategy: str = 'qa_partitioning',
               qa_num_starts: int = 1,
               qa_select_balance_lambda: float = 1.0e6,
               refine_objective: str = 'cut',
               refine_balance_lambda: float = 1.0,
               refine_method: str = 'greedy',
               refine_max_passes_per_level: int = 5,
               refine_max_moves_per_pass: int | None = None,
               validate_node_weights: bool = True,
               seed: int = 42):

    if matrix_k.shape != matrix_m.shape:
        raise ValueError(f"K and M must have the same shape. Got K={matrix_k.shape}, M={matrix_m.shape}")

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

    # Map the matrices into graphs (only K matrix is used for partitioning based on connectivity)
    def _build_graph_k(node_vweight: str):
        return matrix_to_graph(
            matrix_k,
            symmetrize='sum',
            drop_diagonal=True,
            abs_weights=True,
            node_vweight=node_vweight,
            diag=diag_K,
            dof_per_node=dof_per_node
        )

    G_K = _build_graph_k('diag')
    G_M = matrix_to_graph(
        matrix_m,
        symmetrize='sum',
        drop_diagonal=True,
        abs_weights=True,
        node_vweight='diag',
        diag=diag_M,
        dof_per_node=dof_per_node
    )

    # Validate node weights (vweight) for balance; fall back to degree-based weights if invalid.
    if validate_node_weights:
        vweights = []
        bad = False
        for u in G_K.nodes():
            vw = G_K.nodes[u].get('vweight', None)
            if vw is None:
                bad = True
                break
            try:
                f = float(vw)
            except Exception:
                bad = True
                break
            if not np.isfinite(f) or f < 0:
                bad = True
                break
            vweights.append(f)

        if bad or (len(vweights) > 0 and float(np.max(vweights)) == 0.0):
            print("Warning: invalid/degenerate node vweight detected; falling back to degree-based node weights.")
            G_K = _build_graph_k('degree')

    # If user didn't provide a max_node_weight, compute a simple METIS-like heuristic.
    # Common rule of thumb: ~1.5 * (total_node_weight / k_target)
    if max_node_weight is None and k_target is not None and int(k_target) > 1:
        total_vw = 0.0
        ok = True
        for u in G_K.nodes():
            try:
                vw = float(G_K.nodes[u].get('vweight', 1.0))
            except Exception:
                ok = False
                break
            if not np.isfinite(vw) or vw < 0:
                ok = False
                break
            total_vw += vw
        if ok and total_vw > 0:
            max_node_weight = 1.5 * (total_vw / float(int(k_target)))
            print(f"Auto max_node_weight heuristic: {max_node_weight:.6g}")

    print(f"Graphs created: G_K with {G_K.number_of_nodes()} nodes and {G_K.number_of_edges()} edges")
    #print(f"Graphs created: G_M with {G_M.number_of_nodes()} nodes and {G_M.number_of_edges()} edges")

    method = (permuting_strategy or 'qa_partitioning').strip().lower()

    # METIS baseline should be called on the original graph (fair comparison vs. whole METIS pipeline)
    if method == 'metis_partitioning':
        part_k = partition_graph_metis(G_K, nparts=k_target, weight=weight, seed=seed, verbose=True)
        print("\n --- Finished Partitioning using METIS (original graph) ---")
        print(f"Partitioning on original graph produced {len(set(part_k.values()))} parts.")

        permute_result = permute_matrices(
            matrix_k=matrix_k,
            matrix_m=matrix_m,
            partition=part_k,
            dof_per_node=dof_per_node,
            verbose=False
        )
        permutation = permute_result['permutation']
        A_K_permuted = permute_result['matrix_k_permuted']
        A_M_permuted = permute_result['matrix_m_permuted']

        print("\n--- Finished Permuting Matrices (METIS baseline) ---")
        print(f"Original K Shape: {matrix_k.shape}, Original K Nonzeros: {matrix_k.nnz}")
        print(f"Permuted K Shape: {A_K_permuted.shape}, Permuted K Nonzeros: {A_K_permuted.nnz}")
        return A_M_permuted, A_K_permuted, permutation

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

    print("\n--- Finished Coarsening using Heavy Edge Matching ---")
    print(f"Coarsening produced {len(graphs)} levels. Final graph has {graphs[-1].number_of_nodes()} nodes and {graphs[-1].number_of_edges()} edges.")

    Gc = graphs[-1]

    # Handle case where coarsening didn't happen (small graph)
    if len(maps) < 1:
        print("Warning: No coarsening occurred (graph too small or already at target size)")

    if method == 'qa_partitioning':
        part_k_coarse, first_qubo, first_subgraph = recursive_kway_anneal(
            Gc,
            k=k_target,
            balance_weight=balance_lambda,
            num_reads=num_reads,
            choose_by='vweight',
            balance_tolerance=balance_tolerance,
            seed=seed,
            num_starts=qa_num_starts,
            select_balance_lambda=qa_select_balance_lambda,
            return_first_qubo=True  # Return QUBO for validation
        )

        print("\n --- Finished Partitioning using Quantum Annealing ---")
        print(f"Partitioning on coarsest graph produced {len(set(part_k_coarse.values()))} parts.")

    elif method == 'qaoa_partitioning':
        print("Method not implemented yet")
        raise NotImplementedError("qaoa_partitioning is not implemented yet")
    else:
        raise ValueError(
            "Unknown permuting_strategy. Use one of: metis_partitioning, qa_partitioning, qaoa_partitioning"
        )

    quantum_partis_k = uncoarsen_and_refine(
        graphs,
        maps,
        part_k_coarse,
        k=k_target,
        balance_tolerance=balance_tolerance,
        weight_attr=weight,
        node_weight_attr='vweight',
        refine_objective=refine_objective,
        refine_balance_lambda=refine_balance_lambda,
        refine_method=refine_method,
        max_passes_per_level=refine_max_passes_per_level,
        max_moves_per_pass=refine_max_moves_per_pass,
        seed=seed,
    )

    print("\n--- Finished Uncoarsening + Refinement ---")
    print(f"Final partition on original graph has {len(set(quantum_partis_k.values()))} parts.")

    # Permute matrices based on partition
    permute_result = permute_matrices(
        matrix_k=matrix_k,
        matrix_m=matrix_m,
        partition=quantum_partis_k,
        dof_per_node=dof_per_node,
        verbose=False
    )

    permutation = permute_result['permutation']
    A_K_permuted = permute_result['matrix_k_permuted']
    A_M_permuted = permute_result['matrix_m_permuted']

    print("\n--- Finished Permuting Matrices ---")
    print(f"Original K Shape: {matrix_k.shape}, Original K Nonzeros: {matrix_k.nnz}")
    print(f"Permuted K Shape: {A_K_permuted.shape}, Permuted K Nonzeros: {A_K_permuted.nnz}")

    return A_M_permuted, A_K_permuted, permutation