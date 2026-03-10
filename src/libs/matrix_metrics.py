import numpy as np
from scipy import sparse
from typing import Any

def _as_csr(A):
    return A.tocsr() if sparse.issparse(A) else sparse.csr_matrix(A)

def _check_permutation_matrix_relation(matrix_name, A_original, A_permuted, permutation, n_samples=100000, seed=0, tol=0.0):
    """
    Verifies (by random entry checks) that:
        A_permuted[i, j] == A_original[permutation[i], permutation[j]]
    This is the relationship produced by permuting rows/cols with the same permutation.
    """
    A0 = _as_csr(A_original)
    Ap = _as_csr(A_permuted)
    p = np.asarray(permutation, dtype=int)

    n = A0.shape[0]
    assert A0.shape == Ap.shape
    assert p.shape[0] == n

    rng = np.random.default_rng(seed)
    ii = rng.integers(0, n, size=n_samples)
    jj = rng.integers(0, n, size=n_samples)

    mismatches = 0
    max_abs_err = 0.0
    for i, j in zip(ii, jj):
        a_ref = A0[p[i], p[j]]
        a_got = Ap[i, j]
        err = float(abs(a_ref - a_got))
        if err > tol:
            mismatches += 1
            if err > max_abs_err:
                max_abs_err = err
                
    return mismatches, max_abs_err

def _sparsity_metrics(A, band: int = 200):
    A = _as_csr(A)
    coo = A.tocoo()
    r = coo.row
    c = coo.col
    d = np.abs(r - c)
    bw = int(d.max()) if d.size else 0
    avg_bw = float(d.mean()) if d.size else 0.0
    nnz = int(A.nnz)
    n = int(A.shape[0])

    in_band = int(np.count_nonzero(d <= band)) if d.size else 0
    frac_in_band = (in_band / nnz) if nnz else 1.0

    return {
        "n": n,
        "nnz": nnz,
        "bandwidth": bw,
        "avg_bandwidth": avg_bw,
        f"nnz_within_|i-j|<={band}": in_band,
        f"frac_within_|i-j|<={band}": frac_in_band,
    }

def _check_structural_metrics(matrix_name, method_name, A0, Ap):
    m0 = _sparsity_metrics(A0, band=200)
    mp = _sparsity_metrics(Ap, band=200)

    keys = list(dict.fromkeys(list(m0.keys()) + list(mp.keys())))

    def _fmt(x):
        if isinstance(x, float):
            return f"{x:.6g}"
        return str(x)

    rows = []
    for k in keys:
        v0 = m0.get(k, "")
        vp = mp.get(k, "")
        rows.append((k, _fmt(v0), _fmt(vp)))

    return m0, mp

def collect_metrics(
	*,
	matrix_name: str,
	method_name: str,
	original,
	permuted,
	permutation: np.ndarray,
	perm_check_samples: int,
	perm_check_seed: int,
	perm_check_tol: float,
) -> dict[str, Any]:
	mismatches, max_abs_err = _check_permutation_matrix_relation(
		f"{matrix_name}_{method_name}",
		original,
		permuted,
		permutation,
		n_samples=perm_check_samples,
		seed=perm_check_seed,
		tol=perm_check_tol,
	)

	m0, mp = _check_structural_metrics(matrix_name, method_name, original, permuted)
	m0_band200 = _sparsity_metrics(original, band=200)
	mp_band200 = _sparsity_metrics(permuted, band=200)

	return {
		"permutation_check": {
			"samples": int(perm_check_samples),
			"seed": int(perm_check_seed),
			"tol": float(perm_check_tol),
			"mismatches": int(mismatches),
			"max_abs_err": float(max_abs_err),
		},
		"structural_metrics": {
			"original": m0,
			"permuted": mp,
			"band200_original": m0_band200,
			"band200_permuted": mp_band200,
		},
	}
