"""
Validation for Recursive Annealing Phase (Step 4)
"""
import numpy as np
import networkx as nx


def validate_anneal_bipartition(H: nx.Graph, partition: dict, balance_weight: float = 1.0, target_weight: float | None = None, weight: str = 'weight'):
    """
    Validate a 2-way partition produced by annealing.
    
    Args:
        H: Graph that was partitioned
        partition: Partition dict {node: 0|1}
        balance_weight: Weight λ for balance penalty term
        target_weight: Target weight T for partition 1 (default: 0.5 * total weight)
        weight: Edge weight attribute name (default: 'weight')
    
    Checks:
        1. Coverage: all nodes assigned
        2. Binary: only values 0 and 1
        3. Non-empty: both parts have nodes
        4. Cut calculation: verify edge cut
        5. Balance: check partition weights vs target
        6. Energy: verify QUBO energy matches cut + penalty
    
    Returns:
        Dict with cut, penalty, energy, balance metrics
    """
    from libs.multilevel_squeme.qubo_formulation import build_qubo_from_graph
    
    nodes = set(H.nodes())
    c = {u: float(H.nodes[u].get('vweight', 1.0)) for u in nodes}
    Ctot = float(sum(c.values()))
    T = Ctot * 0.5 if target_weight is None else float(target_weight)
    
    print(f"Validating annealing partition on graph |V|={len(nodes)}, |E|={H.number_of_edges()}")
    
    # 1. Coverage check
    part_nodes = set(partition.keys())
    assert part_nodes == nodes, f"Partition missing nodes: {nodes - part_nodes} or has extra: {part_nodes - nodes}"
    print(f"✓ All {len(nodes)} nodes assigned")
    
    # 2. Binary check
    values = set(partition.values())
    assert values.issubset({0, 1}), f"Non-binary values in partition: {values - {0, 1}}"
    print(f"✓ Binary partition (values: {sorted(values)})")
    
    # 3. Non-empty check
    part0 = {u for u, p in partition.items() if p == 0}
    part1 = {u for u, p in partition.items() if p == 1}
    assert len(part0) > 0 and len(part1) > 0, f"Empty partition: |part0|={len(part0)}, |part1|={len(part1)}"
    print(f"✓ Non-empty parts: |part0|={len(part0)}, |part1|={len(part1)}")
    
    # 4. Cut calculation
    cut = 0.0
    for u, v, data in H.edges(data=True):
        if partition[u] != partition[v]:
            cut += float(data.get(weight, 1.0))
    print(f"✓ Cut value: {cut:.4f}")
    
    # 5. Balance check
    w0 = sum(c[u] for u in part0)
    w1 = sum(c[u] for u in part1)
    imbalance = abs(w0 - T)
    balance_ratio = min(w0, w1) / max(w0, w1) if max(w0, w1) > 0 else 1.0
    print(f"✓ Partition weights: part0={w0:.2f}, part1={w1:.2f}, target={T:.2f}")
    print(f"  Imbalance: {imbalance:.2f}, Balance ratio: {balance_ratio:.4f}")
    
    # 6. Energy verification
    penalty = balance_weight * ((w0 - T) ** 2)
    expected_energy = cut + penalty
    
    # Also compute via QUBO matrix
    Q = build_qubo_from_graph(H, balance_weight=balance_weight, target_weight=target_weight)
    qubo_energy = balance_weight * (T ** 2)  # constant offset
    for (i, j), coef in Q.items():
        xi = partition[i]
        xj = partition[j]
        if i == j:
            qubo_energy += coef * xi
        else:
            qubo_energy += coef * xi * xj
    
    print(f"✓ Energy verification:")
    print(f"  Direct (cut + penalty): {expected_energy:.4f}")
    print(f"  QUBO evaluation: {qubo_energy:.4f}")
    
    energy_diff = abs(expected_energy - qubo_energy)
    assert energy_diff < 1e-3, f"Energy mismatch: {energy_diff:.6f}"
    print(f"  Match: {energy_diff:.2e}")
    
    print(f"\n✅ Annealing partition is VALID")
    print(f"   Cut={cut:.2f}, Penalty={penalty:.2f}, Total Energy={expected_energy:.2f}")
    
    return {
        'cut': cut,
        'penalty': penalty,
        'energy': expected_energy,
        'balance_ratio': balance_ratio,
        'imbalance': imbalance,
        'w0': w0,
        'w1': w1
    }


