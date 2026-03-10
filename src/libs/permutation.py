import numpy as np
from scipy.sparse import coo_matrix, issparse
from libs.log import info

def _create_permutation_from_partition(partition: dict, n_nodes: int) -> np.ndarray:
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

def _permute_sparse_matrix(matrix, permutation):
    permutation = np.asarray(permutation, dtype=int)

    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"Matrix must be square, got shape {matrix.shape}")
    if len(permutation) != matrix.shape[0]:
        raise ValueError(
            f"Permutation length {len(permutation)} must match matrix size {matrix.shape[0]}"
        )

    if issparse(matrix):
        # Sparse path: remap indices using inverse permutation
        matrix_coo = matrix.tocoo()
        inv_perm = np.empty_like(permutation)
        inv_perm[permutation] = np.arange(len(permutation))
        new_row = inv_perm[matrix_coo.row]
        new_col = inv_perm[matrix_coo.col]
        permuted_matrix = coo_matrix((matrix_coo.data, (new_row, new_col)), shape=matrix_coo.shape)
        return permuted_matrix.tocsr()
    else:
        # Dense path: advanced indexing with np.ix_
        return matrix[np.ix_(permutation, permutation)]

def _node_to_dof_permutation(node_perm: np.ndarray, dof_per_node: int) -> np.ndarray:
    N = int(len(node_perm))
    d = int(dof_per_node)
    dof_perm = np.empty(N * d, dtype=int)
    for new_node_idx, old_node_idx in enumerate(node_perm):
        base_new = new_node_idx * d
        base_old = old_node_idx * d
        for r in range(d):
            dof_perm[base_new + r] = base_old + r
    return dof_perm

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
    node_perm = _create_permutation_from_partition(partition, n_nodes)

    # Expand to DOF-level permutation if needed
    if dof_per_node == 1:
        permutation = node_perm
    else:
        permutation = _node_to_dof_permutation(node_perm, dof_per_node)

    if verbose:
        info(f"Permutation built: nodes={n_nodes}, dof_per_node={dof_per_node}, total_dofs={n_total}")
    
    matrix_k_permuted = _permute_sparse_matrix(matrix_k, permutation)
    matrix_m_permuted = _permute_sparse_matrix(matrix_m, permutation)
    
    return {
        'permutation': permutation,
        'matrix_k_permuted': matrix_k_permuted,
        'matrix_m_permuted': matrix_m_permuted
    }
