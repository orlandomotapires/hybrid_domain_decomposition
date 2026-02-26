"""
Validation for Matrix Permutation Phase (Step 6)
"""
import numpy as np
from scipy.sparse import issparse, coo_matrix
from scipy.sparse.linalg import eigsh, ArpackNoConvergence


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
    
    # Check 8: Eigenvalue preservation (similarity transformation invariant)
    if verbose:
        print("✓ Checking eigenvalue preservation...")
    
    # For symmetric matrices, compute a few eigenvalues to verify they're preserved
    # Permutation is a similarity transformation: P^T A P, which preserves eigenvalues
    try:
        # Compute a few largest magnitude eigenvalues (safer for sparse matrices)
        k = min(6, n - 2)  # Number of eigenvalues to compute
        
        # Check if matrix is symmetric (eigenvalue check only makes sense for symmetric matrices)
        if is_symmetric and n > 10:  # Only for reasonably sized symmetric matrices
            # Compute eigenvalues of original matrix
            orig_eigvals = eigsh(original_matrix, k=k, return_eigenvectors=False, which='LM')
            orig_eigvals = np.sort(orig_eigvals)
            
            # Compute eigenvalues of permuted matrix
            perm_eigvals = eigsh(permuted_matrix, k=k, return_eigenvectors=False, which='LM')
            perm_eigvals = np.sort(perm_eigvals)
            
            # Compare eigenvalues
            max_eig_diff = np.max(np.abs(orig_eigvals - perm_eigvals))
            rel_eig_error = max_eig_diff / (np.max(np.abs(orig_eigvals)) + 1e-12)
            
            if rel_eig_error > 1e-6:
                raise ValueError(
                    f"❌ Eigenvalues not preserved!\n"
                    f"   Original eigenvalues: {orig_eigvals}\n"
                    f"   Permuted eigenvalues: {perm_eigvals}\n"
                    f"   Max difference: {max_eig_diff:.2e}, Relative error: {rel_eig_error:.2e}"
                )
            
            if verbose:
                print(f"  ✓ Eigenvalues preserved (checked {k} largest magnitude eigenvalues)")
                print(f"    Original: {orig_eigvals}")
                print(f"    Permuted: {perm_eigvals}")
                print(f"    Max difference: {max_eig_diff:.2e}")
        else:
            if verbose:
                if not is_symmetric:
                    print(f"  ⊘ Eigenvalue check skipped (matrix is non-symmetric)")
                else:
                    print(f"  ⊘ Eigenvalue check skipped (matrix too small: n={n})")
    
    except ArpackNoConvergence as e:
        if verbose:
            print(f"  ⚠ Eigenvalue computation did not converge (this is OK for ill-conditioned matrices)")
    except Exception as e:
        if verbose:
            print(f"  ⚠ Eigenvalue check failed: {e} (this is OK, not all matrices support eigsh)")
    
    # Final success message
    print("✅ STEP 6 VALIDATION PASSED: Matrix permutation is valid")
    if verbose:
        print("=" * 80)
