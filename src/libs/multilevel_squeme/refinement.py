import networkx as nx
import heapq
import math


def edge_cut(G: nx.Graph, part: dict, weight: str = "weight") -> float:
    cut = 0.0
    for u, v, data in G.edges(data=True):
        if part[u] != part[v]:
            w = data.get(weight, 1.0)
            cut += abs(w)
    return float(cut)


def _id_ed(G: nx.Graph, u, part: dict, weight: str = "weight") -> tuple[float, float]:
    """Return (id, ed) for node u under partition 'part'."""
    a = part[u]
    idw = 0.0
    edw = 0.0
    for v, data in G[u].items():
        w = float(abs(data.get(weight, 1.0)))
        if part[v] == a:
            idw += w
        else:
            edw += w
    return idw, edw


def _node_gain(G: nx.Graph, u, part: dict, weight: str = "weight") -> float:
    idw, edw = _id_ed(G, u, part, weight)
    return edw - idw


def refine_partition_fm(
    G: nx.Graph,
    part: dict,
    weight: str = "weight",
    max_passes: int = 10,
    balance_tol: float = 0.03,
):
    """
    METIS-nahe 2-Way FM (edge-based):
    - Boundary-Queues pro Seite mit Schlüssel gain = ed - id
    - from/to Wahl gemäß Zielgewichtsabweichung
    - Best-prefix-Rollback mit Limit wie in METIS
    """
    # Setup balance
    vweight = {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}
    total = sum(vweight.values())
    tp0 = total * 0.5
    tp1 = total - tp0
    # initial part weights
    pw0 = sum(vweight[u] for u in G if part[u] == 0)
    pw1 = total - pw0

    # helper to get boundary set and id/ed
    def boundary_set() -> list[int]:
        B = []
        for u in G.nodes():
            a = part[u]
            for v in G[u].keys():
                if part[v] != a:
                    B.append(u)
                    break
        return B

    # rpq simulieren mit heap; wir halten zwei heaps (0 und 1)
    def build_queues(B: list[int]):
        q0: list[tuple[float, int]] = []  # (-(ed-id), u)
        q1: list[tuple[float, int]] = []
        for u in B:
            idw, edw = _id_ed(G, u, part, weight)
            g = edw - idw
            if part[u] == 0:
                heapq.heappush(q0, (-g, u))
            else:
                heapq.heappush(q1, (-g, u))
        return q0, q1

    def update_after_move(moved_u: int, from_side: int, to_side: int, nbset: set[int]):
        # Update boundary membership for neighbors; collect potentially affected nodes
        for v in G[moved_u].keys():
            nbset.add(v)

    def is_boundary(u: int) -> bool:
        a = part[u]
        for v in G[u].keys():
            if part[v] != a:
                return True
        return False

    nv = G.number_of_nodes()
    limit_base = max(15, int(0.01 * nv))
    limit = min(limit_base, 100)

    for _pass in range(max_passes):
        B = boundary_set()
        q0, q1 = build_queues(B)
        moved_order: list[int] = []
        moved_from: dict[int, int] = {}
        gains_applied: list[float] = []
        mincut = edge_cut(G, part, weight)
        initcut = mincut
        best_cut = mincut
        best_ord = -1

        # moved flags
        moved_flag = {u: False for u in G.nodes()}
        affected: set[int] = set()
        nswaps = 0

        while True:
            # choose from-side by current diff to targets
            d0 = abs(tp0 - pw0)
            d1 = abs(tp1 - pw1)
            from_side = 0 if d0 > d1 else 1
            q = q0 if from_side == 0 else q1

            # pop top valid
            candidate = None
            while q:
                neg_g, u = heapq.heappop(q)
                if moved_flag[u]:
                    continue
                if not is_boundary(u):
                    continue
                candidate = (neg_g, u)
                break
            if candidate is None:
                break
            neg_g, u = candidate
            g = -neg_g
            to_side = 1 - from_side

            # balance check
            wu = vweight[u]
            new_pw0 = pw0 - wu if from_side == 0 else pw0 + wu
            new_pw1 = total - new_pw0
            # allow small slack similar to METIS via avg weight fudge (simplified)
            # we primarily allow move; strict bounds enforced by outer rebalance

            # apply move
            part[u] = to_side
            pw0 = new_pw0
            pw1 = new_pw1

            moved_flag[u] = True
            moved_order.append(u)
            moved_from[u] = from_side
            gains_applied.append(g)
            nswaps += 1

            # update current cut
            mincut -= g

            # track best prefix
            if mincut < best_cut - 1e-12:
                best_cut = mincut
                best_ord = len(moved_order) - 1
            elif nswaps - (best_ord if best_ord >= 0 else -1) > limit:
                # undo last move and stop
                part[u] = from_side
                pw0 = pw0 + wu if from_side == 0 else pw0 - wu
                pw1 = total - pw0
                moved_order.pop()
                gains_applied.pop()
                break

            # update neighbor boundary candidates lazily
            update_after_move(u, from_side, to_side, affected)
            # push affected into correct queues with refreshed gains
            for v in list(affected):
                if moved_flag[v]:
                    continue
                if not is_boundary(v):
                    continue
                idw, edw = _id_ed(G, v, part, weight)
                gv = edw - idw
                if part[v] == 0:
                    heapq.heappush(q0, (-gv, v))
                else:
                    heapq.heappush(q1, (-gv, v))
            affected.clear()

        # rollback tail to best
        if best_ord >= 0 and best_cut < initcut - 1e-12:
            # revert moves after best_ord
            for i in range(len(moved_order) - 1, best_ord, -1):
                u = moved_order[i]
                frm = moved_from[u]
                wu = vweight[u]
                if part[u] != frm:
                    part[u] = frm
                    pw0 = pw0 + wu if frm == 0 else pw0 - wu
                    pw1 = total - pw0
        else:
            # revert all moves
            for i in range(len(moved_order) - 1, -1, -1):
                u = moved_order[i]
                frm = moved_from[u]
                wu = vweight[u]
                if part[u] != frm:
                    part[u] = frm
                    pw0 = pw0 + wu if frm == 0 else pw0 - wu
                    pw1 = total - pw0

        # stop if no improvement in this pass
        if best_cut >= initcut - 1e-12:
            break

    return part


