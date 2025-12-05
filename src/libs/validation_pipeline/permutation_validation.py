"""
Validation for Matrix Permutation Phase (Step 6)
"""
import numpy as np
from scipy.sparse import issparse, coo_matrix


def validate_matrix_permutation(original_matrix, permuted_matrix, permutation, partition, verbose=False):
    """
    Validate the matrix permutation/reordering based on partition.
    
    Args:
        original_matrix: Original sparse matrix (K or M)
        permuted_matrix: Permuted sparse matrix
        permutation: Permutation array (new_idx = permutation[old_idx])
        partition: Partition dict (node_id -> partition_id)
        verbose: If True, print detailed validation steps
    
    Raises:
        ValueError: If any validation check fails
    """
    if verbose:
        print("=" * 80)
        print("STEP 6: MATRIX PERMUTATION VALIDATION")
        print("=" * 80)
    
    n = original_matrix.shape[0]
    
    # Check 1: Matrix dimensions preserved
    if verbose:
        print("✓ Checking matrix dimensions...")
    
    if permuted_matrix.shape != original_matrix.shape:
        raise ValueError(
            f"❌ Matrix shape changed: {original_matrix.shape} → {permuted_matrix.shape}"
        )
    
    if verbose:
        print(f"  ✓ Matrix dimensions preserved: {permuted_matrix.shape}")
    
    # Check 2: Sparsity structure
    if verbose:
        print("✓ Checking sparsity structure...")
    
    if not issparse(permuted_matrix):
        raise ValueError("❌ Permuted matrix is not sparse")
    
    if original_matrix.nnz != permuted_matrix.nnz:
        raise ValueError(
            f"❌ Number of non-zeros changed: {original_matrix.nnz} → {permuted_matrix.nnz}"
        )
    
    if verbose:
        density = original_matrix.nnz / (n * n) * 100
        print(f"  ✓ Sparsity preserved: {original_matrix.nnz} non-zeros ({density:.2f}% density)")
    
    # Check 3: Permutation array validity
    if verbose:
        print("✓ Checking permutation array...")
    
    if len(permutation) != n:
        raise ValueError(f"❌ Permutation length {len(permutation)} != matrix size {n}")
    
    if set(permutation) != set(range(n)):
        raise ValueError("❌ Permutation is not a valid permutation of [0, n-1]")
    
    if verbose:
        print(f"  ✓ Permutation is valid: length={len(permutation)}")
    
    # Check 4: Permutation consistency with partition
    if verbose:
        print("✓ Checking permutation consistency with partition...")
    
    # Permutation should group nodes by partition
    # Check that nodes with same partition are contiguous in permuted order
    # permutation[new_idx] = old_idx, so we use it directly
    inverse_perm = np.argsort(permutation)  # inverse_perm[old_idx] = new_idx
    
    partition_segments = {}
    for new_idx in range(n):
        old_idx = permutation[new_idx]
        pid = partition[old_idx]
        if pid not in partition_segments:
            partition_segments[pid] = []
        partition_segments[pid].append(new_idx)
    
    # Check each partition forms a contiguous block
    for pid, indices in partition_segments.items():
        sorted_indices = sorted(indices)
        expected_indices = list(range(min(indices), max(indices) + 1))
        if sorted_indices != expected_indices:
            # Debug: find what's wrong
            missing = set(expected_indices) - set(sorted_indices)
            if missing:
                raise ValueError(
                    f"❌ Partition {pid} nodes are not contiguous in permuted matrix.\n"
                    f"   Expected indices [{min(indices)}, {max(indices)}] ({len(expected_indices)} nodes)\n"
                    f"   But got {len(sorted_indices)} nodes with {len(missing)} gaps: {sorted(list(missing))[:10]}"
                )
            else:
                raise ValueError(f"❌ Partition {pid} nodes are not contiguous in permuted matrix")
    
    if verbose:
        print(f"  ✓ Permutation groups nodes by partition (k={len(partition_segments)} blocks)")
        for pid in sorted(partition_segments.keys()):
            indices = partition_segments[pid]
            print(f"    Partition {pid}: indices [{min(indices)}, {max(indices)}] ({len(indices)} nodes)")
    
    # Check 5: Matrix values preserved
    if verbose:
        print("✓ Checking matrix value preservation...")
    
    # Convert to COO for easier comparison
    orig_coo = coo_matrix(original_matrix)
    perm_coo = coo_matrix(permuted_matrix)
    
    # Check that permuted[perm[i], perm[j]] = original[i, j]
    # Build a mapping of (row, col) -> value for original
    orig_dict = {}
    for i, j, v in zip(orig_coo.row, orig_coo.col, orig_coo.data):
        orig_dict[(i, j)] = v
    
    # Check permuted entries
    errors = 0
    for i_perm, j_perm, v_perm in zip(perm_coo.row, perm_coo.col, perm_coo.data):
        # Get original indices
        # permutation[new_idx] = old_idx, so permutation[i_perm] gives us the original index
        i_orig = permutation[i_perm]
        j_orig = permutation[j_perm]
        
        v_orig = orig_dict.get((i_orig, j_orig), 0.0)
        
        if not np.isclose(v_perm, v_orig, rtol=1e-10):
            errors += 1
            if errors <= 3:  # Show first 3 errors
                print(f"    ❌ Value mismatch at permuted ({i_perm}, {j_perm}) = original ({i_orig}, {j_orig}): {v_perm} != {v_orig}")
    
    if errors > 0:
        raise ValueError(f"❌ {errors} value mismatches found in permuted matrix")
    
    if verbose:
        print(f"  ✓ All {perm_coo.nnz} non-zero values preserved correctly")
    
    # Check 6: Symmetry preserved (if original is symmetric)
    if verbose:
        print("✓ Checking symmetry preservation...")
    
    orig_diff = orig_coo - orig_coo.T
    is_symmetric = np.allclose(orig_diff.data, 0, atol=1e-10)
    
    if is_symmetric:
        perm_diff = perm_coo - perm_coo.T
        if not np.allclose(perm_diff.data, 0, atol=1e-10):
            raise ValueError("❌ Original matrix is symmetric but permuted matrix is not")
        if verbose:
            print(f"  ✓ Symmetry preserved (both matrices symmetric)")
    else:
        if verbose:
            print(f"  ✓ Original matrix is non-symmetric (no symmetry to preserve)")
    
    # Check 7: Block structure visibility
    if verbose:
        print("✓ Checking block structure...")
    
    # Count non-zeros in diagonal vs off-diagonal blocks
    block_starts = [min(indices) for indices in partition_segments.values()]
    block_starts.append(n)
    block_starts = sorted(block_starts)
    
    diagonal_nnz = 0
    offdiag_nnz = 0
    
    for i, j, v in zip(perm_coo.row, perm_coo.col, perm_coo.data):
        # Find which block (i, j) belongs to
        block_i = np.searchsorted(block_starts, i, side='right') - 1
        block_j = np.searchsorted(block_starts, j, side='right') - 1
        
        if block_i == block_j:
            diagonal_nnz += 1
        else:
            offdiag_nnz += 1
    
    if verbose:
        total_nnz = diagonal_nnz + offdiag_nnz
        diag_pct = diagonal_nnz / total_nnz * 100 if total_nnz > 0 else 0
        print(f"  ✓ Block structure:")
        print(f"    Diagonal blocks: {diagonal_nnz} non-zeros ({diag_pct:.1f}%)")
        print(f"    Off-diagonal blocks: {offdiag_nnz} non-zeros ({100-diag_pct:.1f}%)")
    
    # Final success message
    print("✅ STEP 6 VALIDATION PASSED: Matrix permutation is valid")
    if verbose:
        print("=" * 80)
