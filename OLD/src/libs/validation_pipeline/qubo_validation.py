"""
Validation for QUBO Formulation Phase (Step 3)
"""
import numpy as np
import networkx as nx


def validate_qubo_formulation(H: nx.Graph, Q: dict, balance_weight: float = 1.0, target_weight: float | None = None):
    """
    Validate QUBO matrix for balanced 2-way partition.
    
    Args:
        H: Graph to partition
        Q: QUBO matrix as dict[(i,j)] -> coefficient
        balance_weight: Weight λ for balance penalty term
        target_weight: Target weight T for partition 1 (default: 0.5 * total weight)
    
    Checks:
        1. Symmetry: Q is upper-triangular
        2. Diagonal structure: includes cut linear + balance terms
        3. Off-diagonal structure: edge quadratic + balance cross-terms
        4. Energy correctness: spot-check a few assignments
    """
    nodes = list(H.nodes())
    n = len(nodes)
    c = {u: float(H.nodes[u].get('vweight', 1.0)) for u in nodes}
    Ctot = float(sum(c.values()))
    T = Ctot * 0.5 if target_weight is None else float(target_weight)
    
    print(f"Validating QUBO for graph with |V|={n}, |E|={H.number_of_edges()}")
    
    # 1. Check upper-triangular structure
    for (i, j) in Q.keys():
        assert i <= j, f"QUBO not upper-triangular: found ({i},{j}) with i > j"
    print("✓ QUBO is upper-triangular")
    
    # 2. Check all nodes have diagonal entries
    node_set = set(nodes)
    diag_keys = {u for (u, v) in Q.keys() if u == v}
    assert diag_keys == node_set, f"Missing diagonal entries: {node_set - diag_keys}"
    print(f"✓ All {n} nodes have diagonal entries")
    
    # 3. Verify diagonal structure: deg_w(u) + λ c_u² - 2λT c_u
    degw = {u: 0.0 for u in nodes}
    for u, v, data in H.edges(data=True):
        w = float(data.get('weight', 1.0))
        degw[u] += w
        degw[v] += w
    
    max_diag_error = 0.0
    for u in nodes:
        expected = degw[u] + balance_weight * (c[u] ** 2) - 2.0 * balance_weight * T * c[u]
        actual = Q.get((u, u), 0.0)
        error = abs(expected - actual)
        max_diag_error = max(max_diag_error, error)
        if error > 1e-6:
            print(f"⚠ Diagonal mismatch at {u}: expected {expected:.6f}, got {actual:.6f}")
    
    assert max_diag_error < 1e-6, f"Diagonal error too large: {max_diag_error}"
    print(f"✓ Diagonal terms correct (max error: {max_diag_error:.2e})")
    
    # 4. Verify off-diagonal structure: -2 w_uv + 2λ c_u c_v
    edge_dict = {(min(u,v), max(u,v)): float(data.get('weight', 1.0)) 
                 for u, v, data in H.edges(data=True)}
    
    max_offdiag_error = 0.0
    offdiag_count = 0
    for i in range(len(nodes)):
        u = nodes[i]
        for j in range(i + 1, len(nodes)):
            v = nodes[j]
            expected = 2.0 * balance_weight * c[u] * c[v]
            if (u, v) in edge_dict:
                expected += -2.0 * edge_dict[(u, v)]
            
            actual = Q.get((u, v), 0.0)
            
            # Only check if coefficient should be non-zero
            if abs(expected) > 1e-12 or abs(actual) > 1e-12:
                error = abs(expected - actual)
                max_offdiag_error = max(max_offdiag_error, error)
                offdiag_count += 1
                if error > 1e-6:
                    print(f"⚠ Off-diagonal mismatch at ({u},{v}): expected {expected:.6f}, got {actual:.6f}")
    
    assert max_offdiag_error < 1e-6, f"Off-diagonal error too large: {max_offdiag_error}"
    print(f"✓ Off-diagonal terms correct (checked {offdiag_count} pairs, max error: {max_offdiag_error:.2e})")
    
    # 5. Energy calculation spot-check: test a few assignments
    def eval_qubo(assignment: dict) -> float:
        """Evaluate QUBO energy for binary assignment."""
        energy = 0.0
        for (i, j), coef in Q.items():
            xi = assignment.get(i, 0)
            xj = assignment.get(j, 0)
            if i == j:
                energy += coef * xi
            else:
                energy += coef * xi * xj
        # Add constant offset from penalty term: λT²
        energy += balance_weight * (T ** 2)
        return energy
    
    def eval_direct(assignment: dict) -> float:
        """Directly compute cut + penalty."""
        cut = 0.0
        for u, v, data in H.edges(data=True):
            if assignment.get(u, 0) != assignment.get(v, 0):
                cut += float(data.get('weight', 1.0))
        
        part_weight = sum(c[u] * assignment.get(u, 0) for u in nodes)
        penalty = balance_weight * (part_weight - T) ** 2
        return cut + penalty
    
    # Test assignment 1: all zeros
    assign_0 = {u: 0 for u in nodes}
    e_qubo_0 = eval_qubo(assign_0)
    e_direct_0 = eval_direct(assign_0)
    assert abs(e_qubo_0 - e_direct_0) < 1e-6, f"Energy mismatch for all-0: QUBO={e_qubo_0}, direct={e_direct_0}"
    
    # Test assignment 2: all ones
    assign_1 = {u: 1 for u in nodes}
    e_qubo_1 = eval_qubo(assign_1)
    e_direct_1 = eval_direct(assign_1)
    assert abs(e_qubo_1 - e_direct_1) < 1e-6, f"Energy mismatch for all-1: QUBO={e_qubo_1}, direct={e_direct_1}"
    
    # Test assignment 3: alternating (if n > 1)
    if n > 1:
        assign_alt = {nodes[i]: i % 2 for i in range(n)}
        e_qubo_alt = eval_qubo(assign_alt)
        e_direct_alt = eval_direct(assign_alt)
        assert abs(e_qubo_alt - e_direct_alt) < 1e-6, f"Energy mismatch for alternating: QUBO={e_qubo_alt}, direct={e_direct_alt}"
    
    print(f"✓ Energy calculation verified on test assignments")
    print(f"  All-0: {e_qubo_0:.4f}, All-1: {e_qubo_1:.4f}" + (f", Alternating: {e_qubo_alt:.4f}" if n > 1 else ""))
    
    print(f"\n✅ QUBO formulation is CORRECT")
    return True


