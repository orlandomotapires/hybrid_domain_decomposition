import networkx as nx
import neal
import numpy as np

from collections import defaultdict

def anneal_bipartition(
    H: nx.Graph,
    *,
    num_reads=200,
    balance_weight=1.0,
    target_weight: float | None = None,
    sampler=None,
    seed: int | None = None,
    return_qubo=False,
):
    """Run simulated annealing on H's 2-way QUBO and return part dict {node: 0|1} and best energy.
    
    Args:
        H: Graph to partition
        num_reads: Number of annealing samples
        balance_weight: QUBO balance penalty weight
        target_weight: Target weight for partition 1 (default: 0.5 * total weight)
        sampler: Annealing sampler (default: SimulatedAnnealingSampler)
        return_qubo: If True, return (x, energy, Q) instead of (x, energy)
    
    Returns:
        If return_qubo=False: (partition dict, energy)
        If return_qubo=True: (partition dict, energy, QUBO matrix)
    """
    Q = build_qubo_from_graph(H, balance_weight=balance_weight, target_weight=target_weight)
    sampler = sampler or neal.SimulatedAnnealingSampler()
    # dwave-neal supports a `seed` kwarg; keep compatibility if signature differs.
    try:
        resp = sampler.sample_qubo(Q, num_reads=num_reads, seed=seed)
    except TypeError:
        resp = sampler.sample_qubo(Q, num_reads=num_reads)
    best = resp.first
    x = best.sample  # {node: 0/1}
    # normalize: ensure both labels present
    if all(bit == 0 for bit in x.values()):
        # flip a single boundary node to avoid empty part
        u0 = next(iter(x))
        x[u0] = 1
    
    if return_qubo:
        return x, best.energy, Q
    return x, best.energy

def cut_value(H: nx.Graph, part: dict, weight='weight') -> float:
    cut = 0.0
    for u, v, data in H.edges(data=True):
        if part.get(u) != part.get(v):
            cut += float(data.get(weight, 1.0))
    return cut


def _tol_to_ratio(balance_tolerance: float) -> float:
    t = float(balance_tolerance)
    if t < 0:
        return 0.0
    if t > 1.0:
        return t / 100.0
    return t


def _part_weights(G: nx.Graph, part: dict, k: int, *, node_weight_attr: str = 'vweight') -> np.ndarray:
    w = np.zeros(int(k), dtype=float)
    for u in G.nodes():
        p = int(part.get(u, 0))
        if p < 0 or p >= k:
            p = 0
        try:
            wu = float(G.nodes[u].get(node_weight_attr, 1.0))
        except Exception:
            wu = 1.0
        if not np.isfinite(wu) or wu < 0:
            wu = 0.0
        w[p] += wu
    return w


def balance_violation(G: nx.Graph, part: dict, k: int, *, balance_tolerance: float, node_weight_attr: str = 'vweight') -> float:
    """Return total violation of k-way balance bounds (0 means within bounds)."""
    if k <= 1:
        return 0.0
    tol = _tol_to_ratio(balance_tolerance)
    pw = _part_weights(G, part, k, node_weight_attr=node_weight_attr)
    total_w = float(pw.sum())
    target = total_w / float(k)
    lower = target * (1.0 - tol)
    upper = target * (1.0 + tol)

    viol = 0.0
    for wi in pw:
        if wi > upper:
            viol += float(wi - upper)
        elif wi < lower:
            viol += float(lower - wi)
    return float(viol)