"""
Note: The former KL refinement path was removed to streamline the main flow.
Only FM-like refinement is kept (2-way and K-way).
"""

# New: Boundary KL-style refinement with best-prefix rollback (2-way)
def _boundary_nodes(G: nx.Graph, part: dict) -> set:
    B = set()
    for u in G.nodes():
        pu = part[u]
        for v in G[u].keys():
            if part[v] != pu:
                B.add(u)
                break
    return B


def _gain(G: nx.Graph, u, part: dict, weight: str = 'weight') -> float:
    a = part[u]
    ext_w = 0.0
    int_w = 0.0
    for v, data in G[u].items():
        w = float(abs(data.get(weight, 1.0)))
        if part[v] == a:
            int_w += w
        else:
            ext_w += w
    return ext_w - int_w


def refine_partition_bkl(
    G: nx.Graph,
    part: dict,
    *,
    weight: str = 'weight',
    balance_tol: float = 0.03,
    max_passes: int = 10,
) -> dict:
    """
    Boundary KL-like refinement: uses only boundary vertices, applies best-gain moves
    with best-prefix rollback each pass while respecting vweight balance tolerance.
    """
    # Balance model
    vweight = {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}
    total = sum(vweight.values())
    target = total / 2.0
    max_imb = balance_tol * total

    def within_balance(a_w: float, b_w: float) -> bool:
        return abs(a_w - target) <= max_imb and abs(b_w - target) <= max_imb

    def side_weights() -> tuple[float, float]:
        w0 = sum(vweight[u] for u, p in part.items() if p == 0)
        return w0, total - w0

    passes = 0
    improved = True
    while improved and passes < max_passes:
        passes += 1
        improved = False

        # Build boundary and initial gains
        boundary = _boundary_nodes(G, part)
        gains = {u: _gain(G, u, part, weight=weight) for u in boundary}
        # max-heap of (-gain, seq, u)
        H: list[tuple[float, int, int]] = []
        push_id = 0
        for u, g in gains.items():
            heapq.heappush(H, (-g, push_id, u))
            push_id += 1

        w0, w1 = side_weights()
        move_seq: list[tuple[int, int, float]] = []  # (u, old_part, gain)
        cum_best = 0.0
        cum = 0.0
        best_k = -1
        visited = set()

        while H:
            neg_g, _, u = heapq.heappop(H)
            if u in visited:
                continue
            if u not in boundary:
                continue
            g = -neg_g
            a = part[u]
            b = 1 - a
            # Check balance
            wu = vweight.get(u, 1.0)
            new_w0, new_w1 = (w0 - wu, w1 + wu) if a == 0 else (w0 + wu, w1 - wu)
            if not within_balance(new_w0, new_w1):
                continue
            # Apply move
            part[u] = b
            if a == 0:
                w0, w1 = new_w0, new_w1
            else:
                w0, w1 = new_w0, new_w1
            move_seq.append((u, a, g))
            visited.add(u)
            cum += g
            if cum > cum_best + 1e-12:
                cum_best = cum
                best_k = len(move_seq)

            # Update boundary and neighbor gains
            for v in G[u].keys():
                # v may change boundary status
                if part[v] != part[u]:
                    boundary.add(v)
                else:
                    # v might become interior
                    still_boundary = False
                    for z in G[v].keys():
                        if part[z] != part[v]:
                            still_boundary = True
                            break
                    if not still_boundary and v in boundary:
                        boundary.discard(v)
                # update gain if in boundary and not visited
                if v in boundary and v not in visited:
                    gains[v] = _gain(G, v, part, weight=weight)
                    heapq.heappush(H, (-gains[v], push_id, v))
                    push_id += 1

        # Rollback to best prefix if needed
        if best_k <= 0:
            # No improving prefix; revert all
            for u, old_a, _ in reversed(move_seq):
                part[u] = old_a
        else:
            # Revert tail
            for i in range(len(move_seq) - 1, best_k - 1, -1):
                u, old_a, _ = move_seq[i]
                part[u] = old_a
            if cum_best > 1e-12:
                improved = True

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


