from __future__ import annotations

import heapq
import math
from typing import Any, Dict, Iterable, Tuple

import networkx as nx
import numpy as np


def _tol_to_ratio(balance_tolerance: float) -> float:
    """Convert tolerance to a ratio.

    Convention:
    - If balance_tolerance > 1.0, treat as percent (e.g., 5.0 => 0.05).
    - Else treat as already a ratio (e.g., 0.05 => 0.05).
    """
    t = float(balance_tolerance)
    if t < 0:
        return 0.0
    if t > 1.0:
        return t / 100.0
    return t


def _node_weight(G: nx.Graph, u: Any, node_weight_attr: str) -> float:
    w = G.nodes[u].get(node_weight_attr, 1.0)
    try:
        wf = float(w)
    except Exception:
        wf = 1.0
    if not math.isfinite(wf):
        wf = 1.0
    # Negative weights break balance accounting; clamp at 0.
    return max(0.0, wf)


def _edge_weight(data: Dict[str, Any], weight_attr: str) -> float:
    w = data.get(weight_attr, 1.0)
    try:
        wf = float(w)
    except Exception:
        wf = 1.0
    if not math.isfinite(wf):
        wf = 1.0
    return wf


def _compute_part_weights(
    G: nx.Graph,
    part: Dict[Any, int],
    k: int,
    node_weight_attr: str,
) -> np.ndarray:
    weights = np.zeros(int(k), dtype=float)
    for u in G.nodes():
        p = int(part.get(u, 0))
        if p < 0 or p >= k:
            p = 0
            part[u] = 0
        weights[p] += _node_weight(G, u, node_weight_attr)
    return weights


def _boundary_nodes(G: nx.Graph, part: Dict[Any, int]) -> list[Any]:
    boundary: list[Any] = []
    for u in G.nodes():
        pu = part.get(u, 0)
        for v in G.neighbors(u):
            if part.get(v, 0) != pu:
                boundary.append(u)
                break
    return boundary


def refine_kway_boundary_moves(
    G: nx.Graph,
    part: Dict[Any, int],
    *,
    k: int,
    balance_tolerance: float,
    weight_attr: str = "weight",
    node_weight_attr: str = "vweight",
    objective: str = "cut",
    balance_lambda: float = 1.0,
    max_passes: int = 5,
    max_moves_per_pass: int | None = None,
    seed: int | None = 42,
) -> Dict[Any, int]:
    """Refine a k-way partition using greedy boundary node moves.

    This is a lightweight METIS-style idea: move boundary nodes to neighbor parts
    when it improves the objective and preserves balance constraints.

    Balance is defined using node weights stored in node attribute `node_weight_attr`
    (default: 'vweight').
    """
    if k <= 1:
        return {u: 0 for u in G.nodes()}

    obj = (objective or "cut").strip().lower()
    tol = _tol_to_ratio(balance_tolerance)

    part = dict(part)
    part_weights = _compute_part_weights(G, part, k, node_weight_attr)
    total_w = float(part_weights.sum())
    target = total_w / float(k) if k > 0 else total_w
    lower = target * (1.0 - tol)
    upper = target * (1.0 + tol)

    rng = np.random.default_rng(seed)

    def balance_penalty_delta(a: int, b: int, wu: float) -> float:
        if obj != "cut_balance":
            return 0.0
        wa0, wb0 = float(part_weights[a]), float(part_weights[b])
        wa1, wb1 = wa0 - wu, wb0 + wu
        # squared deviation from target (only for the two touched parts)
        before = (wa0 - target) ** 2 + (wb0 - target) ** 2
        after = (wa1 - target) ** 2 + (wb1 - target) ** 2
        return after - before

    for _pass in range(max(0, int(max_passes))):
        moved = 0
        boundary = _boundary_nodes(G, part)
        if not boundary:
            break
        rng.shuffle(boundary)

        for u in boundary:
            a = int(part.get(u, 0))
            wu = _node_weight(G, u, node_weight_attr)

            # Candidate target parts: only parts present in u's neighborhood.
            conn: Dict[int, float] = {}
            neighbor_parts: set[int] = set()
            for v, data in G[u].items():
                pv = int(part.get(v, 0))
                neighbor_parts.add(pv)
                wuv = _edge_weight(data, weight_attr)
                conn[pv] = conn.get(pv, 0.0) + wuv

            if len(neighbor_parts) <= 1:
                continue
            conn_a = conn.get(a, 0.0)

            best_b: int | None = None
            best_score = 0.0

            for b in neighbor_parts:
                if b == a:
                    continue
                # Hard balance bounds (node-weight based)
                if part_weights[a] - wu < lower:
                    continue
                if part_weights[b] + wu > upper:
                    continue

                gain = conn.get(b, 0.0) - conn_a
                score = gain - float(balance_lambda) * balance_penalty_delta(a, b, wu)

                if obj == "cut":
                    # Strict: only accept moves that reduce cut.
                    if gain <= 0:
                        continue
                else:
                    # Trade-off objective: accept if overall score improves.
                    if score <= 0:
                        continue
                if score > best_score:
                    best_score = score
                    best_b = int(b)

            if best_b is None:
                continue

            # Apply move
            part[u] = best_b
            part_weights[a] -= wu
            part_weights[best_b] += wu
            moved += 1

            if max_moves_per_pass is not None and moved >= int(max_moves_per_pass):
                break

        if moved == 0:
            break

    return part


