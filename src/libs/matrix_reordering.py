"""
Matrix Reordering Module

Provides functions to permute sparse matrices according to partition results
and save them in Matrix Market format.
"""

import os
import numpy as np
from scipy.sparse import csr_matrix, coo_matrix
from scipy.io import mmwrite


def create_permutation_from_partition(partition: dict, n_nodes: int) -> np.ndarray:
    """
    Create a permutation array from partition assignments.
    Nodes in the same partition are grouped together.
    
    Args:
        partition: Dict {node_id: partition_id}
        n_nodes: Total number of nodes (matrix size)
    
    Returns:
        permutation: Array where permutation[new_idx] = old_idx
    """
    # Verify that partition covers all matrix indices [0, n_nodes-1]
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
    """
    Permute rows and columns of a sparse matrix according to permutation.
    
    The permuted matrix is constructed such that:
    permuted[i, j] = original[permutation[i], permutation[j]]
    
    Args:
        matrix: Sparse matrix (CSR format)
        permutation: Array where permutation[new_idx] = old_idx
    
    Returns:
        Permuted sparse matrix in CSR format
    """
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


def reorder_and_save_matrices(
    matrix_k,
    partition,
    k_target,
    output_dir="../results",
    partition_method="quantum",
    matrix_m=None,
    save_permutation=True,
    verbose=True
):
    """
    Complete pipeline: create permutation, reorder matrices, and save to disk.
    
    Args:
        matrix_k: Original K sparse matrix (CSR format)
        partition: Partition dict {node_id: partition_id}
        k_target: Number of partitions (k)
        output_dir: Directory to save output files
        partition_method: Name of partitioning method (for filenames)
        matrix_m: Optional M sparse matrix (CSR format)
        save_permutation: If True, save permutation array to text file
        verbose: If True, print progress information
    
    Returns:
        dict: Contains permuted matrices and file paths
            {
                'permutation': np.ndarray,
                'matrix_k_permuted': csr_matrix,
                'matrix_m_permuted': csr_matrix or None,
                'k_path': str,
                'm_path': str or None,
                'perm_path': str or None
            }
    """
    if verbose:
        print("=" * 80)
        print("MATRIX REORDERING AND EXPORT")
        print("=" * 80)
    
    # 1. Create permutation
    # Get matrix size (not partition size, as partition may not cover all nodes)
    n_nodes = matrix_k.shape[0]
    if verbose:
        print(f"\n[1/4] Creating permutation for {n_nodes} nodes...")
        print(f"  Partition has {len(partition)} nodes")
    
    permutation = create_permutation_from_partition(partition, n_nodes)
    
    if verbose:
        print(f"  ✓ Permutation array shape: {permutation.shape}")
        print(f"  ✓ First 10 nodes mapping: {permutation[:10]}")
        print(f"  ✓ Nodes per partition:")
        for part_id in sorted(set(partition.values())):
            count = sum(1 for p in partition.values() if p == part_id)
            print(f"      Partition {part_id}: {count} nodes")
    
    # 2. Permute K matrix
    if verbose:
        print(f"\n[2/4] Permuting K matrix...")
    
    matrix_k_permuted = permute_sparse_matrix(matrix_k, permutation)
    
    if verbose:
        print(f"  ✓ Permuted K matrix: shape={matrix_k_permuted.shape}, nnz={matrix_k_permuted.nnz}")
        print(f"  ✓ Sparsity preserved: nnz before={matrix_k.nnz}, after={matrix_k_permuted.nnz}")
    
    # 3. Permute M matrix if provided
    matrix_m_permuted = None
    if matrix_m is not None:
        if verbose:
            print(f"\n[3/4] Permuting M matrix...")
        
        matrix_m_permuted = permute_sparse_matrix(matrix_m, permutation)
        
        if verbose:
            print(f"  ✓ Permuted M matrix: shape={matrix_m_permuted.shape}, nnz={matrix_m_permuted.nnz}")
            print(f"  ✓ Sparsity preserved: nnz before={matrix_m.nnz}, after={matrix_m_permuted.nnz}")
    else:
        if verbose:
            print(f"\n[3/4] No M matrix provided (skipped)")
    
    # 4. Save to disk
    if verbose:
        print(f"\n[4/4] Saving matrices to disk...")
    
    # Create output directory
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    if verbose:
        print(f"  ✓ Output directory: {output_dir}")
    
    # Save K matrix
    k_path = os.path.join(output_dir, f"matrix_k_reordered_{partition_method}_k{k_target}.mtx")
    mmwrite(
        k_path,
        matrix_k_permuted,
        comment=f"Reordered K matrix using {partition_method} partitioning with k={k_target}",
        field='real',
        symmetry='general'
    )
    if verbose:
        print(f"  ✓ Saved K matrix: {k_path}")
        print(f"      Size: {matrix_k_permuted.shape}, nnz: {matrix_k_permuted.nnz}")
    
    # Save M matrix if available
    m_path = None
    if matrix_m_permuted is not None:
        m_path = os.path.join(output_dir, f"matrix_m_reordered_{partition_method}_k{k_target}.mtx")
        mmwrite(
            m_path,
            matrix_m_permuted,
            comment=f"Reordered M matrix using {partition_method} partitioning with k={k_target}",
            field='real',
            symmetry='general'
        )
        if verbose:
            print(f"  ✓ Saved M matrix: {m_path}")
            print(f"      Size: {matrix_m_permuted.shape}, nnz: {matrix_m_permuted.nnz}")
    
    # Save permutation array
    perm_path = None
    if save_permutation:
        perm_path = os.path.join(output_dir, f"permutation_{partition_method}_k{k_target}.txt")
        np.savetxt(
            perm_path,
            permutation,
            fmt='%d',
            header=f"Permutation array for {partition_method} partitioning with k={k_target}\nFormat: new_index -> old_index"
        )
        if verbose:
            print(f"  ✓ Saved permutation: {perm_path}")
    
    if verbose:
        print(f"\n{'=' * 80}")
        print("✅ Matrix reordering completed successfully!")
        print("=" * 80)
    
    return {
        'permutation': permutation,
        'matrix_k_permuted': matrix_k_permuted,
        'matrix_m_permuted': matrix_m_permuted,
        'k_path': k_path,
        'm_path': m_path,
        'perm_path': perm_path
    }