def recursive_kway_anneal(
    Gc: nx.Graph,
    k: int,
    *,
    balance_weight=1.0,
    num_reads=200,
    choose_by='vweight',
    balance_tolerance=0.0,
    seed=None,
    num_starts: int = 1,
    select_balance_lambda: float = 1.0e6,
    return_first_qubo=False,
):
    """
    Perform k-way partition on Gc by repeatedly bisecting one block using the annealer.
    
    Args:
        Gc: Coarse graph to partition
        k: Number of partitions
        balance_weight: QUBO balance penalty weight
        num_reads: Number of annealing samples
        choose_by: 'vweight' or 'count' for selecting block to split
        balance_tolerance: Percentage tolerance for partition size variation (e.g., 5.0 = ±5%)
        seed: Random seed for target variation
        return_first_qubo: If True, return (partition, first_qubo_matrix, first_subgraph)
    
    Returns:
        If return_first_qubo=False: dict {node: label in 0..k-1} for nodes in Gc
        If return_first_qubo=True: (partition dict, first QUBO matrix, first subgraph)
    """
    if k <= 1:
        return {n: 0 for n in Gc.nodes()}

    def _run_once(run_seed):
        rng = np.random.default_rng(run_seed)

        # start with one block
        blocks: dict[int, set] = {0: set(Gc.nodes())}
        next_lbl = 1

        # Store first QUBO for validation if requested
        first_qubo = None
        first_subgraph = None

        def block_weight(ns):
            if choose_by == 'vweight' and len(ns) > 0:
                return float(sum(Gc.nodes[n].get('vweight', 1.0) for n in ns))
            return float(len(ns))

        split_idx = 0
        while len(blocks) < k:
            # pick a block to split
            block_id = max(blocks, key=lambda b: block_weight(blocks[b]))
            nodes = blocks.pop(block_id)
            H = Gc.subgraph(nodes).copy()

            # target to split H into halves by its own weight
            # Apply random variation within tolerance range
            total_weight = sum(H.nodes[n].get('vweight', 1.0) for n in H.nodes())
            base_target = 0.5 * total_weight

            if balance_tolerance > 0:
                # Allow target to vary by ±balance_tolerance%
                variation_range = (_tol_to_ratio(balance_tolerance)) * total_weight
                target_variation = rng.uniform(-variation_range, variation_range)
                T = base_target + target_variation
                # Clamp to reasonable bounds (at least 10% and at most 90% of total)
                T = max(0.1 * total_weight, min(0.9 * total_weight, T))
            else:
                T = base_target

            split_seed = None
            if run_seed is not None:
                split_seed = int(run_seed) + int(split_idx)
            split_idx += 1

            # Capture first QUBO for validation
            if return_first_qubo and first_qubo is None:
                x, _, Q = anneal_bipartition(
                    H,
                    num_reads=num_reads,
                    balance_weight=balance_weight,
                    target_weight=T,
                    seed=split_seed,
                    return_qubo=True,
                )
                first_qubo = Q
                first_subgraph = H
            else:
                x, _ = anneal_bipartition(
                    H,
                    num_reads=num_reads,
                    balance_weight=balance_weight,
                    target_weight=T,
                    seed=split_seed,
                )

            A = {n for n, bit in x.items() if bit == 0}  # First partition
            B = set(H.nodes()) - A  # Second partition

            # guard against empty sets
            if len(A) == 0 or len(B) == 0:
                # fallback: naive split
                half = len(nodes) // 2
                A = set(list(nodes)[:half])
                B = set(nodes) - A
            blocks[block_id] = A
            blocks[next_lbl] = B
            next_lbl += 1

        # flatten to labels
        out = {}
        for lbl, ns in blocks.items():
            for n in ns:
                out[n] = lbl
        # remap labels to 0..k-1
        remap = {lbl: i for i, lbl in enumerate(sorted(blocks.keys()))}
        partition = {n: remap[lbl] for n, lbl in out.items()}

        if return_first_qubo:
            return partition, first_qubo, first_subgraph
        return partition

    starts = max(1, int(num_starts))
    best_partition = None
    best_first_qubo = None
    best_first_subgraph = None
    best_score = None

    for i in range(starts):
        run_seed = seed
        if seed is not None:
            run_seed = int(seed) + int(i)

        if return_first_qubo:
            part_i, q_i, h_i = _run_once(run_seed)
        else:
            part_i = _run_once(run_seed)
            q_i, h_i = None, None

        cut_i = float(cut_value(Gc, part_i, weight='weight'))
        viol_i = float(balance_violation(Gc, part_i, k, balance_tolerance=balance_tolerance, node_weight_attr='vweight'))
        score_i = cut_i + float(select_balance_lambda) * viol_i

        if best_score is None or score_i < best_score:
            best_score = score_i
            best_partition = part_i
            best_first_qubo = q_i
            best_first_subgraph = h_i

    if return_first_qubo:
        return best_partition, best_first_qubo, best_first_subgraph
    return best_partition

def build_qubo_from_graph(H: nx.Graph, *, balance_weight: float = 1.0, target_weight: float | None = None):
    """
    QUBO for balanced 2-way cut on subgraph H.
    Minimize: sum_{(u,v)∈E} w_uv * [x_u + x_v - 2 x_u x_v] + λ (sum_u c_u x_u - T)^2
    where c_u = node weight (vweight), T = target_weight (default = 0.5 * sum c_u).
    Returns Q (dict[(u,v)] -> coeff) upper-triangular including diagonals.
    """
    Q = defaultdict(float)
    nodes = list(H.nodes())
    c = {u: float(H.nodes[u].get('vweight', 1.0)) for u in nodes}
    Ctot = float(sum(c.values()))
    T = Ctot * 0.5 if target_weight is None else float(target_weight)

    # Edge XOR linear terms: + deg_w(u) * x_u
    degw = {u: 0.0 for u in nodes}
    for u, v, data in H.edges(data=True):
        w = float(data.get('weight', 1.0))
        degw[u] += w
        degw[v] += w

    # Diagonal: edge linear + balance diag: λ c_u^2
    for u in nodes:
        Q[(u, u)] += degw[u]
        Q[(u, u)] += balance_weight * (c[u] ** 2)
        # Linear from balance: -2 λ T c_u
        Q[(u, u)] += -2.0 * balance_weight * T * c[u] # THIS IS WRONG AT THE QUBO FORMULATION PDF, HERE IS CORRECTED

    # Off-diagonals:
    # Balance dense term: + 2 λ c_u c_v
    # Edge XOR quad term: -2 w_uv if edge exists
    # We add only for u < v (upper triangle)
    for i in range(len(nodes)):
        u = nodes[i]
        for j in range(i + 1, len(nodes)):
            v = nodes[j]
            coef = 2.0 * balance_weight * c[u] * c[v]
            if H.has_edge(u, v):
                coef += -2.0 * float(H[u][v].get('weight', 1.0))
            if coef != 0.0:
                Q[(u, v)] += coef

    return dict(Q)