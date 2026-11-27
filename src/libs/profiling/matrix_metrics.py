import numpy as np
from scipy import sparse
from typing import Any

INITIAL_PERCENT = 0
FINAL_PERCENT = 5
STEP_PERCENT = 0.05

DEFAULT_PERCENT_BANDS = tuple(round(step * STEP_PERCENT, 10) for step in range(int(INITIAL_PERCENT / STEP_PERCENT), int(FINAL_PERCENT / STEP_PERCENT)))  # 0.0%, 0.05%, ..., 4.95%

def _as_csr(A):
    return A.tocsr() if sparse.issparse(A) else sparse.csr_matrix(A)

def _check_permutation_matrix_relation(matrix_name, A_original, A_permuted, permutation, n_samples=None, seed=None, tol=0.0):
    """Check every entry of ``A_permuted[i, j] == A_original[permutation[i], permutation[j]]``.

    Returns ``(mismatches, max_abs_err)``: the number of entries that differ by more than ``tol``
    and the largest difference. Exact and O(nnz). (It used to sample random (i, j) positions,
    which on a large sparse matrix almost never hit a nonzero; ``n_samples`` and ``seed`` are
    kept for callers and ignored.)
    """
    A0 = _as_csr(A_original)
    Ap = _as_csr(A_permuted)
    p = np.asarray(permutation, dtype=int)

    n = A0.shape[0]
    assert A0.shape == Ap.shape
    assert p.shape[0] == n

    # float64 first: unsigned integers would wrap around in the subtraction, booleans cannot subtract.
    diff = abs(Ap.astype(np.float64) - A0[p][:, p].astype(np.float64)).tocsr()
    diff.eliminate_zeros()
    errors = diff.data
    bad = ~np.isfinite(errors) | (errors > tol)  # a NaN entry never "matches"
    mismatches = int(np.count_nonzero(bad))
    finite = errors[np.isfinite(errors)]
    max_abs_err = float("inf") if finite.size < errors.size else (float(finite.max()) if finite.size else 0.0)
    return mismatches, max_abs_err


def _format_percent_label(percent: float) -> str:
    value = round(float(percent), 10)
    if float(value).is_integer():
        return f"{value:.1f}%"
    return f"{value:.10f}".rstrip("0").rstrip(".") + "%"

def _percent_band_to_nodes(n: int, percent: float) -> int:
    if n <= 0:
        return 0
    if percent <= 0.0:
        return 0
    return max(1, int(np.ceil((float(percent) / 100.0) * float(n))))


def _sparsity_metrics(A, band: int = 200, percent_bands = DEFAULT_PERCENT_BANDS):
    A = _as_csr(A)
    coo = A.tocoo()
    r = coo.row
    c = coo.col
    d = np.abs(r - c)
    bw = int(d.max()) if d.size else 0
    avg_bw = float(d.mean()) if d.size else 0.0
    nnz = int(A.nnz)
    n = int(A.shape[0])

    sorted_distances = np.sort(d) if d.size else np.array([], dtype=int)
    in_band = int(np.searchsorted(sorted_distances, band, side='right')) if d.size else 0
    frac_in_band = (in_band / nnz) if nnz else 1.0

    metrics = {
        "n": n,
        "nnz": nnz,
        "bandwidth": bw,
        "avg_bandwidth": avg_bw,
        f"nnz_within_|i-j|<={band}": in_band,
        f"frac_within_|i-j|<={band}": frac_in_band,
    }

    for percent in percent_bands:
        percent_value = float(percent)
        if percent_value <= 0.0:
            band_nodes = 0
        else:
            band_nodes = _percent_band_to_nodes(n, percent_value)

        in_percent_band = int(np.searchsorted(sorted_distances, band_nodes, side='right')) if d.size else 0
        frac_in_percent_band = (in_percent_band / nnz) if nnz else 1.0
        percent_label = _format_percent_label(percent_value)

        metrics[f"band_nodes_at_{percent_label}_of_n"] = band_nodes
        metrics[f"nnz_within_|i-j|<={percent_label}_of_n"] = in_percent_band
        metrics[f"frac_within_|i-j|<={percent_label}_of_n"] = frac_in_percent_band

    return metrics


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
        },
    }
