"""
Matrix Reordering Module

Provides functions to permute sparse matrices according to partition results
and save them in Matrix Market format.
"""

import os
import numpy as np
from scipy.sparse import csr_matrix, coo_matrix
from scipy.io import mmwrite
from datetime import datetime


def create_permutation_from_partition(partition: dict, n_nodes: int) -> np.ndarray:
    partition_nodes = set(partition.keys())
    expected_nodes = set(range(n_nodes))
    
    if partition_nodes != expected_nodes:
        missing = expected_nodes - partition_nodes
        extra = partition_nodes - expected_nodes
        error_msg = f"Partition nodes mismatch with matrix size {n_nodes}."
        if missing:
            error_msg += f"\n  Missing {len(missing)} nodes: {sorted(list(missing))[:10]}"
        if extra:
            error_msg += f"\n  Extra {len(extra)} nodes: {sorted(list(extra))[:10]}"
        raise ValueError(error_msg)
    
    # Group nodes by partition
    partitions = {}
    for node, part_id in partition.items():
        if part_id not in partitions:
            partitions[part_id] = []
        partitions[part_id].append(node)
    
    # Sort partitions by ID and concatenate nodes
    permutation = []
    for part_id in sorted(partitions.keys()):
        # Sort nodes within partition for consistency
        nodes_in_part = sorted(partitions[part_id])
        permutation.extend(nodes_in_part)
    
    return np.array(permutation, dtype=int)


def permute_sparse_matrix(matrix, permutation):
    # Convert to COO for easier permutation
    matrix_coo = matrix.tocoo()
    
    # Create inverse permutation: inv_perm[old_idx] = new_idx
    inv_perm = np.empty_like(permutation)
    inv_perm[permutation] = np.arange(len(permutation))
    
    # For each entry at original[old_row, old_col], place it at permuted[new_row, new_col]
    # where new_row = inv_perm[old_row] and new_col = inv_perm[old_col]
    # This ensures: permuted[new_idx, new_idx'] = original[permutation[new_idx], permutation[new_idx']]
    new_row = inv_perm[matrix_coo.row]
    new_col = inv_perm[matrix_coo.col]
    
    # Create new matrix with permuted indices
    permuted_matrix = coo_matrix(
        (matrix_coo.data, (new_row, new_col)),
        shape=matrix_coo.shape
    )
    
    return permuted_matrix.tocsr()


def permute_matrices(
    matrix_k,
    matrix_m,
    partition,
    dof_per_node: int = 1,
    verbose: bool = False,
):
    
    if matrix_k.shape != matrix_m.shape:
        raise ValueError(f"K and M must have the same shape. Got K={matrix_k.shape}, M={matrix_m.shape}")

    if dof_per_node <= 0:
        raise ValueError("dof_per_node must be a positive integer")

    n_total = matrix_k.shape[0]
    if n_total % dof_per_node != 0:
        raise ValueError(
            f"Matrix size {n_total} is not divisible by dof_per_node={dof_per_node}. "
            "Ensure matrices are assembled as (n_nodes*dof)x(n_nodes*dof)."
        )

    n_nodes = n_total // dof_per_node

    # Build node-level permutation (new_node -> old_node)
    node_perm = create_permutation_from_partition(partition, n_nodes)

    # Expand to DOF-level permutation if needed
    if dof_per_node == 1:
        permutation = node_perm
    else:
        permutation = node_to_dof_permutation(node_perm, dof_per_node)

    if verbose:
        print(f"Permutation built: nodes={n_nodes}, dof_per_node={dof_per_node}, total_dofs={n_total}")
    
    matrix_k_permuted = permute_sparse_matrix(matrix_k, permutation)
    matrix_m_permuted = permute_sparse_matrix(matrix_m, permutation)
    
    return {
        'permutation': permutation,
        'matrix_k_permuted': matrix_k_permuted,
        'matrix_m_permuted': matrix_m_permuted
    }


def node_to_dof_permutation(node_perm: np.ndarray, dof_per_node: int) -> np.ndarray:
    """
    Expand a node-level permutation (mapping new_node -> old_node) to DOF-level,
    preserving the intra-node DOF ordering.

    Args:
        node_perm: array of shape (N,), where node_perm[new_node] = old_node
        dof_per_node: number of DOFs per node (e.g., 3 for 3D mechanics)

    Returns:
        dof_perm: array of shape (N*d,), where dof_perm[new_dof] = old_dof
    """
    N = int(len(node_perm))
    d = int(dof_per_node)
    dof_perm = np.empty(N * d, dtype=int)
    for new_node_idx, old_node_idx in enumerate(node_perm):
        base_new = new_node_idx * d
        base_old = old_node_idx * d
        for r in range(d):
            dof_perm[base_new + r] = base_old + r
    return dof_perm


