import networkx as nx
from .coarsening import coarsen_graph
from .partitioning import initial_partition_gggp
from .refinement import (
    refine_partition_fm,
    edge_cut,
    rebalance_partition,
    refine_partition_kway_fm,
    rebalance_partition_kway,
    edge_cut_kway,
)
# Note: Direct K-way pipeline is independent of METIS; METIS baseline is provided separately.


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
    verbose: bool = False,
):
    """
    Multilevel bipartitioning pipeline with multi-start and multi-pass refinement:
        - Coarsen until node count <= coarsen_limit or levels exhausted
        - Initial partition on coarsest via GGGP (multi-start over seeds)
        - Uncoarsen and refine at each level using FM for several passes (2-way is FM-only)

    Notes:
        - refine_method is accepted for API stability but ignored (2-way refinement is FM-only).
        - refine_passes controls how many FM sweeps per level.

    Returns: partition dict {node: 0|1}
    """
    method = str(refine_method).upper()

    def _balance_str(fG: nx.Graph, p: dict) -> str:
        try:
            has_v = all('vweight' in fG.nodes[n] for n in p.keys())
            if has_v:
                w0 = sum(float(fG.nodes[n]['vweight']) for n, lab in p.items() if lab == 0)
                w1 = sum(float(fG.nodes[n]['vweight']) for n, lab in p.items() if lab == 1)
            else:
                w0 = sum(1 for lab in p.values() if lab == 0)
                w1 = sum(1 for lab in p.values() if lab == 1)
            tot = max(1.0, float(w0 + w1))
            return f"balance=({w0/tot:.3f},{w1/tot:.3f})"
        except Exception:
            return "balance=?"

    def run_once(trial_seed: int | None):
        graphs = [G]
        maps: list[dict] = []

        # Step log: start (defer detailed per-level logs)
        if verbose:
            print(f"[bi] start: |V|={G.number_of_nodes()}, |E|={G.number_of_edges()}, seed={trial_seed}")

        lvl = 0
        while graphs[-1].number_of_nodes() > coarsen_limit and len(graphs) < max_levels:
            Gc, label = coarsen_graph(graphs[-1], weight=weight, seed=trial_seed)
            if Gc.number_of_nodes() == graphs[-1].number_of_nodes():
                break
            graphs.append(Gc)
            maps.append(label)
            lvl += 1

        Gc = graphs[-1]
        # Step log: coarsen result
        if verbose:
            print(f"[bi] coarsen result: |V|={Gc.number_of_nodes()}, |E|={Gc.number_of_edges()}")
        # Only GGGP initializer is kept (others removed for simplicity)
        cpart = initial_partition_gggp(Gc, weight=weight, balance_tol=balance_tol, seed=trial_seed)
        if verbose:
            icut = edge_cut(Gc, cpart, weight=weight)
            print(f"[bi] init result: cut={icut:.3f} {_balance_str(Gc, cpart)}")

        # Uncoarsen + multi-pass refine
        for level in range(len(maps) - 1, -1, -1):
            fine_G = graphs[level]
            coarse_label = maps[level]
            part = project_partition(fine_G, coarse_label, cpart)
            # multi-pass refinement (algorithm selected by refine_method)
            best_cut = edge_cut(fine_G, part, weight=weight)
            for _ in range(max(1, refine_passes)):
                # FM-only refinement retained
                new_part = refine_partition_fm(fine_G, dict(part), weight=weight, balance_tol=balance_tol)
                new_cut = edge_cut(fine_G, new_part, weight=weight)
                if new_cut + 1e-12 < best_cut:
                    part, best_cut = new_part, new_cut
                else:
                    break
            cpart = part

        # Final balance enforcement (helps on disconnected graphs)
        pre_cut = edge_cut(G, cpart, weight=weight)
        final_part = rebalance_partition(G, cpart, weight=weight, balance_tol=balance_tol)
        final_cut = edge_cut(G, final_part, weight=weight)
        if verbose:
            print(f"[bi] final result: cut {pre_cut:.3f} -> {final_cut:.3f} {_balance_str(G, final_part)}")
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
        if verbose:
            print(f"[bi] trial {t}: cut={cut:.3f} | best={best_cut:.3f}")

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
    verbose: bool = False,
    **kwargs,
):
    """
    Recursive 2-way bisection to obtain k parts using multilevel_bipartition.
    kwargs are forwarded to multilevel_bipartition (weight, initial_method, refine_method, ...).
    Note: For the underlying 2-way calls, refine_method is ignored (FM-only).
    choose_by: 'vweight' (if available) or 'size' to pick which block to split next.
    Returns: dict {node: part_label in [0..k-1]}
    """
    if k <= 0:
        raise ValueError("k must be >= 1")
    if k == 1:
        return {n: 0 for n in G.nodes()}
    if k == 2:
        return multilevel_bipartition(G, **kwargs)

    if verbose:
        print(f"[kway-rec] start: k={k}, |V|={G.number_of_nodes()}, |E|={G.number_of_edges()}")
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
        if verbose:
            print(f"[kway-rec] split block {pick}: |V|={H.number_of_nodes()}, |E|={H.number_of_edges()}")
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
    out_map = {n: remap[lbl] for n, lbl in out.items()}
    if verbose:
        print(f"[kway-rec] done: parts={len(parts)}")
    return out_map


