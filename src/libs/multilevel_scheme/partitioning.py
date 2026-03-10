from __future__ import annotations
import neal
import numpy as np
from collections import defaultdict
from typing import Any, Dict, List
import networkx as nx
from libs.log import info
import pymetis

def partition_graph_metis(
    G: nx.Graph,
    nparts: int = 2,
) -> Dict[Any, int]:
    
    nodes = list(G.nodes())
    index = {u: i for i, u in enumerate(nodes)}
    adjacency: List[List[int]] = [[index[v] for v in G.neighbors(u)] for u in nodes]

    info(f"nparts={nparts}, |V|={len(nodes)}, |E|={G.number_of_edges()}")
    _, membership = pymetis.part_graph(nparts, adjacency=adjacency)
    return {nodes[i]: int(membership[i]) for i in range(len(nodes))}

def build_qubo_from_graph(
    H: nx.Graph,
    *,
    balance_lambda: float = 1.0,
    target_weight: float | None = None,
    node_weight_attr: str = 'vweight',
    edge_weight_attr: str = 'weight',
):
    """Balanced 2-way cut QUBO for graph H.

    Minimize: cut(x) + λ (sum_u c_u x_u - T)^2
    where c_u is node weight and T is target_weight (default: half total node weight).
    """
    Q = defaultdict(float)
    nodes = list(H.nodes())
    c = {u: float(H.nodes[u].get(node_weight_attr, 1.0)) for u in nodes}
    total_c = float(sum(c.values()))
    T = 0.5 * total_c if target_weight is None else float(target_weight)

    # Precompute degree-based weights for linear terms
    degw = {u: 0.0 for u in nodes}
    for u, v, data in H.edges(data=True):
        w = float(data.get(edge_weight_attr, 1.0))
        degw[u] += w
        degw[v] += w

    # Linear Terms: cut contribution + balance contribution
    for u in nodes:
        Q[(u, u)] += degw[u]
        Q[(u, u)] += balance_lambda * (c[u] ** 2)
        Q[(u, u)] += -2.0 * balance_lambda * T * c[u]

    # Quadratic Terms: cut contribution + balance contribution
    for i, u in enumerate(nodes):
        for v in nodes[i + 1:]:
            coef = 2.0 * balance_lambda * c[u] * c[v]
            if H.has_edge(u, v):
                coef += -2.0 * float(H[u][v].get(edge_weight_attr, 1.0))
            if coef:
                Q[(u, v)] += coef

    return dict(Q)

def anneal_bipartition(
    H: nx.Graph,
    *,
    num_reads: int = 200,
    balance_lambda: float = 1.0,
    target_weight: float | None = None,
    seed: int | None = None,
    return_qubo: bool = False,
):
    Q = build_qubo_from_graph(H, balance_lambda=balance_lambda, target_weight=target_weight)
    sampler = neal.SimulatedAnnealingSampler()
    try:
        resp = sampler.sample_qubo(Q, num_reads=int(num_reads), seed=seed)
    except TypeError:
        resp = sampler.sample_qubo(Q, num_reads=int(num_reads))

    best = resp.first
    x = dict(best.sample)
    if x and all(bit == 0 for bit in x.values()):
        x[next(iter(x))] = 1

    if return_qubo:
        return x, float(best.energy), Q
    return x, float(best.energy)


def _cut_value(G: nx.Graph, part: dict, *, edge_weight_attr: str = 'weight') -> float:
    cut = 0.0
    for u, v, data in G.edges(data=True):
        if part.get(u) != part.get(v):
            cut += float(data.get(edge_weight_attr, 1.0))
    return float(cut)


def _balance_violation(
    G: nx.Graph,
    part: dict,
    k: int,
    *,
    balance_tolerance: float,
    node_weight_attr: str = 'vweight',
):
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

    viol = 0.0
    for wi in weights:
        if wi > upper:
            viol += (wi - upper)
        elif wi < lower:
            viol += (lower - wi)
    return float(viol)

def recursive_kway_anneal(
    Gc: nx.Graph,
    k: int,
    *,
    balance_lambda: float = 1.0,
    num_reads: int = 200,
    choose_by: str = 'vweight',
    balance_tolerance: float = 0.0,
    seed: int | None = None,
    num_starts: int = 1,
    select_balance_lambda: float = 1.0e6,
):
    if k <= 1:
        return {n: 0 for n in Gc.nodes()}

    nodes_all = list(Gc.nodes())
    if not nodes_all:
        return {}

    def block_weight(ns: set) -> float:
        if choose_by == 'vweight':
            return float(sum(float(Gc.nodes[n].get('vweight', 1.0)) for n in ns))
        return float(len(ns))

    def run_once(run_seed: int | None):
        rng = np.random.default_rng(run_seed)
        blocks: list[set] = [set(nodes_all)]
        split_idx = 0

        while len(blocks) < int(k):
            idx = max(range(len(blocks)), key=lambda i: block_weight(blocks[i]))
            nodes = blocks[idx]
            H = Gc.subgraph(nodes).copy()

            total_weight = float(sum(float(H.nodes[n].get('vweight', 1.0)) for n in H.nodes()))
            T = 0.5 * total_weight
            if balance_tolerance and total_weight > 0.0:
                tol = float(balance_tolerance)
                if tol > 1.0:
                    tol = tol / 100.0
                tol = max(0.0, tol)
                delta = rng.uniform(-tol, tol) * total_weight
                T = float(np.clip(T + delta, 0.1 * total_weight, 0.9 * total_weight))

            split_seed = None if run_seed is None else int(run_seed) + int(split_idx)
            split_idx += 1

            x, _ = anneal_bipartition(
                H,
                num_reads=num_reads,
                balance_lambda=balance_lambda,
                target_weight=T,
                seed=split_seed,
            )

            A = {n for n, bit in x.items() if bit == 0}
            B = set(H.nodes()) - A
            if not A or not B:
                half = max(1, len(nodes) // 2)
                ordered = list(nodes)
                A = set(ordered[:half])
                B = set(ordered[half:])

            blocks[idx] = A
            blocks.append(B)

        part = {}
        for lbl, ns in enumerate(blocks):
            for n in ns:
                part[n] = lbl

        return part

    starts = max(1, int(num_starts))
    best_score = None
    best_part = None

    for i in range(starts):
        run_seed = None if seed is None else int(seed) + int(i)
        part_i = run_once(run_seed)

        cut_i = _cut_value(Gc, part_i, edge_weight_attr='weight')
        viol_i = _balance_violation(
            Gc,
            part_i,
            int(k),
            balance_tolerance=balance_tolerance,
            node_weight_attr='vweight',
        )
        score_i = float(cut_i) + float(select_balance_lambda) * float(viol_i)

        if best_score is None or score_i < best_score:
            best_score = score_i
            best_part = part_i

    return best_part