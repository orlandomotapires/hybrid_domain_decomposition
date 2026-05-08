from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np


def cut_value(G: nx.Graph, part: dict[Any, int], *, edge_weight_attr: str = 'weight') -> float:
    cut = 0.0
    for u, v, data in G.edges(data=True):
        if part.get(u) != part.get(v):
            cut += float(data.get(edge_weight_attr, 1.0))
    return float(cut)


def balance_violation(
    G: nx.Graph,
    part: dict[Any, int],
    k: int,
    *,
    balance_tolerance: float,
    node_weight_attr: str = 'vweight',
) -> float:
    if k <= 1:
        return 0.0

    tol = float(balance_tolerance)
    if tol < 0.0:
        tol = 0.0
    if tol > 1.0:
        tol = tol / 100.0

    weights = np.zeros(int(k), dtype=float)
    for u in G.nodes():
        p = int(part.get(u, 0))
        if p < 0 or p >= k:
            p = 0
        wu = float(G.nodes[u].get(node_weight_attr, 1.0))
        if not np.isfinite(wu) or wu < 0.0:
            wu = 0.0
        weights[p] += wu

    total_w = float(weights.sum())
    if total_w <= 0.0:
        return 0.0
    target = total_w / float(k)
    lower = target * (1.0 - tol)
    upper = target * (1.0 + tol)

    violation = 0.0
    for block_weight in weights:
        if block_weight > upper:
            violation += (block_weight - upper)
        elif block_weight < lower:
            violation += (lower - block_weight)
    return float(violation)