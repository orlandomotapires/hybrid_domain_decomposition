import math
from collections import defaultdict
import numpy as np
import networkx as nx


def heavy_edge_matching(G: nx.Graph, weight: str = "weight", seed: int | None = None):
	"""
	Greedy heavy-edge matching: pair each unmatched node with its heaviest unmatched neighbor.
	Returns a dict mate[u] = v (v==u if unmatched/self-matched).
	"""
	rng = np.random.default_rng(seed)
	nodes = list(G.nodes())
	rng.shuffle(nodes)
	matched = set()
	mate: dict = {}

	for u in nodes:
		if u in matched: # If the node is already matched with another node, just skip it
			continue
		best_v = None
		best_w = -math.inf
		for v, data in G[u].items():
			if v in matched:
				continue
			w = abs(data.get(weight, 1.0))
			if w > best_w:
				best_w = w
				best_v = v
		if best_v is None:
			mate[u] = u
			matched.add(u)
		else:
			mate[u] = best_v
			mate[best_v] = u
			matched.add(u)
			matched.add(best_v)
	return mate


def coarsen_graph(G: nx.Graph, weight: str = "weight", seed: int | None = None):
	"""
	Contract matched pairs into supernodes. Edge weights between supernodes are summed.
	Returns (Gc, coarse_label) where coarse_label maps fine node -> coarse node id.
	"""
	mate = heavy_edge_matching(G, weight=weight, seed=seed)

	# Build coarse nodes (create the super nodes from matched pairs)
	coarse_label: dict[int, int] = {}
	coarse_nodes: list[tuple[int, int]] = []
	for u in G.nodes():
		v = mate[u]
		if u <= v:
			cid = len(coarse_nodes)
			coarse_nodes.append((u, v))
			coarse_label[u] = cid
			coarse_label[v] = cid

	# Aggregate edges (create the new edges between coarsed nodes summing up weights of the fine edges)
	agg = defaultdict(float)
	for u, v, data in G.edges(data=True):
		cu = coarse_label[u]
		cv = coarse_label[v]
		if cu == cv:
			continue
		w = abs(data.get(weight, 1.0))
		if cu > cv:
			cu, cv = cv, cu
		agg[(cu, cv)] += w

	Gc = nx.Graph()
	# Add coarse nodes and aggregate vertex weights if present (create the final coarse graph getting the super nodes and edges together)
	for cid, (u, v) in enumerate(coarse_nodes):
		vw_u = float(G.nodes[u].get('vweight', 1.0))
		# If unmatched (self-matched), don't double-count
		if v == u:
			vw = vw_u
		else:
			vw_v = float(G.nodes[v].get('vweight', 1.0))
			vw = vw_u + vw_v
		Gc.add_node(cid, vweight=vw)
	for (cu, cv), w in agg.items():
		Gc.add_edge(cu, cv, **{weight: w})

	return Gc, coarse_label