def validate_recursive_kway_partition(G: nx.Graph, partition: dict, k: int, weight: str = 'weight'):
    """
    Validate a k-way partition produced by recursive annealing.
    
    Args:
        G: Graph that was partitioned
        partition: Partition dict {node: label in [0, k-1]}
        k: Number of partitions
        weight: Edge weight attribute name (default: 'weight')
    
    Checks:
        1. Coverage: all nodes assigned exactly once
        2. Correct k: exactly k distinct partition labels
        3. Label range: labels in [0, k-1]
        4. Non-empty: all parts have at least one node
        5. Cut calculation: total edge weight crossing partitions
        6. Balance: weight distribution across parts
        7. Connectivity: check if parts are internally connected
    
    Returns:
        Dict with cut, part_weights, part_sizes, imbalance metrics
    """
    nodes = set(G.nodes())
    c = {u: float(G.nodes[u].get('vweight', 1.0)) for u in nodes}
    total_vweight = sum(c.values())
    target_per_part = total_vweight / k
    
    print(f"Validating k-way partition: k={k}, |V|={len(nodes)}, |E|={G.number_of_edges()}")
    
    # 1. Coverage check
    part_nodes = set(partition.keys())
    assert part_nodes == nodes, f"Partition missing {len(nodes - part_nodes)} nodes or has {len(part_nodes - nodes)} extra"
    print(f"✓ All {len(nodes)} nodes assigned")
    
    # 2. Correct number of parts
    labels = set(partition.values())
    assert len(labels) == k, f"Expected {k} parts, got {len(labels)}: {sorted(labels)}"
    print(f"✓ Exactly {k} distinct partitions")
    
    # 3. Label range check
    expected_labels = set(range(k))
    assert labels == expected_labels, f"Labels not in [0,{k-1}]: got {sorted(labels)}"
    print(f"✓ Labels in correct range [0, {k-1}]")
    
    # 4. Non-empty parts
    part_sizes = {lbl: sum(1 for n, p in partition.items() if p == lbl) for lbl in range(k)}
    empty_parts = [lbl for lbl, size in part_sizes.items() if size == 0]
    assert len(empty_parts) == 0, f"Empty partitions: {empty_parts}"
    print(f"✓ All parts non-empty: sizes = {[part_sizes[i] for i in range(k)]}")
    
    # 5. Cut calculation
    cut = 0.0
    internal_edges = {lbl: 0 for lbl in range(k)}
    for u, v, data in G.edges(data=True):
        w = float(data.get(weight, 1.0))
        if partition[u] == partition[v]:
            internal_edges[partition[u]] += 1
        else:
            cut += w
    print(f"✓ Total cut: {cut:.4f}")
    print(f"  Internal edges per part: {[internal_edges[i] for i in range(k)]}")
    
    # 6. Balance analysis
    part_weights = {lbl: sum(c[n] for n, p in partition.items() if p == lbl) for lbl in range(k)}
    weights_list = [part_weights[i] for i in range(k)]
    min_w, max_w = min(weights_list), max(weights_list)
    imbalance_ratio = max_w / min_w if min_w > 0 else float('inf')
    max_deviation = max(abs(w - target_per_part) for w in weights_list)
    
    print(f"✓ Balance analysis:")
    print(f"  Per-part weights: {[f'{w:.2f}' for w in weights_list]}")
    print(f"  Target per part: {target_per_part:.2f}")
    print(f"  Min: {min_w:.2f}, Max: {max_w:.2f}")
    print(f"  Imbalance ratio (max/min): {imbalance_ratio:.4f}")
    print(f"  Max deviation from target: {max_deviation:.2f}")
    
    # 7. Connectivity check (optional, can be slow for large graphs)
    if len(nodes) <= 1000:  # only for reasonably sized graphs
        disconnected_parts = []
        for lbl in range(k):
            part_nodes_set = {n for n, p in partition.items() if p == lbl}
            subG = G.subgraph(part_nodes_set)
            if not nx.is_connected(subG):
                disconnected_parts.append(lbl)
        
        if disconnected_parts:
            print(f"⚠ Disconnected parts: {disconnected_parts} (may be acceptable)")
        else:
            print(f"✓ All parts are internally connected")
    else:
        print(f"⚠ Connectivity check skipped (graph too large)")
    
    print(f"\n✅ K-way partition is VALID")
    print(f"   Cut={cut:.2f}, Imbalance ratio={imbalance_ratio:.4f}")
    
    return {
        'cut': cut,
        'part_weights': weights_list,
        'part_sizes': [part_sizes[i] for i in range(k)],
        'imbalance_ratio': imbalance_ratio,
        'max_deviation': max_deviation,
        'internal_edges': [internal_edges[i] for i in range(k)]
    }