def _part_weights(G: nx.Graph, part: dict, k: int) -> list[float]:
    """
    Return per-part weights (vweight if present else counts) for k parts.
    Parts with no nodes get 0.
    """
    has_v = _has_vweight(G)
    w = [0.0] * k
    if has_v:
        for n, p in part.items():
            w[p] += float(G.nodes[n].get('vweight', 1.0))
    else:
        for p in part.values():
            w[p] += 1.0
    return w


def _node_weights(G: nx.Graph) -> dict:
    return {u: float(G.nodes[u].get('vweight', 1.0)) for u in G.nodes()}


def _move_gain_kway(G: nx.Graph, u, part: dict, target_b: int, weight: str = 'weight') -> float:
    """
    Gain of moving node u from current part a to target part b in terms of cut reduction.
    gain = sum_w(u to nodes in b) - sum_w(u to nodes in a)
    """
    a = part[u]
    if a == target_b:
        return 0.0
    sum_to_a = 0.0
    sum_to_b = 0.0
    for v, data in G[u].items():
        w = float(abs(data.get(weight, 1.0)))
        pv = part[v]
        if pv == a:
            sum_to_a += w
        elif pv == target_b:
            sum_to_b += w
    return sum_to_b - sum_to_a


def refine_partition_kway_fm(
    G: nx.Graph,
    part: dict,
    k: int,
    *,
    weight: str = 'weight',
    balance_tol: float = 0.03,
    max_moves: int | None = None,
) -> dict:
    """
    Simple K-way FM-like refinement: repeatedly move the single best node to the best target part
    that yields positive gain and respects global balance tolerance (by vweight if available).
    """
    vweight = _node_weights(G)
    total = sum(vweight.values()) if len(vweight) > 0 else float(len(G))
    target = total / float(max(1, k))
    # Per-part bound relative to target (METIS-like ub on each part)
    max_imb = balance_tol * target

    per = _part_weights(G, part, k)
    moves = 0

    # METIS-nahe rgain-Heuristik: rgain = ed/sqrt(nnbrs) - id
    def rgain(u: int, b: int) -> float:
        a = part[u]
        if a == b:
            return 0.0
        ed = 0.0
        idw = 0.0
        nnbrs = 0
        for v, data in G[u].items():
            w = float(abs(data.get(weight, 1.0)))
            nnbrs += 1
            if part[v] == a:
                idw += w
            elif part[v] == b:
                ed += w
        scale = 1.0 / math.sqrt(max(1, nnbrs))
        return ed * scale - idw

    while True:
        best = None  # (gain, u, b)
        # scan nodes and candidate target parts
        for u in G.nodes():
            a = part[u]
            wu = vweight.get(u, 1.0)
            for b in range(k):
                if b == a:
                    continue
                # Check balance after hypothetical move a->b
                new_a = per[a] - wu
                new_b = per[b] + wu
                # Enforce each part within target ± (balance_tol * target)
                if abs(new_a - target) > max_imb or abs(new_b - target) > max_imb:
                    continue
                # Prefer rgain-Heuristik, fallback auf reinen cut-gain
                g = rgain(u, b)
                if g <= 1e-12:
                    g = _move_gain_kway(G, u, part, b, weight=weight)
                if g > 1e-12:
                    if best is None or g > best[0]:
                        best = (g, u, b)

        if best is None:
            break
        # apply best move
        _, u, b = best
        a = part[u]
        wu = vweight.get(u, 1.0)
        part[u] = b
        per[a] -= wu
        per[b] += wu
        moves += 1
        if max_moves is not None and moves >= max_moves:
            break

    return part


