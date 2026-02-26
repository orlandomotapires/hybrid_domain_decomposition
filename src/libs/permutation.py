from libs.utils import *
from libs.matrix_reordering import *
from libs.multilevel_scheme.coarsening import *
from libs.multilevel_scheme.partitioning import *
from libs.metis_backend import partition_graph_metis

def permute_mk(matrix_m, matrix_k, 
               dof_per_node, 
               coarsen_limit=300, 
               max_levels=10, 
               weight='weight', 
               strategy='sorted',
               coarsen_ratio=2.0, 
               max_node_weight=None, 
               k_target=2, 
               balance_lambda=2.0, 
               num_reads=1000, 
               balance_tolerance=2.0,
               permuting_strategy: str = 'qa_partitioning'):

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
    G_K = matrix_to_graph(
        matrix_k,
        symmetrize='sum',
        drop_diagonal=True,
        abs_weights=True,
        node_vweight='diag',
        diag=diag_K,
        dof_per_node=dof_per_node
    )
    G_M = matrix_to_graph(
        matrix_m,
        symmetrize='sum',
        drop_diagonal=True,
        abs_weights=True,
        node_vweight='diag',
        diag=diag_M,
        dof_per_node=dof_per_node
    )

    print(f"Graphs created: G_K with {G_K.number_of_nodes()} nodes and {G_K.number_of_edges()} edges")
    #print(f"Graphs created: G_M with {G_M.number_of_nodes()} nodes and {G_M.number_of_edges()} edges")

    graphs, maps = coarsen_chain(
        G_K, 
        trial_seed=42, 
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

    method = permuting_strategy
    if method == 'qa_partitioning':
        # Run recursive k-way annealing and capture first QUBO for validation
        part_k_coarse, first_qubo, first_subgraph = recursive_kway_anneal(
            Gc,
            k=k_target,
            balance_weight=balance_lambda,
            num_reads=num_reads,
            choose_by='vweight',
            balance_tolerance=balance_tolerance,
            seed=42,
            return_first_qubo=True  # Return QUBO for validation
        )

        print("\n --- Finished Partitioning using Quantum Annealing ---")
        print(f"Partitioning on coarsest graph produced {len(set(part_k_coarse.values()))} parts.")

    elif method == 'metis_partitioning':
        part_k_coarse = partition_graph_metis(Gc, nparts=k_target, weight=weight, seed=42, verbose=True)
        first_qubo = None
        first_subgraph = None
        print("\n --- Finished Partitioning using METIS ---")
        print(f"Partitioning on coarsest graph produced {len(set(part_k_coarse.values()))} parts.")

    elif method == 'qaoa_partitioning':
        print("Method not implemented yet")
        raise NotImplementedError("qaoa_partitioning is not implemented yet")
    else:
        raise ValueError(
            "Unknown permuting_strategy. Use one of: metis_partitioning, qa_partitioning, qaoa_partitioning"
        )

    quantum_partis_k = lift_partition_to_finer(graphs, maps, part_k_coarse)

    print("\n--- Finished Uncoarsening ---")
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