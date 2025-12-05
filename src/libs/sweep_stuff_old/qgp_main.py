import os

from libs.multilevel_squeme.coarsening import coarsen_chain
from libs.multilevel_squeme import partition_graph_metis
from libs.multilevel_squeme.quantum_annealing import (
    anneal_bipartition,
    lift_partition_to_finer,
    recursive_kway_anneal
)

from libs.utils import (
    load_mtx,
    matrix_to_graph,
    summarize_generic
)

data_dir = os.path.abspath(os.path.join("data"))

k_matrix_path = os.path.join(data_dir, "hybrid_ma.classical.fem.matrix_k.mtx")
print("Using data_dir:", data_dir)

# Load matrices
A_K = load_mtx(k_matrix_path, 'K')

if A_K is None:
    raise RuntimeError("Matrix load failed; check file paths printed above.")

print(f"Loaded: K | shape={A_K.shape}, nnz={A_K.nnz}")

# Build graphs from matrices
diag_K = A_K.diagonal()

# Map the matrix into the graph (only the K matrix is needed since we are partitioning most based on connectivity)
G_K = matrix_to_graph(A_K, symmetrize='sum', drop_diagonal=True, abs_weights=True, node_vweight='diag', diag=diag_K)

print(f"K: |V|={G_K.number_of_nodes()}, |E|={G_K.number_of_edges()}")

# Parameters for the coarsening
coarsen_limit = 100
max_levels = 200
weight = 'weight'

# Parameters for the annealling
K_TARGET = 32                # number of parts desired
BALANCE_LAMBDA = 1
NUM_READS = 500

graphs, maps = coarsen_chain(G_K, trial_seed=42, coarsen_limit=coarsen_limit, max_levels=max_levels, weight=weight)

Gc, Gc_map = graphs[-1], maps[-1]
print(f"K: |V|={Gc.number_of_nodes()}, |E|={Gc.number_of_edges()}")

part_k_coarse_QA = recursive_kway_anneal(
    Gc, 
    K_TARGET,
    balance_weight=BALANCE_LAMBDA,
    num_reads=NUM_READS,
    choose_by='vweight'
)

# Lift back to original nodes
part_k_orig = lift_partition_to_finer(graphs, maps, part_k_coarse_QA)

# Summarize on original graph
summarize_generic(G_K, part_k_orig, f'K [quantum k={K_TARGET}]')

print("\n")

# Baseline METIS comparison for the same K_TARGET
metis_part_K = partition_graph_metis(G_K, nparts=K_TARGET, weight='weight', seed=42, verbose=0)
summarize_generic(G_K, metis_part_K, f"METIS K [{K_TARGET}]")