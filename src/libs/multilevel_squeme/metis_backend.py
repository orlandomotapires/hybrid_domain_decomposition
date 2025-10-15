from __future__ import annotations

from typing import Dict, Any, List, Tuple
import networkx as nx


def _graph_to_adjacency(G: nx.Graph) -> Tuple[List[Any], Dict[Any, int], List[List[int]], List[List[float]]]:
    nodes = list(G.nodes())
    index = {u: i for i, u in enumerate(nodes)}
    adjacency = []
    weights = []  # parallel to adjacency: list of edge weights per row
    for u in nodes:
        nbrs = []
        wts = []
        for v in G.neighbors(u):
            nbrs.append(index[v])
            w = G[u][v].get("weight", 1.0)
            wts.append(float(abs(w)))
        adjacency.append(nbrs)
        weights.append(wts)
    return nodes, index, adjacency, weights


def _to_csr(adjacency: List[List[int]], weights: List[List[float]]):
    xadj: List[int] = [0]
    adjncy: List[int] = []
    eweights: List[int] = []
    for nbrs, wts in zip(adjacency, weights):
        adjncy.extend(nbrs)
        eweights.extend([max(1, int(round(w * 100.0))) for w in wts])
        xadj.append(len(adjncy))
    return xadj, adjncy, eweights


def partition_graph_metis(G: nx.Graph, nparts: int = 2, weight: str = "weight", seed: int | None = None) -> Dict[Any, int]:
    """
    Partition a NetworkX graph using a METIS backend.
    Tries PyMetis first, then python-metis as fallback. Edge weights are currently ignored (unweighted cut).
    Returns a dict {node: part_id}.
    """
    nodes, index, adjacency, weights = _graph_to_adjacency(G)

    # Collect optional node weights (vweight)
    vweights = None
    if len(G) > 0 and 'vweight' in next(iter(G.nodes(data=True)))[1]:
        vweights = [max(1, int(round(abs(float(G.nodes[u]['vweight']))))) for u in nodes]

    # Try PyMetis
    py_err = None
    try:
        import pymetis  # type: ignore

        if seed is not None:
            try:
                pymetis.options["seed"] = int(seed)  # may not exist in all versions
            except Exception:
                pass
        flat = [w for row in weights for w in row]
        if len(flat) > 0 and max(flat) > 0:
            # Variant A: list-of-lists with eweights
            try:
                adj_int = [[int(v) for v in row] for row in adjacency]
                adjwgt = [[max(1, int(round(w * 100.0))) for w in row] for row in weights]
                if vweights is not None:
                    _, membership = pymetis.part_graph(nparts, adjacency=adj_int, eweights=adjwgt, vweights=vweights)
                else:
                    _, membership = pymetis.part_graph(nparts, adjacency=adj_int, eweights=adjwgt)
                return {nodes[i]: int(membership[i]) for i in range(len(nodes))}
            except Exception as e:
                py_err = e
            # Variant B: CSR arrays with eweights
            try:
                xadj, adjncy, eweights = _to_csr(adjacency, weights)
                if vweights is not None:
                    _, membership = pymetis.part_graph(nparts, xadj=xadj, adjncy=adjncy, eweights=eweights, vweights=vweights)
                else:
                    _, membership = pymetis.part_graph(nparts, xadj=xadj, adjncy=adjncy, eweights=eweights)
                return {nodes[i]: int(membership[i]) for i in range(len(nodes))}
            except Exception as e:
                py_err = e
            # Variant C: CSR arrays with adjwgt name
            try:
                xadj, adjncy, eweights = _to_csr(adjacency, weights)
                if vweights is not None:
                    _, membership = pymetis.part_graph(nparts, xadj=xadj, adjncy=adjncy, adjwgt=eweights, vwgt=vweights)  # type: ignore
                else:
                    _, membership = pymetis.part_graph(nparts, xadj=xadj, adjncy=adjncy, adjwgt=eweights)  # type: ignore
                return {nodes[i]: int(membership[i]) for i in range(len(nodes))}
            except Exception as e:
                py_err = e
        else:
            # Unweighted
            _, membership = pymetis.part_graph(nparts, adjacency=adjacency)
            return {nodes[i]: int(membership[i]) for i in range(len(nodes))}
    except Exception as e:
        py_err = e

    # Fallback: python-metis (aka 'metis' package)
    metis_err = None
    try:
        import metis  # type: ignore

        # metis.part_graph can accept a networkx graph directly in some versions
        try:
            # Many wrappers accept nx graph and read 'weight' automatically; ensure abs integer weights
            H = nx.Graph()
            H.add_nodes_from(G.nodes())
            for u, v, d in G.edges(data=True):
                w = d.get("weight", 1.0)
                H.add_edge(u, v, weight=max(1, int(round(abs(float(w)) * 100.0))))
            try:
                # If vweights present, ensure they are integers on nodes
                if vweights is not None:
                    for i, u in enumerate(H.nodes()):
                        H.nodes[u]['vwgt'] = int(vweights[i])
                _, parts = metis.part_graph(H, nparts, objtype='cut')  # type: ignore
            except TypeError:
                _, parts = metis.part_graph(H, nparts)
        except Exception as e:
            # convert to CSR-like structure with integer weights
            try:
                xadj, adjncy, eweights = _to_csr(adjacency, weights)
                if vweights is not None:
                    _, parts = metis.part_graph((len(nodes), xadj, adjncy), nparts, eweights=eweights, vwgt=vweights)
                else:
                    _, parts = metis.part_graph((len(nodes), xadj, adjncy), nparts, eweights=eweights)
            except Exception as ee:
                metis_err = ee
        return {nodes[i]: int(parts[i]) for i in range(len(nodes))}
    except Exception as e:
        metis_err = e

    # If we got here, both attempts failed; include details to help debug
    raise RuntimeError(
        f"No METIS backend succeeded. PyMetis error: {repr(py_err)} | python-metis error: {repr(metis_err)}"
    )