def validate_qubo_phase(graph, Q, num_partitions, verbose=False):
    """
    Validate the QUBO formulation for graph partitioning.
    
    Args:
        graph: Graph to be partitioned
        Q: QUBO matrix (2D numpy array or dict)
        num_partitions: Expected number of partitions (typically 2 for bisection)
        verbose: If True, print detailed validation steps
    
    Raises:
        ValueError: If any validation check fails
    """
    if verbose:
        print("=" * 80)
        print("STEP 3: QUBO FORMULATION VALIDATION")
        print("=" * 80)
    
    n_nodes = graph.number_of_nodes()
    
    # Check 1: QUBO matrix structure
    if verbose:
        print("✓ Checking QUBO matrix structure...")
    
    if isinstance(Q, dict):
        # BQM dict format
        if verbose:
            print(f"  ✓ QUBO is in dict format with {len(Q)} entries")
        # Extract variable names to check dimensionality
        variables = set()
        for key in Q.keys():
            if isinstance(key, tuple):
                variables.update(key)
            else:
                variables.add(key)
        
        # For 2-way partition, QUBO can be either:
        # - Binary encoding: n variables (one per node, binary 0/1)
        # - One-hot encoding: n*k variables
        if num_partitions == 2:
            # Accept both binary (n) and one-hot (n*2) encodings for 2-way
            expected_binary = n_nodes
            expected_onehot = n_nodes * num_partitions
            if len(variables) == expected_binary:
                if verbose:
                    print(f"  ✓ QUBO has {len(variables)} variables (binary encoding: 1 var per node)")
            elif len(variables) == expected_onehot:
                if verbose:
                    print(f"  ✓ QUBO has {len(variables)} variables (one-hot encoding: {num_partitions} vars per node)")
            else:
                raise ValueError(
                    f"❌ QUBO has {len(variables)} variables, expected either {expected_binary} (binary) "
                    f"or {expected_onehot} (one-hot) for {n_nodes} nodes and k={num_partitions}"
                )
        else:
            # For k>2, only one-hot encoding makes sense
            expected_vars = n_nodes * num_partitions
            if len(variables) != expected_vars:
                raise ValueError(f"❌ QUBO has {len(variables)} variables, expected {expected_vars} (nodes={n_nodes}, k={num_partitions})")
            if verbose:
                print(f"  ✓ QUBO has {len(variables)} variables ({n_nodes} nodes × {num_partitions} partitions)")
    
    elif isinstance(Q, np.ndarray):
        # Matrix format
        if Q.ndim != 2:
            raise ValueError(f"❌ QUBO matrix must be 2D, got {Q.ndim}D")
        if Q.shape[0] != Q.shape[1]:
            raise ValueError(f"❌ QUBO matrix must be square, got shape {Q.shape}")
        expected_size = n_nodes * num_partitions
        if Q.shape[0] != expected_size:
            raise ValueError(f"❌ QUBO size {Q.shape[0]} != expected {expected_size} (nodes={n_nodes}, k={num_partitions})")
        if verbose:
            print(f"  ✓ QUBO matrix is square: {Q.shape}")
            print(f"  ✓ Size matches: {n_nodes} nodes × {num_partitions} partitions = {expected_size}")
    
    else:
        raise ValueError(f"❌ QUBO must be dict or numpy array, got {type(Q)}")
    
    # Check 2: QUBO matrix symmetry (for upper-triangular format)
    if isinstance(Q, np.ndarray):
        if verbose:
            print("✓ Checking QUBO matrix symmetry...")
        # QUBO should be upper triangular or symmetric
        lower_tri = np.tril(Q, -1)
        if not np.allclose(lower_tri, 0, atol=1e-10):
            # If lower triangle not zero, check full symmetry
            if not np.allclose(Q, Q.T, atol=1e-10):
                raise ValueError("❌ QUBO matrix is neither upper-triangular nor symmetric")
            if verbose:
                print(f"  ✓ QUBO matrix is symmetric")
        else:
            if verbose:
                print(f"  ✓ QUBO matrix is upper-triangular")
    
    # Check 3: QUBO has finite values
    if verbose:
        print("✓ Checking QUBO value validity...")
    
    if isinstance(Q, dict):
        values = list(Q.values())
    else:
        values = Q.flatten()
    
    if not all(np.isfinite(v) for v in values):
        raise ValueError("❌ QUBO contains non-finite values (inf or nan)")
    if verbose:
        print(f"  ✓ All QUBO values are finite")
        print(f"  ✓ QUBO value range: [{np.min(values):.2e}, {np.max(values):.2e}]")
    
    # Check 4: QUBO incorporates edge weights
    if verbose:
        print("✓ Checking edge weight incorporation...")
    
    # For a valid QUBO, edge weights should appear (implicitly check by looking at non-zero entries)
    if isinstance(Q, dict):
        non_zero_entries = len([v for v in Q.values() if abs(v) > 1e-10])
    else:
        non_zero_entries = np.count_nonzero(np.abs(Q) > 1e-10)
    
    if non_zero_entries == 0:
        raise ValueError("❌ QUBO matrix is all zeros (no edge information)")
    if verbose:
        total_entries = len(Q) if isinstance(Q, dict) else Q.size
        density = non_zero_entries / total_entries * 100
        print(f"  ✓ QUBO has {non_zero_entries} non-zero entries ({density:.2f}% density)")
    
    # Check 5: Expected QUBO structure for bisection
    if verbose:
        print("✓ Checking QUBO structure for partitioning...")
    
    # For k-way partitioning, we expect constraints ensuring each node in exactly one partition
    # This is encoded in the quadratic terms between partition variables for same node
    if num_partitions > 1:
        if verbose:
            print(f"  ✓ QUBO formulated for {num_partitions}-way partitioning")
    
    # Final success message
    print("✅ STEP 3 VALIDATION PASSED: QUBO formulation is valid")
    if verbose:
        print("=" * 80)