def refine_kway_fm(
    G: nx.Graph,
    part: Dict[Any, int],
    *,
    k: int,
    balance_tolerance: float,
    weight_attr: str = "weight",
    node_weight_attr: str = "vweight",
    objective: str = "cut",
    balance_lambda: float = 1.0,
    max_passes: int = 10,
    max_moves_per_pass: int | None = 5000,
    seed: int | None = 42,
) -> Dict[Any, int]:
    """FM-like k-way refinement.

    - Uses a priority queue of candidate node moves (boundary moves by default)
    - Locks each node at most once per pass
    - Tracks best-prefix cumulative improvement and rolls back moves after the best point

    Balance constraints are hard bounds based on `node_weight_attr` and `balance_tolerance`.
    """
    if k <= 1:
        return {u: 0 for u in G.nodes()}

    obj = (objective or "cut").strip().lower()
    tol = _tol_to_ratio(balance_tolerance)

    part = dict(part)
    part_weights = _compute_part_weights(G, part, k, node_weight_attr)
    total_w = float(part_weights.sum())
    target = total_w / float(k) if k > 0 else total_w
    lower = target * (1.0 - tol)
    upper = target * (1.0 + tol)

    rng = np.random.default_rng(seed)

    def balance_penalty_delta(a: int, b: int, wu: float) -> float:
        if obj != "cut_balance":
            return 0.0
        wa0, wb0 = float(part_weights[a]), float(part_weights[b])
        wa1, wb1 = wa0 - wu, wb0 + wu
        before = (wa0 - target) ** 2 + (wb0 - target) ** 2
        after = (wa1 - target) ** 2 + (wb1 - target) ** 2
        return after - before

    def best_move_for(u: Any) -> tuple[float, int, int, float] | None:
        a = int(part.get(u, 0))
        wu = _node_weight(G, u, node_weight_attr)

        # Candidate targets: neighbor parts.
        conn: Dict[int, float] = {}
        neighbor_parts: set[int] = set()
        for v, data in G[u].items():
            pv = int(part.get(v, 0))
            neighbor_parts.add(pv)
            wuv = _edge_weight(data, weight_attr)
            conn[pv] = conn.get(pv, 0.0) + wuv

        if len(neighbor_parts) <= 1:
            return None

        conn_a = conn.get(a, 0.0)
        best_b: int | None = None
        best_score = 0.0

        for b in neighbor_parts:
            if b == a:
                continue
            if part_weights[a] - wu < lower:
                continue
            if part_weights[b] + wu > upper:
                continue

            gain = conn.get(b, 0.0) - conn_a
            score = gain - float(balance_lambda) * balance_penalty_delta(a, int(b), wu)

            if obj == "cut":
                if gain <= 0:
                    continue
                score = gain
            else:
                if score <= 0:
                    continue

            if score > best_score:
                best_score = float(score)
                best_b = int(b)

        if best_b is None:
            return None
        return float(best_score), a, int(best_b), float(wu)

    for _pass in range(max(0, int(max_passes))):
        locked: set[Any] = set()
        move_stack: list[tuple[Any, int, int, float, float]] = []
        cumulative = 0.0
        best_cum = 0.0
        best_idx = -1

        boundary = _boundary_nodes(G, part)
        if not boundary:
            break
        rng.shuffle(boundary)

        pq: list[tuple[float, float, Any, int, int]] = []
        for u in boundary:
            mv = best_move_for(u)
            if mv is None:
                continue
            score, a, b, _wu = mv
            heapq.heappush(pq, (-score, float(rng.random()), u, a, b))

        moves = 0
        while pq:
            if max_moves_per_pass is not None and moves >= int(max_moves_per_pass):
                break

            neg_score, _tie, u, a0, b0 = heapq.heappop(pq)
            if u in locked:
                continue

            a_cur = int(part.get(u, 0))
            if a_cur != int(a0):
                # stale; recompute
                mv = best_move_for(u)
                if mv is not None:
                    score, a, b, _wu = mv
                    heapq.heappush(pq, (-score, float(rng.random()), u, a, b))
                continue

            mv = best_move_for(u)
            if mv is None:
                continue
            score, a, b, wu = mv
            if a != a_cur:
                continue

            # Apply move
            part[u] = b
            part_weights[a] -= wu
            part_weights[b] += wu
            locked.add(u)
            moves += 1

            cumulative += float(score)
            move_stack.append((u, a, b, wu, float(score)))
            if cumulative > best_cum:
                best_cum = cumulative
                best_idx = len(move_stack) - 1

            # Update neighbor candidates lazily.
            for v in G.neighbors(u):
                if v in locked:
                    continue
                mv_v = best_move_for(v)
                if mv_v is None:
                    continue
                s_v, a_v, b_v, _wu_v = mv_v
                heapq.heappush(pq, (-s_v, float(rng.random()), v, a_v, b_v))

        # Roll back moves after best prefix.
        if best_idx < 0:
            break

        for i in range(len(move_stack) - 1, best_idx, -1):
            u, a, b, wu, _sc = move_stack[i]
            if int(part.get(u, a)) != int(b):
                continue
            part[u] = a
            part_weights[a] += wu
            part_weights[b] -= wu

    return part


