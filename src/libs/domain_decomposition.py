from libs.log import info, progress, finished, start_timer
from libs.utils import *
from libs.permutation import *
from libs.multilevel_scheme.coarsening import *
from libs.multilevel_scheme.partitioning import *
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
               partitioning_strategy: str = 'qa_partitioning',
               qa_num_starts: int = 1,
               qa_select_balance_lambda: float = 1.0e6,
               refine_objective: str = 'cut',
               refine_balance_lambda: float = 1.0,
               refine_method: str = 'greedy',
               refine_max_passes_per_level: int = 5,
               refine_max_moves_per_pass: int | None = None,
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
    progress("Converting matrices to graphs")
    G_K = matrix_to_graph(matrix_k, dof_per_node=dof_per_node)
    G_M = matrix_to_graph(matrix_m, dof_per_node=dof_per_node)
    finished("Converting matrices to graphs", start_timer())

    _set_node_vweight_diag(G_K, diag_K, dof_per_node)
    _set_node_vweight_diag(G_M, diag_M, dof_per_node)
    _set_edge_weight_attr(G_K, weight)
    _set_edge_weight_attr(G_M, weight)

    # Common rule of thumb: ~1.5 * (total_node_weight / k_target)
    if max_node_weight is None and k_target is not None and int(k_target) > 1:
        total_vw = sum(float(G_K.nodes[u].get('vweight', 1.0)) for u in G_K.nodes())
        max_node_weight = 1.5 * (total_vw / float(int(k_target)))
        info(f"Auto max_node_weight heuristic: {max_node_weight:.6g}")

    info(f"Graph G_K with {G_K.number_of_nodes()} nodes and {G_K.number_of_edges()} edges created from K matrix.")

    if partitioning_strategy == 'metis_partitioning':
        start = start_timer()
        progress("Multilevel Partitioning Scheme using METIS")
        part_k = partition_graph_metis(G_K, nparts=k_target)
        finished("Multilevel Partitioning Scheme using METIS", start)
        info(f"Partitioning on original graph produced {len(set(part_k.values()))} parts.")

    elif partitioning_strategy == 'qa_partitioning':
        start = start_timer()
        progress("Coarsening using Heavy Edge Matching")
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

        finished("Coarsening using Heavy Edge Matching", start)
        info(f"Coarsening produced {len(graphs)} levels. Final graph has {graphs[-1].number_of_nodes()} nodes and {graphs[-1].number_of_edges()} edges.")

        Gc = graphs[-1]
        # Handle case where coarsening didn't happen (small graph)
        if len(maps) < 1:
            info("Warning: No coarsening occurred (graph too small or already at target size)")

        start = start_timer()
        progress("Partitioning coarsest graph using Quantum Annealing")
        part_k_coarse = recursive_kway_anneal(
            Gc,
            k=k_target,
            balance_lambda=balance_lambda,
            num_reads=num_reads,
            choose_by='vweight',
            balance_tolerance=balance_tolerance,
            seed=seed,
            num_starts=qa_num_starts,
            select_balance_lambda=qa_select_balance_lambda,
        )

        finished("Partitioning coarsest graph using Quantum Annealing", start)
        info(f"Partitioning on coarsest graph produced {len(set(part_k_coarse.values()))} parts.")

        start = start_timer()
        progress(f"Uncoarsening + Refining with Kernighan-Lin")
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

        finished("Uncoarsening + Refining with Kernighan-Lin", start)
        info(f"Final partition on original graph has {len(set(part_k.values()))} parts.")

    start = start_timer()
    progress("Permuting matrices based on partition")
    # Permute matrices based on partition
    permute_result = permute_matrices(
        matrix_k=matrix_k,
        matrix_m=matrix_m,
        partition=part_k,
        dof_per_node=dof_per_node,
        verbose=False
    )

    permutation = permute_result['permutation']
    matrix_k_permuted = permute_result['matrix_k_permuted']
    matrix_m_permuted = permute_result['matrix_m_permuted']

    finished("Permuting matrices based on partition", start)
    info(f"Original K Shape: {matrix_k.shape}, Original K Nonzeros: {matrix_k.nnz}")
    info(f"Permuted K Shape: {matrix_k_permuted.shape}, Permuted K Nonzeros: {matrix_k_permuted.nnz}")

    info(f"Original M Shape: {matrix_m.shape}, Original M Nonzeros: {matrix_m.nnz}")
    info(f"Permuted M Shape: {matrix_m_permuted.shape}, Permuted M Nonzeros: {matrix_m_permuted.nnz}")

    return matrix_m_permuted, matrix_k_permuted, permutation