def rebalance_partition_kway(
    G: nx.Graph,
    part: dict,
    k: int,
    *,
    weight: str = 'weight',
    balance_tol: float = 0.03,
    max_iters: int = 100000,
) -> dict:
    """
    Greedy K-way rebalancing: while any part exceeds allowed tolerance relative to target,
    move a single node from the heaviest part to the lightest part that yields the largest gain
    (smallest increase in cut). This enforces global balance at slight cut cost.
    """
    vweight = _node_weights(G)
    total = sum(vweight.values()) if len(vweight) > 0 else float(len(G))
    target = total / float(max(1, k))
    # Per-part bound relative to target (METIS-like)
    max_imb = balance_tol * target
    per = _part_weights(G, part, k)

    def imbalance_ok() -> bool:
        return all(abs(w - target) <= max_imb + 1e-12 for w in per)

    it = 0
    while not imbalance_ok() and it < max_iters:
        # identify heaviest part and lightest candidate
        heavy = max(range(k), key=lambda i: per[i])
        light = min(range(k), key=lambda i: per[i])
        # find best node to move from heavy to any other part (prefer light), by gain and balance feasibility
        best = None  # (gain, u, b)
        for u in G.nodes():
            if part[u] != heavy:
                continue
            wu = vweight.get(u, 1.0)
            for b in range(k):
                if b == heavy:
                    continue
                new_heavy = per[heavy] - wu
                new_b = per[b] + wu
                if abs(new_heavy - target) > max_imb or abs(new_b - target) > max_imb:
                    continue
                g = _move_gain_kway(G, u, part, b, weight=weight)
                if best is None or g > best[0]:
                    best = (g, u, b)
        if best is None:
            # cannot improve while respecting balance; relax by moving smallest-weight node
            # pick a node from heavy with minimal penalty towards light
            alt = None
            for u in G.nodes():
                if part[u] != heavy:
                    continue
                wu = vweight.get(u, 1.0)
                b = light
                new_heavy = per[heavy] - wu
                new_b = per[b] + wu
                if abs(new_heavy - target) > max_imb or abs(new_b - target) > max_imb:
                    continue
                g = _move_gain_kway(G, u, part, b, weight=weight)
                if alt is None or g > alt[0]:
                    alt = (g, u, b)
            if alt is None:
                break
            best = alt

        _, u, b = best
        a = part[u]
        wu = vweight.get(u, 1.0)
        part[u] = b
        per[a] -= wu
        per[b] += wu
        it += 1
    return part
