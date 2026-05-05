import math
from collections import defaultdict
import numpy as np
import networkx as nx


def heavy_edge_matching(G: nx.Graph, weight: str = "weight", seed: int | None = None, strategy: str = "random", max_node_weight: float | None = None):
	"""
	Greedy heavy-edge matching with multiple strategies and node weight constraint.
	
	Strategies:
	- 'random': Random node order (original HEM)
	- 'sorted': Degree-sorted order (SHEM - Sorted HEM, METIS default)
	- 'modified': Modified HEM considering node weights (MHEM)
	- 'light': Light-edge matching (for sparse graphs)
	
	Args:
		G: Input graph
		weight: Edge weight attribute
		seed: Random seed
		strategy: Matching strategy
		max_node_weight: Maximum allowed weight for a supernode (prevents creating too heavy nodes)
	
	Returns a dict mate[u] = v (v==u if unmatched/self-matched).
	"""
	rng = np.random.default_rng(seed)
	nodes = list(G.nodes())
	matched = set()
	mate: dict = {}
	
	if strategy == "sorted":
		# SHEM: Sort nodes by weighted degree initially (descending)
		# High-degree nodes get priority to be matched first
		nodes = sorted(nodes, key=lambda u: G.degree(u, weight=weight), reverse=True)
	elif strategy == "random":
		# Random shuffle (original HEM)
		rng.shuffle(nodes)
	elif strategy in ("modified", "light"):
		# For modified/light, we'll process in random order but scoring differs
		rng.shuffle(nodes)
	else:
		raise ValueError(f"Unknown matching strategy: {strategy}")

	for u in nodes:
		if u in matched:
			continue
		
		vw_u = float(G.nodes[u].get('vweight', 1.0))
		
		# Collect unmatched candidates
		candidates = []
		for v, data in G[u].items():
			if v in matched:
				continue
			
			# Check max_node_weight constraint
			if max_node_weight is not None:
				vw_v = float(G.nodes[v].get('vweight', 1.0))
				combined_weight = vw_u + vw_v
				if combined_weight > max_node_weight:
					# Skip this candidate - would create too heavy supernode
					continue
			
			edge_w = abs(data.get(weight, 1.0))
			
			if strategy == "modified":
				# Modified HEM: consider node weights to avoid unbalanced supernodes
				# Score = edge_weight / sqrt(vweight_u * vweight_v)
				# This favors matching nodes with similar weights
				vw_v = float(G.nodes[v].get('vweight', 1.0))
				score = edge_w / math.sqrt(vw_u * vw_v) if vw_u > 0 and vw_v > 0 else edge_w
			elif strategy == "light":
				# Light-edge matching: prefer lighter edges (useful for sparse graphs)
				score = -edge_w
			else:
				# Standard HEM: just edge weight
				score = edge_w
			
			candidates.append((score, edge_w, v))
		
		if not candidates:
			# No unmatched neighbors (or all violate weight constraint) - self-match
			mate[u] = u
			matched.add(u)
		else:
			# Sort by score (descending), then by edge weight for tie-breaking, then shuffle tied entries
			candidates.sort(key=lambda x: (-x[0], -x[1], rng.random()))
			best_v = candidates[0][2]
			
			mate[u] = best_v
			mate[best_v] = u
			matched.add(u)
			matched.add(best_v)
	
	return mate


def coarsen_graph(G: nx.Graph, weight: str = "weight", seed: int | None = None, strategy: str = "sorted", max_node_weight: float | None = None):
	"""
	Contract matched pairs into supernodes. Edge weights between supernodes are summed.
	
	Args:
		G: Input graph
		weight: Edge weight attribute name
		seed: Random seed for matching
		strategy: Matching strategy ('random', 'sorted', 'modified', 'light')
		max_node_weight: Maximum allowed weight for a supernode (None = no limit)
	
	Returns (Gc, coarse_label) where coarse_label maps fine node -> coarse node id.
	"""
	mate = heavy_edge_matching(G, weight=weight, seed=seed, strategy=strategy, max_node_weight=max_node_weight)

	# Build supernodes from the selected matches.
	coarse_label: dict[int, int] = {}
	coarse_nodes: list[tuple[int, int]] = []
	for u in G.nodes():
		v = mate[u]
		if u <= v:
			cid = len(coarse_nodes)
			coarse_nodes.append((u, v))
			coarse_label[u] = cid
			coarse_label[v] = cid

	# Aggregate fine edges between supernodes by summing their weights.
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

	# Add coarse nodes with summed vweights
	Gc = nx.Graph()
	for cid, (u, v) in enumerate(coarse_nodes):
		vw_u = float(G.nodes[u].get('vweight', 1.0))
		# If unmatched (self-matched), don't double-count
		if v == u:
			vw = vw_u
		else:
			vw_v = float(G.nodes[v].get('vweight', 1.0))
			vw = vw_u + vw_v
		Gc.add_node(cid, vweight=vw)

	# Connect the coarse graph with the aggregated edge weights.
	for (cu, cv), w in agg.items():
		Gc.add_edge(cu, cv, **{weight: w})

	return Gc, coarse_label


def coarsen_chain(
	H, 
	trial_seed: int | None, 
	coarsen_limit: int = 50, 
	max_levels: int = 20, 
	weight: str = "weight",
	strategy: str = "sorted",
	coarsen_ratio: float = 0.80,
	max_node_weight: float | None = None
):
	"""
	Build coarsening chain with METIS-like improvements.
	
	Args:
		H: Input graph
		trial_seed: Random seed
		coarsen_limit: Minimum accepted coarse size. A new level is only kept if it
			still has at least this many nodes.
		max_levels: Maximum coarsening levels
		weight: Edge weight attribute
		strategy: Matching strategy ('random', 'sorted', 'modified', 'light')
		coarsen_ratio: Stop if reduction ratio < this (METIS uses ~0.7-0.85)
		max_node_weight: Maximum allowed supernode weight (None = no limit)
			Common heuristic: 1.5 * (total_weight / target_parts)
	
	Returns:
		graphs: List of graphs from fine to coarse [G0, G1, ..., Gc]
		maps: List of mappings [map0, map1, ...] where map[i] goes from G[i] -> G[i+1]
	"""
	graphs = [H]
	maps: list[dict] = []
	
	while graphs[-1].number_of_nodes() > coarsen_limit and len(graphs) < max_levels:
		G_prev = graphs[-1]
		n_prev = G_prev.number_of_nodes()
		
		Gc, label = coarsen_graph(G_prev, weight=weight, seed=trial_seed, strategy=strategy, max_node_weight=max_node_weight)
		n_coarse = Gc.number_of_nodes()

		if n_coarse < coarsen_limit:
			# Do not accept a coarsening level that would overshoot below the requested limit.
			break
		
		# Stop if a new level does not shrink enough to justify another refinement stage.
		reduction_ratio = n_coarse / n_prev if n_prev > 0 else 1.0
		
		if n_coarse >= n_prev:
			# No reduction - stop coarsening
			break
		
		if reduction_ratio > coarsen_ratio:
			# Insufficient reduction - stop to avoid creating too many levels
			# METIS typically stops when ratio > 0.8-0.85
			break
		
		graphs.append(Gc)
		maps.append(label)
	
	return graphs, maps