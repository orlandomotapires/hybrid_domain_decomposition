import networkx as nx
import neal
import numpy as np

from collections import defaultdict
import networkx as nx

def anneal_bipartition(H: nx.Graph, *, num_reads=200, balance_weight=1.0, target_weight: float | None = None, sampler=None, return_qubo=False):
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

def recursive_kway_anneal(Gc: nx.Graph, k: int, *, balance_weight=1.0, num_reads=200, choose_by='vweight', balance_tolerance=0.0, seed=None, return_first_qubo=False):
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
    
    rng = np.random.default_rng(seed)
    
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
            # Example: tolerance=5 means target can be 0.475 to 0.525 of total weight
            variation_range = (balance_tolerance / 100.0) * total_weight
            target_variation = rng.uniform(-variation_range, variation_range)
            T = base_target + target_variation
            # Clamp to reasonable bounds (at least 10% and at most 90% of total)
            T = max(0.1 * total_weight, min(0.9 * total_weight, T))
        else:
            T = base_target
        
        # Capture first QUBO for validation
        if return_first_qubo and first_qubo is None:
            x, _, Q = anneal_bipartition(H, num_reads=num_reads, balance_weight=balance_weight, target_weight=T, return_qubo=True)
            first_qubo = Q
            first_subgraph = H
        else:
            x, _ = anneal_bipartition(H, num_reads=num_reads, balance_weight=balance_weight, target_weight=T)

        A = {n for n, bit in x.items() if bit == 0} # First partition
        B = set(H.nodes()) - A # Second partition

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