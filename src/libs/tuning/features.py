"""Cheap structural features of a library matrix, cached in ``matrices/<id>/features.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from scipy import sparse

from libs.profiling.matrix_metrics import _sparsity_metrics
from libs.runtime.atomic import atomic_write_json
from libs.runtime.matrix_library import load_matrix_meta
from libs.graph_prep import build_pipeline_graph  # noqa: F401  (re-exported)
from libs.runtime.utils import load_mtx

FEATURES_FILE = "features.json"
FEATURES_VERSION = 1


def _matrix_features(A) -> dict[str, Any]:
    A = A.tocsr() if sparse.issparse(A) else sparse.csr_matrix(A)
    n = int(A.shape[0])
    s = _sparsity_metrics(A, band=200, percent_bands=(1.0,))
    pattern = A.copy()
    pattern.data = np.ones_like(pattern.data)
    pattern_asym = abs(pattern - pattern.T)
    diff = abs(A - A.T)
    absA = abs(A)
    diag = np.abs(A.diagonal())
    offdiag_rowsum = np.asarray(absA.sum(axis=1)).ravel() - diag
    max_abs = float(absA.max()) if A.nnz else 0.0
    return {
        "n": n,
        "nnz": int(A.nnz),
        "density": float(A.nnz) / float(n * n) if n else 0.0,
        "nnz_per_row": float(A.nnz) / float(n) if n else 0.0,
        "bandwidth": int(s["bandwidth"]),
        "avg_bandwidth": float(s["avg_bandwidth"]),
        "relative_bandwidth": float(s["bandwidth"]) / float(n) if n else 0.0,
        "pattern_symmetric": bool(pattern_asym.nnz == 0),
        "numeric_symmetric": bool(diff.nnz == 0 or float(diff.max()) <= 1e-12 * max(max_abs, 1.0)),
        "zero_diagonal_rows": int(np.count_nonzero(diag == 0)),
        "diag_dominant_fraction": float(np.mean(diag >= offdiag_rowsum)) if n else 0.0,
        "diag_to_offdiag_ratio": float(diag.sum() / offdiag_rowsum.sum()) if offdiag_rowsum.sum() > 0 else float("inf"),
    }


def _graph_features(G: nx.Graph) -> dict[str, Any]:
    degrees = np.array([d for _, d in G.degree()], dtype=float)
    vweights = np.array([float(G.nodes[u].get("vweight", 1.0)) for u in G.nodes()], dtype=float)
    eweights = np.array([float(d.get("weight", 1.0)) for _, _, d in G.edges(data=True)], dtype=float)
    components = nx.number_connected_components(G) if G.number_of_nodes() else 0
    return {
        "nodes": int(G.number_of_nodes()),
        "edges": int(G.number_of_edges()),
        "degree_mean": float(degrees.mean()) if degrees.size else 0.0,
        "degree_max": int(degrees.max()) if degrees.size else 0,
        "degree_std": float(degrees.std()) if degrees.size else 0.0,
        "connected_components": int(components),
        "vweight_cv": float(vweights.std() / vweights.mean()) if vweights.size and vweights.mean() > 0 else 0.0,
        "eweight_cv": float(eweights.std() / eweights.mean()) if eweights.size and eweights.mean() > 0 else 0.0,
    }


def candidate_dof_per_node(n: int) -> list[int]:
    return [d for d in (1, 2, 3, 6) if n % d == 0]


def compute_matrix_features(matrix_id: str, dof_per_node: int = 1, *, use_cache: bool = True) -> dict[str, Any]:
    """Features of ``matrix_id`` for a given block size, cached next to the matrix.

    The cache is keyed by the .mtx size/mtime and ``dof_per_node`` so it refreshes when the
    matrix file changes.
    """
    meta = load_matrix_meta(matrix_id)
    mtx_path: Path = meta["dir"] / meta["file"]
    stat = mtx_path.stat()
    signature = {"size": stat.st_size, "mtime": int(stat.st_mtime), "version": FEATURES_VERSION}
    cache_path: Path = meta["dir"] / FEATURES_FILE
    cache: dict[str, Any] = {}
    if use_cache and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    if cache.get("signature") != signature:
        cache = {"signature": signature, "matrix": None, "graph": {}}

    key = str(int(dof_per_node))
    if use_cache and cache.get("matrix") and key in cache.get("graph", {}):
        return _assemble(matrix_id, cache, key)

    A = load_mtx(str(mtx_path), matrix_id)
    if cache.get("matrix") is None:
        cache["matrix"] = _matrix_features(A)
    if A.shape[0] % int(dof_per_node) != 0:
        raise ValueError(f"Matrix size {A.shape[0]} is not divisible by dof_per_node={dof_per_node}")
    cache.setdefault("graph", {})[key] = _graph_features(build_pipeline_graph(A, int(dof_per_node)))
    try:
        atomic_write_json(cache_path, cache)
    except OSError:
        pass
    return _assemble(matrix_id, cache, key)


def _assemble(matrix_id: str, cache: dict[str, Any], key: str) -> dict[str, Any]:
    matrix = cache["matrix"]
    return {
        "matrix_id": matrix_id,
        "dof_per_node": int(key),
        "matrix": matrix,
        "graph": cache["graph"][key],
        "valid_dof_per_node": candidate_dof_per_node(int(matrix["n"])),
    }


def feature_vector(features: dict[str, Any]) -> np.ndarray:
    """Scale-free numeric summary used to compare matrices (history kNN)."""
    m, g = features["matrix"], features["graph"]
    return np.array(
        [
            np.log10(max(m["n"], 1)),
            np.log10(max(m["nnz_per_row"], 1e-9)),
            m["relative_bandwidth"],
            float(m["pattern_symmetric"]),
            m["diag_dominant_fraction"],
            np.log10(max(g["degree_mean"], 1e-9)),
            g["degree_std"] / max(g["degree_mean"], 1e-9),
            g["vweight_cv"],
        ],
        dtype=float,
    )
