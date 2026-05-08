from __future__ import annotations

from typing import Any, Callable

import networkx as nx
import numpy as np

from .metrics import balance_violation, cut_value


def _normalized_partition_score(
    Gc: nx.Graph,
    part: dict[Any, int],
    *,
    k: int,
    balance_tolerance: float,
    balance_violation_lambda: float,
) -> float:
    cut_i = cut_value(Gc, part, edge_weight_attr='weight')
    violation_i = balance_violation(
        Gc,
        part,
        int(k),
        balance_tolerance=balance_tolerance,
        node_weight_attr='vweight',
    )

    total_edge_weight = float(
        sum(float(data.get('weight', 1.0)) for _, _, data in Gc.edges(data=True))
    )
    total_node_weight = float(
        sum(float(Gc.nodes[node].get('vweight', 1.0)) for node in Gc.nodes())
    )

    normalized_cut = float(cut_i) / max(total_edge_weight, 1.0)
    normalized_violation = float(violation_i) / max(total_node_weight, 1.0)
    return normalized_cut + float(balance_violation_lambda) * normalized_violation


def choose_target_weight(
    total_weight: float,
    *,
    balance_tolerance: float,
    rng: np.random.Generator,
) -> float:
    target = 0.5 * float(total_weight)
    if total_weight <= 0.0:
        return 0.0
    if not balance_tolerance:
        return float(target)

    tol = float(balance_tolerance)
    if tol > 1.0:
        tol = tol / 100.0
    tol = max(0.0, tol)
    delta = rng.uniform(-tol, tol) * float(total_weight)
    return float(np.clip(target + delta, 0.1 * total_weight, 0.9 * total_weight))


def recursive_kway_via_bipartition(
    Gc: nx.Graph,
    k: int,
    *,
    weight: str,
    balance_tolerance: float,
    seed: int | None,
    num_starts: int,
    balance_violation_lambda: float,
    bipartition: Callable[[nx.Graph, float, int | None, bool], dict[Any, int]],
    simulated: bool,
) -> dict[Any, int]:
    """Build a k-way partition by repeatedly splitting the heaviest current block."""
    if k <= 1:
        return {n: 0 for n in Gc.nodes()}

    nodes_all = list(Gc.nodes())
    if not nodes_all:
        return {}
    k = min(int(k), len(nodes_all))

    def block_weight(nodes: set[Any]) -> float:
        if weight == 'vweight':
            return float(sum(float(Gc.nodes[n].get('vweight', 1.0)) for n in nodes))
        return float(len(nodes))

    def run_once(run_seed: int | None) -> dict[Any, int]:
        rng = np.random.default_rng(run_seed)
        blocks: list[set[Any]] = [set(nodes_all)]
        split_idx = 0

        while len(blocks) < int(k):
            idx = max(range(len(blocks)), key=lambda i: block_weight(blocks[i]))
            nodes = blocks[idx]
            G = Gc.subgraph(nodes).copy()

            total_weight = float(sum(float(G.nodes[n].get('vweight', 1.0)) for n in G.nodes()))
            target_weight = choose_target_weight(
                total_weight,
                balance_tolerance=balance_tolerance,
                rng=rng,
            )

            split_seed = None if run_seed is None else int(run_seed) + int(split_idx)
            split_idx += 1

            x = bipartition(G, target_weight, split_seed, simulated=simulated)

            part_a = {n for n, bit in x.items() if int(bit) == 0}
            part_b = set(G.nodes()) - part_a
            if not part_a or not part_b:
                half = max(1, len(nodes) // 2)
                ordered = list(nodes)
                part_a = set(ordered[:half])
                part_b = set(ordered[half:])

            if not part_a or not part_b:
                raise RuntimeError("Bipartition fallback failed: produced an empty side")

            blocks[idx] = part_a
            blocks.append(part_b)

        part: dict[Any, int] = {}
        for label, nodes in enumerate(blocks):
            for node in nodes:
                part[node] = int(label)

        if set(part.keys()) != set(nodes_all):
            raise RuntimeError("Partition does not cover all nodes")

        return part

    starts = max(1, int(num_starts))
    best_score = None
    best_part = None

    for i in range(starts):
        run_seed = None if seed is None else int(seed) + int(i)
        part_i = run_once(run_seed)

        score_i = _normalized_partition_score(
            Gc,
            part_i,
            k=int(k),
            balance_tolerance=balance_tolerance,
            balance_violation_lambda=balance_violation_lambda,
        )

        if best_score is None or score_i < best_score:
            best_score = score_i
            best_part = part_i

    return best_part