"""
Validation for Coarsening Phase (Step 2)
"""
import networkx as nx


def validate_coarsening_chain(graphs: list, maps: list, weight: str = "weight"):
    """
    Validate entire coarsening chain: check each level preserves weights.
    
    Args:
        graphs: List of graphs where graphs[0] = original, graphs[-1] = coarsest
        maps: List of mappings where maps[i] = fine->coarse mapping from graphs[i] to graphs[i+1]
        weight: Edge weight attribute name (default: 'weight')
    
    Checks:
        - Node weight (vweight) conservation at each level
        - Edge weight conservation (excluding internal edges in collapsed pairs)
    """
    print(f"Validating coarsening chain: {len(graphs)} levels")
    
    # Check each consecutive pair
    for i in range(len(maps)):
        G_fine = graphs[i]
        G_coarse = graphs[i + 1]
        label = maps[i]
        
        # Validate this step
        orig_vw = sum(G_fine.nodes[u].get('vweight', 1.0) for u in G_fine.nodes())
        coarse_vw = sum(G_coarse.nodes[c].get('vweight', 1.0) for c in G_coarse.nodes())
        assert abs(orig_vw - coarse_vw) < 1e-9, f"Level {i}: vweight mismatch: {orig_vw} vs {coarse_vw}"
        
        # Edge weight sum (excluding internal edges in collapsed pairs)
        orig_ew = sum(abs(data.get(weight, 1.0)) for u, v, data in G_fine.edges(data=True) if label[u] != label[v])
        coarse_ew = sum(abs(data.get(weight, 1.0)) for u, v, data in G_coarse.edges(data=True))
        assert abs(orig_ew - coarse_ew) < 1e-6, f"Level {i}: edge weight mismatch: {orig_ew} vs {coarse_ew}"
    
    print(f"✓ All {len(maps)} coarsening levels preserve weights")
    print(f"  Original: |V|={graphs[0].number_of_nodes()}, |E|={graphs[0].number_of_edges()}")
    print(f"  Coarsest: |V|={graphs[-1].number_of_nodes()}, |E|={graphs[-1].number_of_edges()}")


def validate_coarsening_phase(original_graph, coarse_chain, maps=None, verbose=False):
    """
    Validate the coarsening phase and resulting graph hierarchy.
    
    Args:
        original_graph: Original finest-level graph (G_0)
        coarse_chain: List of coarsened graphs [G_1, G_2, ..., G_L] or [G_0, G_1, G_2, ..., G_L]
        maps: Optional list of mappings (coarse_label dicts) from coarsen_chain
        verbose: If True, print detailed validation steps
    
    Raises:
        ValueError: If any validation check fails
    """
    if verbose:
        print("=" * 80)
        print("STEP 2: COARSENING PHASE VALIDATION")
        print("=" * 80)
    
    # Check 1: Coarse chain is not empty
    if verbose:
        print("✓ Checking coarse chain structure...")
    if not coarse_chain:
        raise ValueError("❌ Coarse chain is empty")
    if verbose:
        print(f"  ✓ Coarse chain has {len(coarse_chain)} levels")
    
    # Check if coarse_chain already includes original graph as first element
    if coarse_chain[0].number_of_nodes() == original_graph.number_of_nodes():
        # coarse_chain includes original graph
        all_graphs = coarse_chain
        if verbose:
            print(f"  ✓ Coarse chain includes original graph as first level")
    else:
        # coarse_chain only has coarsened levels
        all_graphs = [original_graph] + coarse_chain
        if verbose:
            print(f"  ✓ Prepending original graph to coarse chain")
    
    # Check 2: Each level is smaller than previous
    if verbose:
        print("✓ Checking coarsening progression...")
    for i in range(len(all_graphs) - 1):
        n_curr = all_graphs[i].number_of_nodes()
        n_next = all_graphs[i+1].number_of_nodes()
        if n_next >= n_curr:
            raise ValueError(f"❌ Level {i+1} has {n_next} nodes >= level {i} ({n_curr} nodes)")
        reduction = (n_curr - n_next) / n_curr * 100
        if verbose:
            print(f"  ✓ Level {i} → {i+1}: {n_curr} → {n_next} nodes ({reduction:.1f}% reduction)")
    
    # Check 3: Node weights are preserved through coarsening
    if verbose:
        print("✓ Checking total weight preservation...")
    
    # Compute total weight at each level
    total_weights = []
    for g in all_graphs:
        total_vw = sum(g.nodes[n].get('vweight', 1.0) for n in g.nodes())
        total_weights.append(total_vw)
    
    original_weight = total_weights[0]
    for i, tw in enumerate(total_weights[1:], start=1):
        if not abs(tw - original_weight) < 1e-3 * original_weight:  # 0.1% tolerance
            raise ValueError(f"❌ Level {i} total weight {tw:.2f} differs from original {original_weight:.2f}")
        if verbose:
            diff_pct = abs(tw - original_weight) / original_weight * 100
            print(f"  ✓ Level {i}: total_vweight={tw:.2f} (diff: {diff_pct:.3f}%)")
    
    # Check 4: Validate node coverage using maps if provided
    if maps is not None and verbose:
        print("✓ Checking node mapping coverage...")
        # maps[i] maps from level i to level i+1
        for i, label_map in enumerate(maps):
            # Check that all nodes at level i are mapped
            level_i_nodes = set(all_graphs[i].nodes())
            mapped_nodes = set(label_map.keys())
            if level_i_nodes != mapped_nodes:
                missing = level_i_nodes - mapped_nodes
                raise ValueError(f"❌ Level {i}: {len(missing)} nodes not mapped to next level")
            if verbose:
                coarse_labels = set(label_map.values())
                print(f"  ✓ Level {i} → {i+1}: {len(mapped_nodes)} nodes mapped to {len(coarse_labels)} coarse nodes")
    
    # Check 5: Edge weights are reasonable (not negative)
    if verbose:
        print("✓ Checking edge weights at each level...")
    for level_idx, g in enumerate(all_graphs):
        for u, v, data in g.edges(data=True):
            w = data.get('weight', 1.0)
            if w < 0:
                raise ValueError(f"❌ Level {level_idx} edge ({u}, {v}) has negative weight: {w}")
        if verbose:
            edge_weights = [data.get('weight', 1.0) for u, v, data in g.edges(data=True)]
            if edge_weights:
                print(f"  ✓ Level {level_idx}: {len(edge_weights)} edges, weight range [{min(edge_weights):.2f}, {max(edge_weights):.2f}]")
            else:
                print(f"  ⚠ Level {level_idx}: No edges (graph might be disconnected components)")
    
    # Final success message
    print("✅ STEP 2 VALIDATION PASSED: Coarsening phase is valid")
    if verbose:
        print("=" * 80)
