from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np


def tolerance_ratio(balance_tolerance: float) -> float:
    """``balance_tolerance`` is a percentage of the ideal part weight (2.0 = ±2%); return it as a ratio."""
    return max(0.0, float(balance_tolerance)) / 100.0


def legacy_tolerance_percent(balance_tolerance: float) -> float:
    """Percent value of a tolerance stored before it became percent-only.

    The old rule read values above 1.0 as percent and values up to 1.0 as a ratio (0.1 = 10%).
    Only use this for data written under that rule (old tuning history and studies).
    """
    value = float(balance_tolerance)
    return value * 100.0 if 0.0 <= value <= 1.0 else value


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

    tol = tolerance_ratio(balance_tolerance)

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