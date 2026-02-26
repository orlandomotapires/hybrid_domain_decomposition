"""
Validation for Matrix to Graph Conversion (Step 1)
"""
import numpy as np
import networkx as nx
from scipy.sparse import issparse


def validate_matrix_to_graph(matrix_k, matrix_m, graph_k, diag_k, verbose=False):
    """
    Validate the matrix-to-graph conversion step.
    
    Args:
        matrix_k: Original K sparse matrix
        matrix_m: Original M sparse matrix (can be None)
        graph_k: Converted NetworkX graph from K matrix
        diag_k: Diagonal values used for node weights
        verbose: If True, print detailed validation steps
    
    Raises:
        ValueError: If any validation check fails
    """
    if verbose:
        print("=" * 80)
        print("STEP 1: MATRIX TO GRAPH CONVERSION VALIDATION")
        print("=" * 80)
    
    # Check 1: Matrix is sparse and valid
    if verbose:
        print("✓ Checking matrix format...")
    if not issparse(matrix_k):
        raise ValueError("❌ K matrix must be sparse format")
    if matrix_k.shape[0] != matrix_k.shape[1]:
        raise ValueError(f"❌ K matrix must be square, got shape {matrix_k.shape}")
    if verbose:
        print(f"  ✓ K matrix is sparse: shape={matrix_k.shape}, nnz={matrix_k.nnz}")
    
    if matrix_m is not None:
        if not issparse(matrix_m):
            raise ValueError("❌ M matrix must be sparse format")
        if matrix_m.shape != matrix_k.shape:
            raise ValueError(f"❌ M and K matrices must have same shape: K={matrix_k.shape}, M={matrix_m.shape}")
        if verbose:
            print(f"  ✓ M matrix is sparse: shape={matrix_m.shape}, nnz={matrix_m.nnz}")
    
    # Check 2: Graph structure matches matrix
    if verbose:
        print("✓ Checking graph structure...")
    expected_nodes = matrix_k.shape[0]
    actual_nodes = graph_k.number_of_nodes()
    if actual_nodes != expected_nodes:
        raise ValueError(f"❌ Graph nodes ({actual_nodes}) != matrix size ({expected_nodes})")
    if verbose:
        print(f"  ✓ Graph has correct number of nodes: {actual_nodes}")
    
    # Check 3: Node IDs are valid
    if verbose:
        print("✓ Checking node IDs...")
    node_ids = set(graph_k.nodes())
    expected_ids = set(range(expected_nodes))
    if node_ids != expected_ids:
        raise ValueError(f"❌ Graph node IDs do not match expected range [0, {expected_nodes-1}]")
    if verbose:
        print(f"  ✓ Node IDs are sequential: [0, {expected_nodes-1}]")
    
    # Check 4: Node weights (vweight) are present and valid
    if verbose:
        print("✓ Checking node weights (vweight)...")
    missing_vweight = [n for n in graph_k.nodes() if 'vweight' not in graph_k.nodes[n]]
    if missing_vweight:
        raise ValueError(f"❌ {len(missing_vweight)} nodes missing 'vweight' attribute")
    
    # Verify vweights match diagonal
    for node in graph_k.nodes():
        vw = graph_k.nodes[node]['vweight']
        expected_vw = abs(diag_k[node])
        if not np.isclose(vw, expected_vw, rtol=1e-5):
            raise ValueError(f"❌ Node {node} vweight mismatch: {vw} != {expected_vw}")
    if verbose:
        print(f"  ✓ All {actual_nodes} nodes have valid vweight from diagonal")
        vweights = [graph_k.nodes[n]['vweight'] for n in graph_k.nodes()]
        print(f"  ✓ vweight range: [{min(vweights):.2f}, {max(vweights):.2f}]")
    
    # Check 5: Edge weights are present and positive
    if verbose:
        print("✓ Checking edge weights...")
    for u, v, data in graph_k.edges(data=True):
        if 'weight' not in data:
            raise ValueError(f"❌ Edge ({u}, {v}) missing 'weight' attribute")
        w = data['weight']
        if w < 0:
            raise ValueError(f"❌ Edge ({u}, {v}) has negative weight: {w}")
    if verbose:
        edge_weights = [data['weight'] for u, v, data in graph_k.edges(data=True)]
        if edge_weights:
            print(f"  ✓ All {len(edge_weights)} edges have positive weights")
            print(f"  ✓ Edge weight range: [{min(edge_weights):.2f}, {max(edge_weights):.2f}]")
        else:
            print(f"  ⚠ Graph has no edges (isolated nodes)")
    
    # Check 6: Graph is undirected
    if verbose:
        print("✓ Checking graph type...")
    if graph_k.is_directed():
        raise ValueError("❌ Graph must be undirected")
    if verbose:
        print(f"  ✓ Graph is undirected")
    
    # Check 7: No self-loops (diagonal was dropped)
    if verbose:
        print("✓ Checking for self-loops...")
    self_loops = list(nx.selfloop_edges(graph_k))
    if self_loops:
        raise ValueError(f"❌ Graph contains {len(self_loops)} self-loops (diagonal should be dropped)")
    if verbose:
        print(f"  ✓ No self-loops present (diagonal correctly dropped)")
    
    # Final success message
    print("✅ STEP 1 VALIDATION PASSED: Matrix to Graph conversion is valid")
    if verbose:
        print("=" * 80)
