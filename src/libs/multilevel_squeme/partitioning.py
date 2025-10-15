import numpy as np
import networkx as nx
import scipy.sparse as sp
import scipy.sparse.linalg as spla


def _seed_start_nodes(G: nx.Graph, k: int = 1, seed: int | None = None):
    rng = np.random.default_rng(seed)
    nodes = list(G.nodes())
    if len(nodes) == 0:
        return []
    # Use absolute weighted degree to avoid negative probabilities
    degrees = []
    for n in nodes:
        s = 0.0
        for _, data in G[n].items():
            w = data.get("weight", 1.0)
            s += abs(w)
        degrees.append(s)
    degrees = np.array(degrees, dtype=float)
    total = degrees.sum()
    if total <= 0:
        # Fallback to uniform random if all zero
        idx = rng.integers(len(nodes), size=min(k, len(nodes)), endpoint=False)
        return [nodes[i] for i in np.atleast_1d(idx)]
    probs = degrees / total
    # Safety: ensure non-negative and finite probabilities
    if np.any(~np.isfinite(probs)) or np.any(probs < 0):
        idx = rng.integers(len(nodes), size=min(k, len(nodes)), endpoint=False)
        return [nodes[i] for i in np.atleast_1d(idx)]
    # Normalize in case of rounding
    probs = probs / probs.sum()
    idx = rng.choice(len(nodes), size=min(k, len(nodes)), replace=False, p=probs)
    return [nodes[i] for i in idx]


def initial_partition_gggp(G: nx.Graph, weight: str = "weight", balance_tol: float = 0.1, seed: int | None = None):
    """
    Greedy Graph Growing Partitioning (GGGP):
    - Start from a seed node in part 0; grow part 0 greedily by gain while respecting balance.
    - Remaining nodes constitute part 1.
    Returns partition dict {node: 0|1}.
    """
    n = G.number_of_nodes()
    if n == 0:
        return {}
    if n == 1:
        u = next(iter(G.nodes()))
        return {u: 0}

    # Use vertex weights if present; else fallback to 1 per node
    vweights = {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}
    total_w = sum(vweights.values())
    target = total_w / 2.0
    max_imbalance = balance_tol * total_w

    seeds = _seed_start_nodes(G, k=1, seed=seed)
    s0 = seeds[0]
    part = {u: 1 for u in G.nodes()}
    part[s0] = 0
    size0 = vweights[s0]

    def gain(u):
        ext_w = 0.0
        int_w = 0.0
        for v, data in G[u].items():
            w = abs(data.get(weight, 1.0))
            if part[v] == 0:
                int_w += w
            else:
                ext_w += w
        return ext_w - int_w

    boundary = set()
    for v in G.neighbors(s0):
        if part[v] == 1:
            boundary.add(v)

    while size0 < target + max_imbalance and boundary:
        best_v = None
        best_gain = -1e18
        for v in list(boundary):
            g = gain(v)
            if g > best_gain:
                best_gain = g
                best_v = v
        if best_v is None:
            break
        if size0 + vweights[best_v] <= target + max_imbalance:
            part[best_v] = 0
            size0 += vweights[best_v]
            boundary.discard(best_v)
            for w in G.neighbors(best_v):
                if part[w] == 1:
                    boundary.add(w)
        else:
            break

    return part


