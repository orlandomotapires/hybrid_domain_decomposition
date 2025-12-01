from collections import defaultdict
import networkx as nx

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

