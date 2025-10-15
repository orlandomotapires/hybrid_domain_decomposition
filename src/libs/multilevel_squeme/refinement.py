import networkx as nx


def edge_cut(G: nx.Graph, part: dict, weight: str = "weight") -> float:
    cut = 0.0
    for u, v, data in G.edges(data=True):
        if part[u] != part[v]:
            w = data.get(weight, 1.0)
            cut += abs(w)
    return float(cut)


def _node_gain(G: nx.Graph, u, part: dict, weight: str = "weight") -> float:
    a = part[u]
    ext_w = 0.0
    int_w = 0.0
    for v, data in G[u].items():
        w = abs(data.get(weight, 1.0))
        if part[v] == a:
            int_w += w
        else:
            ext_w += w
    return ext_w - int_w


def refine_partition_fm(
    G: nx.Graph,
    part: dict,
    weight: str = "weight",
    max_moves: int | None = None,
    balance_tol: float = 0.1,
):
    """
    Simple FM-like refinement: iteratively move nodes with positive gain while preserving approximate balance.
    """
    # Balance based on vertex weights if present
    vweight = {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}
    total_w = sum(vweight.values())
    target = total_w / 2.0
    max_imbalance = balance_tol * total_w

    w0 = sum(vweight[u] for u in G if part[u] == 0)
    w1 = total_w - w0

    locked = set()
    moves = 0

    while True:
        best_u = None
        best_gain = 0.0
        for u in G.nodes():
            if u in locked:
                continue
            gain = _node_gain(G, u, part, weight=weight)
            if part[u] == 0:
                new_w0, new_w1 = w0 - vweight[u], w1 + vweight[u]
            else:
                new_w0, new_w1 = w0 + vweight[u], w1 - vweight[u]
            if abs(new_w0 - target) > max_imbalance or abs(new_w1 - target) > max_imbalance:
                continue
            if gain > best_gain:
                best_gain = gain
                best_u = u

        if best_u is not None and best_gain > 1e-12:
            a = part[best_u]
            part[best_u] = 1 - a
            if a == 0:
                w0 -= vweight[best_u]
                w1 += vweight[best_u]
            else:
                w0 += vweight[best_u]
                w1 -= vweight[best_u]
            locked.add(best_u)
            moves += 1
            if max_moves is not None and moves >= max_moves:
                break
        else:
            break

    return part


def refine_partition_kl(
    G: nx.Graph, part: dict, weight: str = "weight", max_pairs: int | None = None
):
    """
    Simplified KL: repeatedly swap the best pair (a in A, b in B) with the highest gain
    until no positive-gain swap exists or max_pairs reached.
    """
    A = {u for u, p in part.items() if p == 0}
    B = set(G.nodes()) - A
    if not A or not B:
        return part

    def D(u):
        d_ext = 0.0
        d_int = 0.0
        for v, data in G[u].items():
            w = abs(data.get(weight, 1.0))
            if (v in A) == (u in A):
                d_int += w
            else:
                d_ext += w
        return d_ext - d_int

    moves = 0
    while True:
        Dvals = {u: D(u) for u in G.nodes()}
        best_gain = 0.0
        best_pair = None
        for a in A:
            for b in B:
                w_ab = abs(G[a][b][weight]) if G.has_edge(a, b) and weight in G[a][b] else (1.0 if G.has_edge(a, b) else 0.0)
                gain = Dvals[a] + Dvals[b] - 2.0 * w_ab
                if gain > best_gain:
                    best_gain = gain
                    best_pair = (a, b)

        if best_pair and best_gain > 1e-12:
            a, b = best_pair
            A.remove(a); B.add(a)
            B.remove(b); A.add(b)
            part[a], part[b] = 1, 0
            moves += 1
            if max_pairs is not None and moves >= max_pairs:
                break
        else:
            break

    return part


def rebalance_partition(
    G: nx.Graph, part: dict, weight: str = "weight", balance_tol: float = 0.1, max_iters: int = 10000
):
    """
    Greedy rebalancing: while imbalance exceeds tolerance, move one node from the heavy side
    that yields the smallest increase in cut (i.e., maximal gain). This enforces balance
    even on disconnected graphs (at the cost of possibly increasing cut).
    """
    vweight = {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}
    total = sum(vweight.values())
    target = total / 2.0
    max_imb = balance_tol * total

    def sums():
        w0 = sum(vweight[u] for u in G if part[u] == 0)
        return w0, total - w0

    w0, w1 = sums()
    iters = 0
    while abs(w0 - target) > max_imb and iters < max_iters:
        heavy = 0 if w0 > target else 1
        best_u = None
        best_gain = -1e300
        for u in G.nodes():
            if part[u] != heavy:
                continue
            g = _node_gain(G, u, part, weight=weight)
            if g > best_gain:
                best_gain = g
                best_u = u
        if best_u is None:
            break
        # Move best_u
        part[best_u] = 1 - part[best_u]
        if heavy == 0:
            w0 -= vweight[best_u]
            w1 += vweight[best_u]
        else:
            w0 += vweight[best_u]
            w1 -= vweight[best_u]
        iters += 1
    return part


def edge_cut_kway(G: nx.Graph, part: dict, weight: str = "weight") -> float:
    """Sum of weights of edges whose endpoints are in different part labels."""
    cut = 0.0
    for u, v, data in G.edges(data=True):
        if part[u] != part[v]:
            cut += float(abs(data.get(weight, 1.0)))
    return float(cut)


def _has_vweight(G: nx.Graph) -> bool:
    try:
        return all('vweight' in G.nodes[n] for n in G.nodes())
    except Exception:
        return False


def kway_balance_info(G: nx.Graph, part: dict):
    """
    Returns (labels_sorted, per_part_weights, total) where weights are vweight if present else counts.
    """
    labels = sorted(set(part.values()))
    per = []
    if _has_vweight(G):
        for lbl in labels:
            per.append(sum(float(G.nodes[n].get('vweight', 1.0)) for n, p in part.items() if p == lbl))
    else:
        for lbl in labels:
            per.append(sum(1 for n, p in part.items() if p == lbl))
    total = float(sum(per))
    return labels, per, total
