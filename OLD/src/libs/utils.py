from scipy.io import mmread
import scipy.sparse as sp
import numpy as np
import networkx as nx

def load_mtx(filename, target_name):
    """
    Load a Matrix Market (MTX) file and return a scipy.sparse.csr_matrix.
    Falls back to converting dense arrays to CSR. Prints shape and nnz.
    """
    try:
        M = mmread(filename)
    except Exception as e:
        print(f"Error loading {filename}: {e}. Ensure SciPy is installed.")
        return None

    if sp.issparse(M):
        A = M.tocsr()
    else:
        A = sp.csr_matrix(np.asarray(M))

    print(f"Loaded: {target_name} | shape={A.shape}, nnz={A.nnz}")
    return A


def matrix_to_graph(
    A,
    *,
    directed=False,
    symmetrize='auto',
    drop_diagonal=True,
    threshold=0.0,
    abs_weights=False,
    node_vweight: str | None = None,  # 'degree' | 'diag' | None
    diag: np.ndarray | None = None,
    dof_per_node: int = 1,
):
    """
    Convert a matrix A (sparse or dense) into a NetworkX graph.
    If dof_per_node > 1, aggregate DOF blocks into node-level adjacency, ensuring
    graph partitioning is performed at node granularity (preserving FEM physics).
    - directed: create DiGraph if True, else Graph
    - symmetrize: 'auto'|'max'|'sum'|'avg'|'none'
    - drop_diagonal: remove self-loops
    - threshold: drop edges with |weight| < threshold
    Returns a NetworkX graph with edge attribute 'weight'.
    """
    if A is None:
        return None

    if not sp.issparse(A):
        A = sp.csr_matrix(A)
    A = A.asformat('csr')

    d = int(dof_per_node) if dof_per_node is not None else 1

    if d <= 1:
        # Original scalar-DOF path
        # Symmetrization
        if symmetrize == 'auto':
            if (A - A.T).nnz != 0:
                A = A.maximum(A.T)
        elif symmetrize == 'max':
            A = A.maximum(A.T)
        elif symmetrize == 'sum':
            A = A + A.T
        elif symmetrize == 'avg':
            A = (A + A.T) * 0.5
        elif symmetrize == 'none':
            pass

        if drop_diagonal:
            A.setdiag(0)
            A.eliminate_zeros()

        if abs_weights:
            C = A.tocoo()
            C.data = np.abs(C.data)
            A = C.tocsr()

        if threshold and threshold > 0:
            C = A.tocoo()
            mask = np.abs(C.data) >= threshold
            A = sp.coo_matrix((C.data[mask], (C.row[mask], C.col[mask])), shape=C.shape).tocsr()

        Gtype = nx.DiGraph if directed else nx.Graph
        try:
            G = nx.from_scipy_sparse_array(A, create_using=Gtype, edge_attribute='weight')
        except AttributeError:
            G = nx.from_scipy_sparse_matrix(A, create_using=Gtype, edge_attribute='weight')

        if node_vweight:
            if node_vweight == 'degree':
                degrees = np.ravel(A.sum(axis=1))
                for i, u in enumerate(G.nodes()):
                    G.nodes[u]['vweight'] = float(degrees[i])
            elif node_vweight == 'diag':
                if diag is None:
                    dvec = A.diagonal()
                else:
                    dvec = np.asarray(diag).ravel()
                for i, u in enumerate(G.nodes()):
                    G.nodes[u]['vweight'] = float(dvec[i])
        return G

    # DOF-aggregating path (build node-level graph of size N x N)
    N_total = A.shape[0]
    if N_total % d != 0:
        raise ValueError(
            f"matrix_to_graph: shape[0]={N_total} is not divisible by dof_per_node={d}"
        )
    N = N_total // d

    C = A.tocoo()

    # Optionally take absolute values before aggregation (consistent with scalar path)
    values = np.abs(C.data) if abs_weights else C.data
    node_row = (C.row // d).astype(int)
    node_col = (C.col // d).astype(int)

    # Build aggregated node-level adjacency by summing DOF-coupling magnitudes per node pair
    B = sp.coo_matrix((values, (node_row, node_col)), shape=(N, N)).tocsr()

    # Symmetrize at node level
    if symmetrize == 'auto':
        if (B - B.T).nnz != 0:
            B = B.maximum(B.T)
    elif symmetrize == 'max':
        B = B.maximum(B.T)
    elif symmetrize == 'sum':
        B = B + B.T
    elif symmetrize == 'avg':
        B = (B + B.T) * 0.5
    elif symmetrize == 'none':
        pass

    # Drop self-loops at node level
    if drop_diagonal:
        B.setdiag(0)
        B.eliminate_zeros()

    # Thresholding at node level
    if threshold and threshold > 0:
        Cb = B.tocoo()
        mask = np.abs(Cb.data) >= threshold
        B = sp.coo_matrix((Cb.data[mask], (Cb.row[mask], Cb.col[mask])), shape=Cb.shape).tocsr()

    Gtype = nx.DiGraph if directed else nx.Graph
    try:
        G = nx.from_scipy_sparse_array(B, create_using=Gtype, edge_attribute='weight')
    except AttributeError:
        G = nx.from_scipy_sparse_matrix(B, create_using=Gtype, edge_attribute='weight')

    # Assign node weights if requested
    if node_vweight:
        if node_vweight == 'degree':
            degrees = np.ravel(B.sum(axis=1))
            for i, u in enumerate(G.nodes()):
                G.nodes[u]['vweight'] = float(degrees[i])
        elif node_vweight == 'diag':
            # Aggregate diagonal entries per node (trace of each node block)
            if diag is None:
                dvec = A.diagonal()
            else:
                dvec = np.asarray(diag).ravel()
            if len(dvec) != N_total:
                raise ValueError(
                    f"diag length {len(dvec)} does not match matrix size {N_total}"
                )
            node_diag = np.add.reduceat(dvec, np.arange(0, N_total, d))
            for i, u in enumerate(G.nodes()):
                G.nodes[u]['vweight'] = float(node_diag[i])

    return G

# Helpers: balance and cut utilities
def partition_balance(G, part):
    # Balance by vweight if available else by node count
    if all('vweight' in G.nodes[n] for n in G.nodes):
        wA = sum(G.nodes[n]['vweight'] for n, p in part.items() if p == 0)
        wB = sum(G.nodes[n]['vweight'] for n, p in part.items() if p == 1)
        total = wA + wB
    else:
        wA = sum(1 for p in part.values() if p == 0)
        wB = sum(1 for p in part.values() if p == 1)
        total = wA + wB
    return wA / total, wB / total

def edge_cut(G: nx.Graph, part: dict, weight: str = "weight") -> float:
    cut = 0.0
    for u, v, data in G.edges(data=True):
        if part[u] != part[v]:
            w = data.get(weight, 1.0)
            cut += abs(w)
    return float(cut)

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

def summarize(G, part, label):
    cut = edge_cut(G, part)
    b0, b1 = partition_balance(G, part)
    print(f"{label}: cut={cut:.4f}, balance=({b0:.3f}, {b1:.3f})")

def summarize_generic(G, part, label, weight='weight'):
    labels = set(part.values())
    if len(labels) == 2:
        summarize(G, part, label)
    else:
        cut = edge_cut_kway(G, part, weight=weight)
        labs, per, total = kway_balance_info(G, part)
        print(f"{label}: cut={cut:.4f}, parts={labs}, per={per}, total={total:.4f}")
        print(f"Per difference: {(max(per) - min(per))} Max per: {max(per)} Min per: {min(per)}")
