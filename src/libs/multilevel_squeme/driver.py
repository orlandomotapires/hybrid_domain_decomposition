import networkx as nx
from .coarsening import coarsen_graph
from .partitioning import initial_partition_gggp, initial_partition_spectral, initial_partition_component_aware
from .refinement import refine_partition_fm, refine_partition_kl, edge_cut, rebalance_partition


def project_partition(fine_G: nx.Graph, coarse_label: dict, coarse_part: dict):
    part = {}
    for u in fine_G.nodes():
        cu = coarse_label[u]
        part[u] = coarse_part.get(cu, 0)
    return part


def multilevel_bipartition(
    G: nx.Graph,
    weight: str = "weight",
    coarsen_limit: int = 80,
    max_levels: int = 20,
    seed: int | None = None,
    balance_tol: float = 0.03,
    refine_method: str = "FM",
    refine_passes: int = 3,
    n_trials: int = 8,
    initial_method: str = "GGGP",
):
    """
    Multilevel bipartitioning pipeline with multi-start and multi-pass refinement:
      - Coarsen until node count <= coarsen_limit or levels exhausted
      - Initial partition on coarsest via GGGP (multi-start over seeds)
      - Uncoarsen and refine at each level using FM (default) or KL, for several passes
    Returns: partition dict {node: 0|1}
    """

    def run_once(trial_seed: int | None):
        graphs = [G]
        maps: list[dict] = []

        while graphs[-1].number_of_nodes() > coarsen_limit and len(graphs) < max_levels:
            Gc, label = coarsen_graph(graphs[-1], weight=weight, seed=trial_seed)
            if Gc.number_of_nodes() == graphs[-1].number_of_nodes():
                break
            graphs.append(Gc)
            maps.append(label)

        Gc = graphs[-1]
        if initial_method.upper() == "SPECTRAL":
            cpart = initial_partition_spectral(Gc, weight=weight)
        elif initial_method.upper() == "COMPONENT_AWARE":
            cpart = initial_partition_component_aware(Gc, weight=weight, balance_tol=balance_tol)
        else:
            cpart = initial_partition_gggp(Gc, weight=weight, balance_tol=balance_tol, seed=trial_seed)

        # Uncoarsen + multi-pass refine
        for level in range(len(maps) - 1, -1, -1):
            fine_G = graphs[level]
            coarse_label = maps[level]
            part = project_partition(fine_G, coarse_label, cpart)
            # multi-pass refinement
            if refine_method.upper() == "KL":
                best_cut = edge_cut(fine_G, part, weight=weight)
                for _ in range(max(1, refine_passes)):
                    new_part = refine_partition_kl(fine_G, dict(part), weight=weight)
                    new_cut = edge_cut(fine_G, new_part, weight=weight)
                    if new_cut + 1e-12 < best_cut:
                        part, best_cut = new_part, new_cut
                    else:
                        break
            else:
                best_cut = edge_cut(fine_G, part, weight=weight)
                for _ in range(max(1, refine_passes)):
                    new_part = refine_partition_fm(
                        fine_G, dict(part), weight=weight, balance_tol=balance_tol
                    )
                    new_cut = edge_cut(fine_G, new_part, weight=weight)
                    if new_cut + 1e-12 < best_cut:
                        part, best_cut = new_part, new_cut
                    else:
                        break
            cpart = part

        # Final balance enforcement (helps on disconnected graphs)
        final_part = rebalance_partition(G, cpart, weight=weight, balance_tol=balance_tol)
        final_cut = edge_cut(G, final_part, weight=weight)
        return final_part, final_cut

    # Multi-start trials
    best_part = None
    best_cut = float("inf")
    base_seed = 0 if seed is None else int(seed)
    for t in range(max(1, n_trials)):
        trial_seed = base_seed + t
        part, cut = run_once(trial_seed)
        if cut < best_cut:
            best_cut = cut
            best_part = part

    return best_part if best_part is not None else {}


def _has_vweight(G: nx.Graph) -> bool:
    try:
        return all('vweight' in G.nodes[n] for n in G.nodes())
    except Exception:
        return False


def _sum_vweight(G: nx.Graph, nodes) -> float:
    return float(sum(G.nodes[n].get('vweight', 1.0) for n in nodes))


def k_way_partition(
    G: nx.Graph,
    k: int,
    choose_by: str = 'vweight',
    **kwargs,
):
    """
    Recursive 2-way bisection to obtain k parts using multilevel_bipartition.
    kwargs are forwarded to multilevel_bipartition (weight, initial_method, refine_method, ...).
    choose_by: 'vweight' (if available) or 'size' to pick which block to split next.
    Returns: dict {node: part_label in [0..k-1]}
    """
    if k <= 0:
        raise ValueError("k must be >= 1")
    if k == 1:
        return {n: 0 for n in G.nodes()}
    if k == 2:
        return multilevel_bipartition(G, **kwargs)

    # Start with a single block containing all nodes
    parts: dict[int, set] = {0: set(G.nodes())}
    next_label = 1

    while len(parts) < k:
        # pick block to split
        if choose_by == 'vweight' and _has_vweight(G):
            pick = max(parts, key=lambda pid: _sum_vweight(G, parts[pid]))
        else:
            pick = max(parts, key=lambda pid: len(parts[pid]))

        nodes = parts.pop(pick)
        H = G.subgraph(nodes).copy()
        bi = multilevel_bipartition(H, **kwargs)
        A = {n for n, p in bi.items() if p == 0}
        B = set(H.nodes()) - A

        parts[pick] = A
        parts[next_label] = B
        next_label += 1

    # flatten labels
    out: dict = {}
    for lbl, ns in parts.items():
        for n in ns:
            out[n] = lbl
    # remap to 0..k-1
    remap = {lbl: i for i, lbl in enumerate(sorted(parts.keys()))}
    return {n: remap[lbl] for n, lbl in out.items()}
