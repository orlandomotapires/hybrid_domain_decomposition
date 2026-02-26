import numpy as np
from scipy import sparse

def _as_csr(A):
    return A.tocsr() if sparse.issparse(A) else sparse.csr_matrix(A)

def check_permutation_matrix_relation(matrix_name, A_original, A_permuted, permutation, n_samples=100000, seed=0, tol=0.0):
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

    print(f"Permutation check for {matrix_name}:")
    print(f"  samples={n_samples}, mismatches={mismatches}, max_abs_err={max_abs_err}")
    return mismatches, max_abs_err

def sparsity_metrics(A, band: int = 200):
    """Simple structural metrics that can be computed from the matrix alone."""
    A = _as_csr(A)
    coo = A.tocoo()
    r = coo.row
    c = coo.col
    d = np.abs(r - c)
    bw = int(d.max()) if d.size else 0
    nnz = int(A.nnz)
    n = int(A.shape[0])

    in_band = int(np.count_nonzero(d <= band)) if d.size else 0
    frac_in_band = (in_band / nnz) if nnz else 1.0

    return {
        "n": n,
        "nnz": nnz,
        "bandwidth": bw,
        f"nnz_within_|i-j|<={band}": in_band,
        f"frac_within_|i-j|<={band}": frac_in_band,
    }

def check_structural_metrics(matrix_name, method_name, A0, Ap):
    m0 = sparsity_metrics(A0, band=200)
    mp = sparsity_metrics(Ap, band=200)

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

    # Jupyter-friendly HTML table (fallback to plain text if IPython isn't available)
    try:
        from IPython.display import display, HTML  # type: ignore

        html = [f"<h4>{matrix_name}: structural metrics for method '{method_name}'</h4>"]
        html.append("<table style='border-collapse:collapse; border:1px solid #ccc;'>")
        html.append(
            "<thead><tr>"
            "<th style='border:1px solid #ccc; padding:6px; text-align:left;'>metric</th>"
            "<th style='border:1px solid #ccc; padding:6px; text-align:right;'>original</th>"
            "<th style='border:1px solid #ccc; padding:6px; text-align:right;'>permuted</th>"
            "</tr></thead><tbody>"
        )
        for metric, original, permuted in rows:
            html.append(
                "<tr>"
                f"<td style='border:1px solid #ccc; padding:6px; text-align:left;'>{metric}</td>"
                f"<td style='border:1px solid #ccc; padding:6px; text-align:right;'>{original}</td>"
                f"<td style='border:1px solid #ccc; padding:6px; text-align:right;'>{permuted}</td>"
                "</tr>"
            )
        html.append("</tbody></table>")
        display(HTML("".join(html)))
    except Exception:
        print(f"\n{matrix_name}: structural metrics for method '{method_name}'")
        w = max(len(r[0]) for r in rows) if rows else 10
        print(f"{'metric'.ljust(w)}  {'original':>12}  {'permuted':>12}")
        for metric, original, permuted in rows:
            print(f"{metric.ljust(w)}  {original:>12}  {permuted:>12}")

    return m0, mp