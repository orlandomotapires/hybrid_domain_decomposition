"""Turning a sparse matrix into the weighted graph the pipeline partitions.

Kept apart from ``libs.domain_decomposition`` so that callers that only need the
graph (feature extraction, coarsening previews, tuning) do not import the quantum
partitioning backends.
"""

from __future__ import annotations

import networkx as nx
import numpy as np

from libs.runtime.utils import matrix_to_graph


def set_edge_weight_attr(G, attr_name: str) -> None:
    """Copy each edge's ``weight`` into ``attr_name`` (no-op for ``"weight"``)."""
    if attr_name == "weight":
        return
    for _, _, data in G.edges(data=True):
        data[attr_name] = data.get("weight", 1.0)


def set_node_vweight_diag(G, diag: np.ndarray, dof_per_node: int) -> bool:
    """Node weight = sum of |diagonal| over the node's rows. Falls back to uniform weights
    (rows per node) when any node's diagonal block is zero, which is common for non-FEM
    matrices. Returns True when the diagonal was used."""
    d = int(dof_per_node)
    node_diag = np.add.reduceat(np.abs(np.asarray(diag, dtype=float).ravel()), np.arange(0, len(diag), d))
    use_diag = bool(node_diag.size) and bool(np.all(node_diag > 0))
    for i in G.nodes():
        G.nodes[i]["vweight"] = float(node_diag[int(i)]) if use_diag else float(d)
    return use_diag


def build_pipeline_graph(matrix, dof_per_node: int, weight_attr: str = "weight") -> nx.Graph:
    """The same weighted graph ``decompose_matrix`` builds (node weights from |diag|)."""
    G = matrix_to_graph(matrix, dof_per_node=dof_per_node)
    set_node_vweight_diag(G, matrix.diagonal(), dof_per_node)
    set_edge_weight_attr(G, weight_attr)
    return G


def default_max_node_weight(G, k_target: int | None) -> float | None:
    """Common rule of thumb for the largest supernode: 1.5 x (total node weight / k)."""
    if k_target is None or int(k_target) <= 1:
        return None
    total = sum(float(G.nodes[u].get("vweight", 1.0)) for u in G.nodes())
    return 1.5 * total / float(int(k_target))
