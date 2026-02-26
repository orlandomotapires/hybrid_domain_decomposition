from __future__ import annotations

from typing import Dict, Any, List, Tuple
import networkx as nx


def partition_graph_metis(
    G: nx.Graph,
    nparts: int = 2,
    weight: str = "weight",
    seed: int | None = None,
    verbose: bool = False,
) -> Dict[Any, int]:
    """
    Simple, clean METIS wrapper using PyMetis with optional weights.
    - Builds adjacency from G and calls pymetis.part_graph.
    - Uses edge weights from edge attribute `weight` (default 'weight') if present.
    - Uses node weights from node attribute 'vweight' if present.
    - Converts weights to small positive integers (METIS requirement) via auto-scaling.
    - Returns a dict {node: part_id}.

    Requires: pymetis
    """
    if verbose:
        print(f"[metis] nparts={nparts}, |V|={G.number_of_nodes()}, |E|={G.number_of_edges()}")

    try:
        import pymetis  # type: ignore
    except Exception as e:
        raise RuntimeError("PyMetis is required for partition_graph_metis. Please install 'pymetis'.") from e

    # Stable node order
    nodes: List[Any] = list(G.nodes())
    index = {u: i for i, u in enumerate(nodes)}
    adjacency: List[List[int]] = [[] for _ in nodes]
    eweights: List[List[int]] = [[] for _ in nodes]

    # Collect edge weights and determine auto-scale
    edge_vals: List[float] = []
    for u, v, data in G.edges(data=True):
        w = data.get(weight, 1.0)
        try:
            wf = float(w)
        except Exception:
            wf = 1.0
        if wf > 0:
            edge_vals.append(wf)

    def _auto_scale_to_int(values: List[float]) -> float:
        """Return a scale so that min positive value maps ~ to 1 when rounded."""
        if not values:
            return 1.0
        m = min(values)
        if m <= 0:
            return 1.0
        # Limit scale to avoid huge integers
        scale = 1.0 / m
        # cap scale so that max doesn't explode (heuristic)
        mx = max(values)
        if mx * scale > 10_000_000:
            scale = 10_000_000 / max(mx, 1e-12)
        return scale

    escale = _auto_scale_to_int(edge_vals)

    for u in nodes:
        ui = index[u]
        for v in G.neighbors(u):
            vi = index[v]
            adjacency[ui].append(vi)
            # per-edge weight from u->v
            data = G.get_edge_data(u, v, default={})
            w = data.get(weight, 1.0)
            try:
                wf = float(w)
            except Exception:
                wf = 1.0
            iw = int(max(1, round(wf * escale)))
            eweights[ui].append(iw)

    has_vw = False
    vwgt_f: List[float] = []
    for u in nodes:
        val = G.nodes[u].get("vweight", None)
        if val is not None:
            has_vw = True
        vwgt_f.append(1.0 if val is None else float(val))

    if has_vw:
        # scale to ints using same strategy
        vpos = [v for v in vwgt_f if v > 0]
        vscale = (1.0 / min(vpos)) if vpos else 1.0
        # cap scale
        if vpos and max(vpos) * vscale > 10_000_000:
            vscale = 10_000_000 / max(vpos)
        vwgt = [int(max(1, round(v * vscale))) for v in vwgt_f]
    else:
        vwgt = None

    # CSR conversion (xadj/adjncy/eweights) is the most stable API across versions
    xadj: List[int] = [0]
    adjncy: List[int] = []
    eweights_flat: List[int] = []
    for row_idx in range(len(adjacency)):
        row = adjacency[row_idx]
        wrow = eweights[row_idx]
        adjncy.extend(row)
        eweights_flat.extend(wrow)
        xadj.append(len(adjncy))

    # Decide if we pass weights
    pass_eweights = any(w != 1 for w in eweights_flat)

    # Prepare kwargs with CSR; try new-style then old-style names
    try:
        kwargs: Dict[str, Any] = {"nparts": nparts, "xadj": xadj, "adjncy": adjncy}
        if pass_eweights:
            kwargs["eweights"] = eweights_flat
        if vwgt is not None:
            kwargs["vweights"] = vwgt
        _, membership = pymetis.part_graph(**kwargs)  # type: ignore[arg-type]
    except TypeError:
        try:
            kwargs = {"nparts": nparts, "xadj": xadj, "adjncy": adjncy}
            if pass_eweights:
                kwargs["adjwgt"] = eweights_flat
            if vwgt is not None:
                kwargs["vwgt"] = vwgt
            _, membership = pymetis.part_graph(**kwargs)  # type: ignore[arg-type]
        except TypeError:
            # Fallback to unweighted adjacency call
            _, membership = pymetis.part_graph(nparts, adjacency=adjacency)
    return {nodes[i]: int(membership[i]) for i in range(len(nodes))}
