import networkx as nx
import neal

from .qubo_formulation import build_qubo_from_graph

def anneal_bipartition(H: nx.Graph, *, num_reads=200, balance_weight=1.0, target_weight: float | None = None, sampler=None):
    """Run simulated annealing on H’s 2-way QUBO and return part dict {node: 0|1} and best energy."""
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
    return x, best.energy

def cut_value(H: nx.Graph, part: dict, weight='weight') -> float:
    cut = 0.0
    for u, v, data in H.edges(data=True):
        if part.get(u) != part.get(v):
            cut += float(data.get(weight, 1.0))
    return cut

def recursive_kway_anneal(Gc: nx.Graph, k: int, *, balance_weight=1.0, num_reads=200, choose_by='vweight'):
    """
    Perform k-way partition on Gc by repeatedly bisecting one block using the annealer.
    Returns dict {node: label in 0..k-1} for nodes in Gc.
    """
    if k <= 1:
        return {n: 0 for n in Gc.nodes()}
    # start with one block
    blocks: dict[int, set] = {0: set(Gc.nodes())}
    next_lbl = 1

    def block_weight(ns):
        if choose_by == 'vweight' and len(ns) > 0:
            return float(sum(Gc.nodes[n].get('vweight', 1.0) for n in ns))
        return float(len(ns))

    while len(blocks) < k:
        # pick a block to split
        bid = max(blocks, key=lambda b: block_weight(blocks[b]))
        nodes = blocks.pop(bid)
        H = Gc.subgraph(nodes).copy()
        # target to split H into halves by its own weight
        T = 0.5 * sum(H.nodes[n].get('vweight', 1.0) for n in H.nodes())
        x, _ = anneal_bipartition(H, num_reads=num_reads, balance_weight=balance_weight, target_weight=T)

        A = {n for n, bit in x.items() if bit == 0}
        B = set(H.nodes()) - A
        # guard against empty sets
        if len(A) == 0 or len(B) == 0:
            # fallback: naive split
            half = len(nodes) // 2
            A = set(list(nodes)[:half])
            B = set(nodes) - A
        blocks[bid] = A
        blocks[next_lbl] = B
        next_lbl += 1

    # flatten to labels
    out = {}
    for lbl, ns in blocks.items():
        for n in ns:
            out[n] = lbl
    # remap labels to 0..k-1
    remap = {lbl: i for i, lbl in enumerate(sorted(blocks.keys()))}
    return {n: remap[lbl] for n, lbl in out.items()}

def lift_partition_to_finer(graphs: list[nx.Graph], maps: list[dict], coarse_part: dict):
    """
    Given graphs[0]=original,...,graphs[L]=coarsest and maps[l] mapping fine(node)->coarse(node) for each l,
    lift coarse_part defined on graphs[L] back to original graph’s nodes.
    """
    part = coarse_part
    # traverse maps in reverse: level L-1 down to 0
    for l in range(len(maps) - 1, -1, -1):
        fine_G = graphs[l]
        label_map = maps[l]          # fine -> coarse
        # build fine partition by pulling labels from current part via coarse id
        fine_part = {}
        for u in fine_G.nodes():
            cu = label_map[u]
            fine_part[u] = part.get(cu, 0)
        part = fine_part
    return part