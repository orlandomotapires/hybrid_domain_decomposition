"""
Validation for Partition Lifting Phase (Step 5)
"""
import numpy as np


def validate_lifting_phase(original_graph, coarse_chain, coarse_partition, final_partition, maps=None, verbose=False):
    """
    Validate the partition lifting/projection from coarsest to finest level.
    
    Args:
        original_graph: Original finest-level graph (G_0)
        coarse_chain: List of coarsened graphs [G_1, G_2, ..., G_L] or [G_0, G_1, ..., G_L]
        coarse_partition: Partition on coarsest graph
        final_partition: Lifted partition on original graph
        maps: Optional list of mappings from coarsen_chain (for consistency checking)
        verbose: If True, print detailed validation steps
    
    Raises:
        ValueError: If any validation check fails
    """
    if verbose:
        print("=" * 80)
        print("STEP 5: PARTITION LIFTING VALIDATION")
        print("=" * 80)
    
    n_original = original_graph.number_of_nodes()
    
    # Check 1: Final partition covers all original nodes
    if verbose:
        print("✓ Checking final partition coverage...")
    
    if len(final_partition) != n_original:
        raise ValueError(f"❌ Final partition has {len(final_partition)} entries, expected {n_original}")
    
    original_nodes = set(original_graph.nodes())
    final_nodes = set(final_partition.keys())
    
    if original_nodes != final_nodes:
        missing = original_nodes - final_nodes
        extra = final_nodes - original_nodes
        raise ValueError(f"❌ Node coverage mismatch: {len(missing)} missing, {len(extra)} extra")
    
    if verbose:
        print(f"  ✓ Final partition covers all {n_original} original nodes")
    
    # Check 2: Partition IDs are consistent
    if verbose:
        print("✓ Checking partition ID consistency...")
    
    coarse_pids = set(coarse_partition.values())
    final_pids = set(final_partition.values())
    
    if final_pids != coarse_pids:
        # Allow subset (some partitions might be empty after lifting)
        if not final_pids.issubset(coarse_pids) and not coarse_pids.issubset(final_pids):
            raise ValueError(f"❌ Partition ID mismatch: coarse={coarse_pids}, final={final_pids}")
    
    if verbose:
        print(f"  ✓ Partition IDs consistent: {sorted(final_pids)}")
    
    # Check 3: Lifting is consistent with mapping
    if maps is not None and verbose:
        print("✓ Checking lifting consistency with node mapping...")
        
        # Build reverse mapping from coarsest to original
        # We need to trace back through all levels
        # Start with identity mapping at original level
        all_graphs = coarse_chain if coarse_chain[0].number_of_nodes() == original_graph.number_of_nodes() else [original_graph] + coarse_chain
        
        # Create mapping from original nodes to coarsest nodes
        orig_to_coarsest = {}
        for orig_node in original_graph.nodes():
            current_node = orig_node
            # Apply each mapping level
            for level_map in maps:
                if current_node in level_map:
                    current_node = level_map[current_node]
            orig_to_coarsest[orig_node] = current_node
        
        # Check that all original nodes mapped to same coarse node have same partition
        coarse_to_orig = {}
        for orig_node, coarse_node in orig_to_coarsest.items():
            if coarse_node not in coarse_to_orig:
                coarse_to_orig[coarse_node] = []
            coarse_to_orig[coarse_node].append(orig_node)
        
        for coarse_node, orig_nodes in coarse_to_orig.items():
            if coarse_node in coarse_partition:
                coarse_pid = coarse_partition[coarse_node]
                for orig_node in orig_nodes:
                    if final_partition[orig_node] != coarse_pid:
                        raise ValueError(
                            f"❌ Lifting inconsistency: original node {orig_node} "
                            f"(mapped to coarse node {coarse_node}, pid={coarse_pid}) "
                            f"has different partition {final_partition[orig_node]}"
                        )
        
        if verbose:
            print(f"  ✓ Lifting is consistent with node mapping for all {len(coarse_partition)} coarse nodes")
    elif verbose:
        print("✓ Skipping lifting consistency check (no maps provided)")
    
    # Check 4: Weight distribution preserved
    if verbose:
        print("✓ Checking weight distribution preservation...")
    
    # Determine coarsest graph
    if coarse_chain[0].number_of_nodes() == original_graph.number_of_nodes():
        coarsest_graph = coarse_chain[-1]
    else:
        coarsest_graph = coarse_chain[-1]
    
    # Compute weight distribution in coarse partition
    coarse_weights = {}
    for coarse_node, pid in coarse_partition.items():
        vw = coarsest_graph.nodes[coarse_node].get('vweight', 1.0)
        coarse_weights[pid] = coarse_weights.get(pid, 0.0) + vw
    
    # Compute weight distribution in final partition
    final_weights = {}
    for orig_node, pid in final_partition.items():
        vw = original_graph.nodes[orig_node].get('vweight', 1.0)
        final_weights[pid] = final_weights.get(pid, 0.0) + vw
    
    # Compare distributions (should be identical within numerical tolerance)
    for pid in coarse_weights.keys():
        coarse_w = coarse_weights.get(pid, 0.0)
        final_w = final_weights.get(pid, 0.0)
        
        if not np.isclose(coarse_w, final_w, rtol=1e-3):
            raise ValueError(
                f"❌ Weight mismatch for partition {pid}: "
                f"coarse={coarse_w:.2f}, final={final_w:.2f}"
            )
    
    if verbose:
        print(f"  ✓ Weight distribution preserved across lifting:")
        for pid in sorted(final_weights.keys()):
            print(f"    Partition {pid}: {final_weights[pid]:.2f}")
    
    # Check 5: Partition size distribution
    if verbose:
        print("✓ Checking final partition size distribution...")
    
    final_sizes = {}
    for pid in final_partition.values():
        final_sizes[pid] = final_sizes.get(pid, 0) + 1
    
    if verbose:
        print(f"  ✓ Final partition sizes: {dict(sorted(final_sizes.items()))}")
        total_weight = sum(final_weights.values())
        for pid in sorted(final_sizes.keys()):
            size_pct = final_sizes[pid] / n_original * 100
            weight_pct = final_weights[pid] / total_weight * 100
            print(f"    Partition {pid}: {final_sizes[pid]} nodes ({size_pct:.1f}%), weight {weight_pct:.1f}%")
    
    # Check 6: No empty partitions
    if verbose:
        print("✓ Checking for empty partitions...")
    
    if min(final_sizes.values()) == 0:
        raise ValueError("❌ Empty partition detected after lifting")
    
    if verbose:
        print(f"  ✓ No empty partitions (min size: {min(final_sizes.values())})")
    
    # Final success message
    print("✅ STEP 5 VALIDATION PASSED: Partition lifting is valid")
    if verbose:
        print("=" * 80)