def save_permuted_matrices(
    matrix_k_permuted,
    matrix_m_permuted,
    permutation,
    k_target,
    output_dir="../results",
    partition_method="quantum",
    save_permutation=True,
    original_matrix_filename=None,
    coarsening_params=None,
    annealing_params=None
):
    output_dir = os.path.abspath(output_dir)
    n_nodes = matrix_k_permuted.shape[0]
    
    # Extract matrix base name from original filename
    if original_matrix_filename:
        base_name = os.path.basename(original_matrix_filename)
        # Remove .mtx extension
        if base_name.endswith('.mtx'):
            base_name = base_name[:-4]
        
        matrix_folder = base_name
    else:
        matrix_folder = f"matrix_{n_nodes}nodes"
    
    # Create matrix-specific folder
    matrix_dir = os.path.join(output_dir, matrix_folder)
    os.makedirs(matrix_dir, exist_ok=True)
    
    # Build run-specific folder name with parameters
    run_params = [
        f"method_{partition_method}",
        f"k{k_target}"
    ]
    
    if coarsening_params:
        if 'strategy' in coarsening_params:
            run_params.append(f"coarse_{coarsening_params['strategy']}")
        if 'limit' in coarsening_params:
            run_params.append(f"limit{coarsening_params['limit']}")
    
    if annealing_params:
        if 'balance_lambda' in annealing_params:
            run_params.append(f"lambda{annealing_params['balance_lambda']}")
        if 'num_reads' in annealing_params:
            run_params.append(f"reads{annealing_params['num_reads']}")
        if 'balance_tolerance' in annealing_params:
            run_params.append(f"tol{annealing_params['balance_tolerance']}")
    
    run_folder = "_".join(run_params)
    
    # Add timestamp to ensure uniqueness
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = f"{run_folder}_{timestamp}"
    
    # Create run-specific folder
    run_dir = os.path.join(matrix_dir, run_folder)
    os.makedirs(run_dir, exist_ok=True)
    
    # Save K matrix
    k_path = os.path.join(run_dir, f"matrix_k_reordered.mtx")
    mmwrite(
        k_path,
        matrix_k_permuted,
        comment=f"Reordered K matrix using {partition_method} partitioning with k={k_target}",
        field='real',
        symmetry='general'
    )
    
    # Save M matrix if available
    m_path = os.path.join(run_dir, f"matrix_m_reordered.mtx")
    mmwrite(
        m_path,
        matrix_m_permuted,
        comment=f"Reordered M matrix using {partition_method} partitioning with k={k_target}",
        field='real',
        symmetry='general'
    )
    
    # Save permutation array
    perm_path = None
    if save_permutation:
        perm_path = os.path.join(run_dir, f"permutation.txt")
        np.savetxt(
            perm_path,
            permutation,
            fmt='%d',
            header=f"Permutation array for {partition_method} partitioning with k={k_target}\nFormat: new_index -> old_index"
        )

    
    # Save run parameters to a metadata file
    metadata_path = os.path.join(run_dir, "run_metadata.txt")
    with open(metadata_path, 'w') as f:
        f.write(f"Run Metadata\n")
        f.write(f"{'=' * 80}\n\n")
        f.write(f"Timestamp: {timestamp}\n")
        f.write(f"Original matrix: {original_matrix_filename or 'Unknown'}\n")
        f.write(f"Matrix size: {n_nodes} nodes\n")
        f.write(f"Partition method: {partition_method}\n")
        f.write(f"Number of partitions (k): {k_target}\n\n")
        
        if coarsening_params:
            f.write(f"Coarsening Parameters:\n")
            for key, val in coarsening_params.items():
                f.write(f"  {key}: {val}\n")
            f.write("\n")
        
        if annealing_params:
            f.write(f"Annealing Parameters:\n")
            for key, val in annealing_params.items():
                f.write(f"  {key}: {val}\n")
            f.write("\n")
        
        f.write(f"Output Files:\n")
        f.write(f"  K matrix: matrix_k_reordered.mtx\n")
        f.write(f"  M matrix: matrix_m_reordered.mtx\n")

        if save_permutation:
            f.write(f"  Permutation: permutation.txt\n")

    return {
        'k_path': k_path,
        'm_path': m_path,
        'perm_path': perm_path,
        'run_dir': run_dir
    }