def initial_partition_spectral(G: nx.Graph, weight: str = "weight", target_weight: float | None = None):
    """
    Spectral bipartition using the Fiedler vector of the weighted Laplacian.
    Solves L x = lambda D x, D is diagonal of vertex weights (or identity).
    Splits nodes at the weighted median of x to achieve near 50/50 by vweight.
    Returns partition dict {node: 0|1}.
    """
    n = G.number_of_nodes()
    if n == 0:
        return {}
    if n == 1:
        u = next(iter(G.nodes()))
        return {u: 0}

    # Work on the largest connected component to avoid multiple zero eigenvalues
    if G.number_of_edges() == 0:
        # No edges: split by vweight greedily
        nodes = list(G.nodes())
        vw = {u: float(G.nodes[u].get('vweight', 1.0)) for u in nodes}
        order_nodes = sorted(nodes, key=lambda u: vw[u], reverse=True)
        part = {u: 1 for u in nodes}
        s0 = 0.0
        target = sum(vw.values()) / 2.0
        for u in order_nodes:
            if s0 + vw[u] <= target:
                part[u] = 0
                s0 += vw[u]
        return part

    components = list(nx.connected_components(G))
    comp_main = max(components, key=len)
    H = G.subgraph(comp_main).copy()
    nodes = list(H.nodes())
    # Weighted Laplacian on main component
    try:
        L = nx.laplacian_matrix(H, weight=weight).asfptype()
    except Exception:
        A = nx.to_scipy_sparse_array(H, weight=weight, format='csr')
        d = np.asarray(A.sum(axis=1)).ravel()
        L = sp.diags(d) - A

    # Vertex weights diagonal (use 1 if missing) on H
    vw_arr = np.array([float(H.nodes[u].get('vweight', 1.0)) for u in nodes], dtype=float)
    vw_arr[~np.isfinite(vw_arr)] = 1.0
    vw_arr[vw_arr <= 0] = 1.0
    D = sp.diags(vw_arr)

    # Compute Fiedler vector with regularization to avoid singularities
    fiedler = None
    # Attempt 1: shift-invert with small sigma
    try:
        vals, vecs = spla.eigsh(L, k=2, M=D, sigma=1e-8, which='LM')
        order = np.argsort(vals)
        fiedler = vecs[:, order[1]] if len(order) > 1 else vecs[:, 0]
    except Exception:
        pass
    # Attempt 2: regularize Laplacian with eps*D and ask for SM
    if fiedler is None:
        try:
            Lreg = L + 1e-8 * D
            vals, vecs = spla.eigsh(Lreg, k=2, M=D, which='SM')
            order = np.argsort(vals)
            fiedler = vecs[:, order[1]] if len(order) > 1 else vecs[:, 0]
        except Exception:
            pass
    # Attempt 3: regularize with identity, no M
    if fiedler is None:
        try:
            I = sp.identity(L.shape[0], format='csr')
            vals, vecs = spla.eigsh(L + 1e-6 * I, k=2, which='SM')
            order = np.argsort(vals)
            fiedler = vecs[:, order[1]] if len(order) > 1 else vecs[:, 0]
        except Exception:
            pass
    # Fallback: return GGGP if spectral failed completely
    if fiedler is None:
        return initial_partition_gggp(G, weight=weight, balance_tol=0.03, seed=None)

    # Split at weighted threshold on H (median if no target)
    perm = np.argsort(fiedler)
    cum = np.cumsum(vw_arr[perm])
    desired = vw_arr.sum() / 2.0 if target_weight is None else float(target_weight)
    cut_idx = int(np.searchsorted(cum, desired, side='left'))
    threshold = fiedler[perm[min(max(cut_idx, 0), len(nodes) - 1)]]

    part = {u: 1 for u in G.nodes()}
    # Assign component nodes
    for i, u in enumerate(nodes):
        part[u] = 0 if fiedler[i] <= threshold else 1
    # Assign remaining nodes to balance total vweight
    vw_full = {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}
    s0 = sum(vw_full[u] for u in G.nodes() if part[u] == 0)
    target = sum(vw_full.values()) / 2.0
    others = [u for u in G.nodes() if u not in H]
    # Greedy assign heavy nodes first to the lighter side
    for u in sorted(others, key=lambda x: vw_full[x], reverse=True):
        if s0 + vw_full[u] <= target:
            part[u] = 0
            s0 += vw_full[u]
        else:
            part[u] = 1
    # Ensure both parts non-empty
    if all(p == 0 for p in part.values()):
        any_u = next(iter(G.nodes()))
        part[any_u] = 1
    if all(p == 1 for p in part.values()):
        any_u = next(iter(G.nodes()))
        part[any_u] = 0
    return part


def initial_partition_component_aware(
    G: nx.Graph, weight: str = "weight", balance_tol: float = 0.03
):
    """
    Component-aware initializer:
    - If graph is disconnected, pack whole components into two parts to get close to 50% by vweight.
    - Split at most one component using spectral to reach the remaining target.
    Returns {node: 0|1}.
    """
    if G.number_of_nodes() <= 1:
        return {u: 0 for u in G.nodes()}
    comps = list(nx.connected_components(G))
    if len(comps) == 1:
        return initial_partition_spectral(G, weight=weight)

    vw = {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}
    comp_weights = [(c, sum(vw[u] for u in c)) for c in comps]
    comp_weights.sort(key=lambda x: x[1], reverse=True)

    total = sum(w for _, w in comp_weights)
    target = total / 2.0
    tol = balance_tol * total

    part = {u: 1 for u in G.nodes()}
    acc = 0.0
    split_comp = None

    # Greedily take whole components into part 0 until we would exceed target+tol
    for c, w in comp_weights:
        if acc + w <= target + tol:
            for u in c:
                part[u] = 0
            acc += w
        else:
            split_comp = (c, w)
            break

    if split_comp is None:
        # Already balanced enough without cutting a component
        return part

    c, w = split_comp
    remaining = max(0.0, target - acc)
    if remaining <= 0.0:
        # We already met target; no split needed
        return part

    # Run spectral on the chosen component and take just enough weight into part 0
    H = G.subgraph(c).copy()
    sub_part = initial_partition_spectral(H, weight=weight, target_weight=remaining)
    for u, p in sub_part.items():
        part[u] = p

    return part
