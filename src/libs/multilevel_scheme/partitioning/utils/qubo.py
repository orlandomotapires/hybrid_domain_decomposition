from __future__ import annotations

from collections import defaultdict
from typing import Any

import networkx as nx
import numpy as np


def _normalized_node_and_edge_weights(
    G: nx.Graph,
    *,
    target_weight: float | None,
    node_weight_attr: str,
    edge_weight_attr: str,
) -> tuple[dict[Any, float], dict[Any, float], float, float]:
    nodes = list(G.nodes())
    raw_node_weights = {u: float(G.nodes[u].get(node_weight_attr, 1.0)) for u in nodes}
    total_node_weight = float(sum(raw_node_weights.values()))
    node_scale = total_node_weight if total_node_weight > 0.0 else 1.0
    node_weights = {u: raw_node_weights[u] / node_scale for u in nodes}

    raw_target = 0.5 * total_node_weight if target_weight is None else float(target_weight)
    target = raw_target / node_scale if node_scale > 0.0 else raw_target

    total_edge_weight = 0.0
    for _, _, data in G.edges(data=True):
        total_edge_weight += abs(float(data.get(edge_weight_attr, 1.0)))
    edge_scale = total_edge_weight if total_edge_weight > 0.0 else 1.0

    degree_weights = {u: 0.0 for u in nodes}
    for u, v, data in G.edges(data=True):
        edge_weight = float(data.get(edge_weight_attr, 1.0)) / edge_scale
        degree_weights[u] += edge_weight
        degree_weights[v] += edge_weight

    return node_weights, degree_weights, target, edge_scale


def build_qubo_from_graph(
    G: nx.Graph,
    *,
    balance_lambda: float = 1.0,
    target_weight: float | None = None,
    node_weight_attr: str = 'vweight',
    edge_weight_attr: str = 'weight',
) -> dict[tuple[Any, Any], float]:
    """Balanced 2-way cut QUBO for graph G.

    Minimize: cut(x) + λ (sum_u c_u x_u - T)^2
    where c_u is node weight and T is target_weight (default: half total node weight).

    The FEM-derived weights can span many orders of magnitude, so both node and edge
    weights are normalized to unit-scale totals before building the QUBO. This keeps
    balance_lambda numerically meaningful across datasets and coarse levels.
    """
    qubo = defaultdict(float)
    nodes = list(G.nodes())
    node_weights, degree_weights, target, edge_scale = _normalized_node_and_edge_weights(
        G,
        target_weight=target_weight,
        node_weight_attr=node_weight_attr,
        edge_weight_attr=edge_weight_attr,
    )

    for u in nodes:
        qubo[(u, u)] += degree_weights[u]
        qubo[(u, u)] += balance_lambda * (node_weights[u] ** 2)
        qubo[(u, u)] += -2.0 * balance_lambda * target * node_weights[u]

    for i, u in enumerate(nodes):
        for v in nodes[i + 1:]:
            coefficient = 2.0 * balance_lambda * node_weights[u] * node_weights[v]
            if G.has_edge(u, v):
                coefficient += -2.0 * float(G[u][v].get(edge_weight_attr, 1.0)) / edge_scale
            if coefficient:
                qubo[(u, v)] += coefficient

    return dict(qubo)


def qubo_dense_from_dict(Q: dict[tuple[Any, Any], float], nodes: list[Any]) -> np.ndarray:
    index = {u: i for i, u in enumerate(nodes)}
    size = len(nodes)
    dense_qubo = np.zeros((size, size), dtype=float)
    for (u, v), coefficient in Q.items():
        i = index[u]
        j = index[v]
        if i <= j:
            dense_qubo[i, j] += float(coefficient)
        else:
            dense_qubo[j, i] += float(coefficient)

    upper = np.triu_indices(size, 1)
    dense_qubo[upper[1], upper[0]] = dense_qubo[upper]
    return dense_qubo


def qubo_energy(Qm: np.ndarray, x: np.ndarray) -> float:
    size = int(Qm.shape[0])
    energy = 0.0
    for i in range(size):
        if x[i] == 0:
            continue
        energy += float(Qm[i, i])
        for j in range(i + 1, size):
            if x[j] == 0:
                continue
            energy += float(Qm[i, j])
    return float(energy)


def qubo_to_ising(Qm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert QUBO (x in {0,1}) to Ising (z in {+1,-1}) up to a constant."""
    size = int(Qm.shape[0])
    h = np.zeros(size, dtype=float)
    J = np.zeros((size, size), dtype=float)

    for i in range(size):
        h[i] += -0.5 * float(Qm[i, i])

    for i in range(size):
        for j in range(i + 1, size):
            q = float(Qm[i, j])
            if q == 0.0:
                continue
            J[i, j] += 0.25 * q
            h[i] += -0.25 * q
            h[j] += -0.25 * q

    return h, J