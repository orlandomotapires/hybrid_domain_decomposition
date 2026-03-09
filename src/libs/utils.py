from __future__ import annotations

from scipy.io import mmread
from scipy.io import mmwrite
import scipy.sparse as sp
import numpy as np
import networkx as nx

import json
from datetime import datetime
from pathlib import Path
from typing import Any

def load_mtx(path, label=None):
    A = mmread(path)
    if sp.issparse(A):
        return A.tocsr()
    return sp.csr_matrix(A)

def write_json(path: Path, obj: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as f:
		json.dump(obj, f, indent=2, sort_keys=True)

def writte_results_table_text(path: Path, data: dict[str, Any]) -> None:
    def _format_value(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.6g}"
        if isinstance(v, (int, np.integer)):
            return str(int(v))
        if isinstance(v, (np.floating,)):
            return f"{float(v):.6g}"
        if v is None:
            return ""
        return str(v).replace("\n", " ")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for matrix_name, matrix_metrics in data.items():
            f.write(f"Matrix {matrix_name} metrics (original x permuted)\n\n")

            structural = {}
            if isinstance(matrix_metrics, dict):
                structural = matrix_metrics.get("structural_metrics", {})

            original = structural.get("original", {}) if isinstance(structural, dict) else {}
            permuted = structural.get("permuted", {}) if isinstance(structural, dict) else {}

            keys = list(dict.fromkeys(list(original.keys()) + list(permuted.keys())))
            rows: list[tuple[str, str, str]] = []
            for k in keys:
                rows.append(
                    (
                        str(k),
                        _format_value(original.get(k, "")),
                        _format_value(permuted.get(k, "")),
                    )
                )

            w_metric = max([len("Metric")] + [len(r[0]) for r in rows])
            w_orig = max([len("Original")] + [len(r[1]) for r in rows])
            w_perm = max([len("Permuted")] + [len(r[2]) for r in rows])

            f.write(f"{'Metric'.ljust(w_metric)}  {'Original'.rjust(w_orig)}  {'Permuted'.rjust(w_perm)}\n")
            for metric, orig_v, perm_v in rows:
                f.write(
                    f"{metric.ljust(w_metric)}  {orig_v.rjust(w_orig)}  {perm_v.rjust(w_perm)}\n"
                )

            perm_check = matrix_metrics.get("permutation_check", {}) if isinstance(matrix_metrics, dict) else {}
            if isinstance(perm_check, dict) and len(perm_check) > 0:
                f.write("\nPermutation check\n")
                pc_rows = [(str(k), _format_value(v)) for k, v in perm_check.items()]
                w_k = max([len("Metric")] + [len(r[0]) for r in pc_rows])
                w_v = max([len("Value")] + [len(r[1]) for r in pc_rows])
                f.write(f"{'Metric'.ljust(w_k)}  {'Value'.rjust(w_v)}\n")
                for k, v in pc_rows:
                    f.write(f"{k.ljust(w_k)}  {v.rjust(w_v)}\n")

            f.write("\n\n")
    
def save_mtx(path: Path, matrix, *, comment: str = "") -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	mmwrite(path, matrix, comment=comment)

def save_permutation_txt(path: Path, permutation: np.ndarray) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	np.savetxt(path, np.asarray(permutation, dtype=np.int64), fmt="%d")

def matrix_to_graph(A, dof_per_node: int = 1):
    """Convert a (sparse/dense) matrix into an undirected NetworkX graph.

    Minimal behavior:
    - If dof_per_node > 1, aggregate DOF blocks to node-level adjacency
    - Uses absolute values for edge weights
    - Symmetrizes by sum (A + A^T)
    - Drops diagonal/self-loops
    - Edge weights stored under attribute 'weight'
    """
    if not sp.issparse(A):
        A = sp.csr_matrix(A)
    A = A.tocsr()

    d = int(dof_per_node)
    if d > 1:
        C = A.tocoo()
        values = np.abs(C.data)
        node_row = (C.row // d).astype(int)
        node_col = (C.col // d).astype(int)
        n = A.shape[0] // d
        A = sp.coo_matrix((values, (node_row, node_col)), shape=(n, n)).tocsr()
    else:
        C = A.tocoo()
        C.data = np.abs(C.data)
        A = C.tocsr()

    A = A + A.T
    A.setdiag(0)
    A.eliminate_zeros()

    return nx.from_scipy_sparse_array(A, create_using=nx.Graph, edge_attribute='weight')