def uncoarsen_and_refine(
    graphs: list[nx.Graph],
    maps: list[dict],
    coarse_part: dict,
    *,
    k: int,
    balance_tolerance: float,
    weight_attr: str = "weight",
    node_weight_attr: str = "vweight",
    refine_objective: str = "cut",
    refine_balance_lambda: float = 1.0,
    refine_method: str = "greedy",
    max_passes_per_level: int = 5,
    max_moves_per_pass: int | None = None,
    seed: int | None = 42,
) -> dict:
    """Uncoarsen a coarse partition back to the original graph with per-level refinement."""
    if not graphs:
        return {}

    part = dict(coarse_part)
    # Traverse maps in reverse: level L-1 down to 0
    for l in range(len(maps) - 1, -1, -1):
        fine_G = graphs[l]
        label_map = maps[l]  # fine -> coarse

        fine_part: Dict[Any, int] = {}
        for u in fine_G.nodes():
            cu = label_map[u]
            fine_part[u] = int(part.get(cu, 0))

        method = (refine_method or "greedy").strip().lower()
        if method == "fm":
            fine_part = refine_kway_fm(
                fine_G,
                fine_part,
                k=k,
                balance_tolerance=balance_tolerance,
                weight_attr=weight_attr,
                node_weight_attr=node_weight_attr,
                objective=refine_objective,
                balance_lambda=refine_balance_lambda,
                max_passes=max_passes_per_level,
                max_moves_per_pass=max_moves_per_pass,
                seed=seed,
            )
        elif method == "greedy":
            fine_part = refine_kway_boundary_moves(
                fine_G,
                fine_part,
                k=k,
                balance_tolerance=balance_tolerance,
                weight_attr=weight_attr,
                node_weight_attr=node_weight_attr,
                objective=refine_objective,
                balance_lambda=refine_balance_lambda,
                max_passes=max_passes_per_level,
                max_moves_per_pass=max_moves_per_pass,
                seed=seed,
            )
        else:
            raise ValueError("Unknown refine_method. Use one of: fm, greedy")

        part = fine_part

    return part


def uncoarsening(graphs: list[nx.Graph], maps: list[dict], coarse_part: dict):
    """Backwards-compatible alias: pure lifting with no refinement."""
    part = coarse_part
    for l in range(len(maps) - 1, -1, -1):
        fine_G = graphs[l]
        label_map = maps[l]
        fine_part = {}
        for u in fine_G.nodes():
            cu = label_map[u]
            fine_part[u] = part.get(cu, 0)
        part = fine_part
    return part