def validate_recursive_annealing_phase(graph, partition, num_partitions, verbose=False):
    """
    Validate the result of recursive quantum annealing partitioning.
    
    Args:
        graph: Graph that was partitioned
        partition: Dict mapping node_id -> partition_id
        num_partitions: Expected number of partitions (k)
        verbose: If True, print detailed validation steps
    
    Raises:
        ValueError: If any validation check fails
    """
    if verbose:
        print("=" * 80)
        print("STEP 4: RECURSIVE ANNEALING VALIDATION")
        print("=" * 80)
    
    n_nodes = graph.number_of_nodes()
    
    # Check 1: Partition dict structure
    if verbose:
        print("✓ Checking partition structure...")
    
    if not isinstance(partition, dict):
        raise ValueError(f"❌ Partition must be dict, got {type(partition)}")
    
    if len(partition) != n_nodes:
        raise ValueError(f"❌ Partition has {len(partition)} entries, expected {n_nodes} nodes")
    
    if verbose:
        print(f"  ✓ Partition dict has {len(partition)} entries (matches graph nodes)")
    
    # Check 2: All graph nodes are in partition
    if verbose:
        print("✓ Checking node coverage...")
    
    graph_nodes = set(graph.nodes())
    partition_nodes = set(partition.keys())
    
    if graph_nodes != partition_nodes:
        missing = graph_nodes - partition_nodes
        extra = partition_nodes - graph_nodes
        raise ValueError(f"❌ Node coverage mismatch: {len(missing)} missing, {len(extra)} extra")
    
    if verbose:
        print(f"  ✓ All {n_nodes} graph nodes present in partition")
    
    # Check 3: Partition IDs are valid
    if verbose:
        print("✓ Checking partition IDs...")
    
    partition_ids = set(partition.values())
    expected_ids = set(range(num_partitions))
    
    # All partition IDs should be in [0, k-1]
    invalid_ids = partition_ids - expected_ids
    if invalid_ids:
        raise ValueError(f"❌ Invalid partition IDs found: {invalid_ids} (expected [0, {num_partitions-1}])")
    
    # Check if all expected partitions are used (some may be empty for small graphs)
    if len(partition_ids) < num_partitions:
        if verbose:
            print(f"  ⚠ Warning: Only {len(partition_ids)} partitions used out of {num_partitions} expected")
    
    if verbose:
        print(f"  ✓ All partition IDs are valid: {sorted(partition_ids)}")
    
    # Check 4: Partition size distribution
    if verbose:
        print("✓ Checking partition size distribution...")
    
    partition_sizes = {}
    for node, pid in partition.items():
        partition_sizes[pid] = partition_sizes.get(pid, 0) + 1
    
    sizes = list(partition_sizes.values())
    min_size = min(sizes)
    max_size = max(sizes)
    avg_size = np.mean(sizes)
    
    if min_size == 0:
        raise ValueError(f"❌ Empty partition detected")
    
    if verbose:
        print(f"  ✓ Partition sizes: {dict(sorted(partition_sizes.items()))}")
        print(f"  ✓ Size stats: min={min_size}, max={max_size}, avg={avg_size:.1f}")
    
    # Check 5: Weight distribution across partitions
    if verbose:
        print("✓ Checking weight distribution...")
    
    partition_weights = {}
    for node, pid in partition.items():
        vw = graph.nodes[node].get('vweight', 1.0)
        partition_weights[pid] = partition_weights.get(pid, 0.0) + vw
    
    total_weight = sum(partition_weights.values())
    weight_pcts = {pid: w/total_weight*100 for pid, w in partition_weights.items()}
    
    if verbose:
        print(f"  ✓ Partition weights: {dict(sorted(partition_weights.items()))}")
        print(f"  ✓ Weight percentages: {dict(sorted({pid: f'{pct:.1f}%' for pid, pct in weight_pcts.items()}.items()))}")
    
    # Check if weights are extremely unbalanced (>95% in one partition)
    max_weight_pct = max(weight_pcts.values())
    if max_weight_pct > 95.0:
        raise ValueError(f"❌ Extremely unbalanced partition: {max_weight_pct:.1f}% in one partition")
    
    # Check 6: Cut edges (edges crossing partitions)
    if verbose:
        print("✓ Checking cut edges...")
    
    cut_edges = 0
    cut_weight = 0.0
    total_edge_weight = 0.0
    
    for u, v, data in graph.edges(data=True):
        w = data.get('weight', 1.0)
        total_edge_weight += w
        if partition[u] != partition[v]:
            cut_edges += 1
            cut_weight += w
    
    if verbose:
        if total_edge_weight > 0:
            cut_pct = cut_weight / total_edge_weight * 100
            print(f"  ✓ Cut edges: {cut_edges} / {graph.number_of_edges()} ({cut_pct:.1f}% of total weight)")
        else:
            print(f"  ⚠ Graph has no edges (disconnected)")
    
    # Final success message
    print("✅ STEP 4 VALIDATION PASSED: Recursive annealing partition is valid")
    if verbose:
        print("=" * 80)