def multilevel_kway_partition(
    G: nx.Graph,
    k: int,
    *,
    weight: str = 'weight',
    coarsen_limit: int = 80,
    max_levels: int = 20,
    seed: int | None = None,
    balance_tol: float = 0.03,
    refine_passes: int = 3,
    n_trials: int = 4,
    initial_method: str = 'GGGP',  # used when k==2 at coarsest for bootstrap
    verbose: bool = False,
) -> dict:
    """
    Direct K-way multilevel partitioning (no METIS involved):
        - Coarsen repeatedly (HEM)
        - Initialize K labels on the coarsest graph via internal recursive bisection (bootstrap)
        - Uncoarsen; at each level perform K-way refinement (FM-like) for multiple passes
        - Final K-way rebalancing to enforce global tolerance
    Returns {node: label in [0..k-1]}.
    """
    if k <= 1:
        return {n: 0 for n in G.nodes()}

    def coarsen_chain(H: nx.Graph, trial_seed: int | None):
        graphs = [H]
        maps: list[dict] = []
        if verbose:
            print(f"[kway] start: k={k}, |V|={H.number_of_nodes()}, |E|={H.number_of_edges()}, seed={trial_seed}")
        while graphs[-1].number_of_nodes() > coarsen_limit and len(graphs) < max_levels:
            Gc, label = coarsen_graph(graphs[-1], weight=weight, seed=trial_seed)
            if Gc.number_of_nodes() == graphs[-1].number_of_nodes():
                break
            graphs.append(Gc)
            maps.append(label)
        return graphs, maps

    def project_k(fine_G: nx.Graph, coarse_label: dict, coarse_part: dict):
        out = {}
        for u in fine_G.nodes():
            cu = coarse_label[u]
            out[u] = coarse_part.get(cu, 0)
        return out

    def init_k(Gc: nx.Graph, kk: int, trial_seed: int | None):
        # Bootstrap by internal recursive bisection only (no METIS)
        part0 = k_way_partition(
            Gc,
            kk,
            choose_by='vweight',
            weight=weight,
            coarsen_limit=max(20, coarsen_limit // 2),
            max_levels=max(5, max_levels // 2),
            seed=trial_seed,
            balance_tol=balance_tol,
            refine_method='FM',
            refine_passes=max(1, refine_passes // 2),
            n_trials=max(1, n_trials // 2),
            initial_method=initial_method,
            verbose=verbose,
        )
        if verbose:
            print(f"[kway] coarsen result: |V|={Gc.number_of_nodes()}, |E|={Gc.number_of_edges()}")
            print(f"[kway] init result: cut={edge_cut_kway(Gc, part0, weight=weight):.3f}")
        return part0

    best_part = None
    best_cut = float('inf')
    base_seed = 0 if seed is None else int(seed)

    for t in range(max(1, n_trials)):
        trial_seed = base_seed + t
        graphs, maps = coarsen_chain(G, trial_seed)
        Gc = graphs[-1]
        print("Most Coarsed Graph:", Gc.number_of_nodes(), Gc.number_of_edges())
        cpart = init_k(Gc, k, trial_seed)

        # Uncoarsen with K-way refinement passes per level
        for level in range(len(maps) - 1, -1, -1):
            fine_G = graphs[level]
            coarse_label = maps[level]
            part = project_k(fine_G, coarse_label, cpart)
            for _ in range(max(1, refine_passes)):
                part = refine_partition_kway_fm(
                    fine_G, dict(part), k, weight=weight, balance_tol=balance_tol
                )
            cpart = part

        # Final K-way rebalance and score
        pre = edge_cut_kway(G, cpart, weight=weight)
        final = rebalance_partition_kway(G, cpart, k, weight=weight, balance_tol=balance_tol)
        cut = edge_cut_kway(G, final, weight=weight)
        if verbose:
            print(f"[kway] final result: cut {pre:.3f} -> {cut:.3f}")
        if cut < best_cut:
            best_cut = cut
            best_part = final

    if verbose:
        print(f"[kway] best cut={best_cut:.3f}")
    return best_part if best_part is not None else {}
