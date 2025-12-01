import numpy as np
import networkx as nx

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