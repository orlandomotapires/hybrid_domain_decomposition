# FEM Graph Partitioning Toolkit (Multilevel + METIS)

This repository contains utilities and algorithms to load FEM matrices (Matrix Market `.mtx`), convert them to graphs, and partition those graphs using a multilevel scheme with optional METIS integration. It includes a runnable Jupyter notebook showcasing end‑to‑end workflows and comparisons.

Concept Board link: https://fraunhofer.conceptboard.com/board/x7ec-yo4e-gsdk-nxpq-15sy

## Repository structure

- `data/`
	- FEM matrices in Matrix Market format used in the notebook demos:
		- `hybrid_ma.classical.fem.matrix_k.mtx`
		- `hybrid_ma.classical.fem.matrix_m.mtx`
- `src/`
	- `graph_partitioning_main.ipynb` — Main notebook demonstrating graph construction, multilevel partitioning (2‑way and K‑way), and METIS comparison.
	- `libs/`
		- `utils.py` — Matrix IO and matrix→graph conversion, plus small print helpers.
		- `multilevel_squeme/` — Modular multilevel graph partitioning implementation:
			- `coarsening.py` — Heavy Edge Matching (HEM) coarsening and graph contraction.
			- `partitioning.py` — Initial partitioning strategies: GGGP, Spectral, Component‑aware.
			- `refinement.py` — Refinements (FM/KL), cut utilities, balance helpers.
			- `driver.py` — Orchestrates the multilevel pipeline; includes 2‑way and recursive K‑way.
			- `metis_backend.py` — Adapters to PyMetis and python‑metis for direct 2‑/K‑way partitioning.
- `requirements.txt` — Python dependencies. One METIS backend is optional (PyMetis recommended).

## Key modules and main functions

### Matrix and graph utilities (`src/libs/utils.py`)
- `load_mtx(path, target_name)` — Loads a Matrix Market file into `scipy.sparse.csr_matrix` and logs shape/nnz.
- `matrix_to_graph(A, symmetrize='sum', drop_diagonal=True, abs_weights=True, node_vweight=None| 'diag' | 'degree', diag=None)` — Builds a NetworkX graph from a matrix. Supports:
	- Symmetrization (sum/max/avg/none), diagonal removal, thresholding.
	- Absolute edge weights (recommended for stable cuts and matching).
	- Optional node vertex weights (vweight) from the matrix diagonal (e.g., mass) or degrees.
- Convenience printers used by the notebook:
	- `summarize(G, part, label)` — 2‑way cut and balance.
	- `summarize_generic(G, part, label)` — Handles 2‑way or K‑way (uses library cut/balance helpers).

### Multilevel scheme (`src/libs/multilevel_squeme/`)

Coarsening:
- `heavy_edge_matching(G, weight='weight', seed=None)` — HEM matching prioritizing heavier edges.
- `coarsen_graph(G, weight='weight', seed=None)` — Contracts matched pairs; preserves/aggregates vweights.

Initial partitioning:
- `initial_partition_gggp(G, weight='weight', balance_tol=0.03, seed=None)` — Greedy Growing (GGGP), vweight‑balanced when present.
- `initial_partition_spectral(G, weight='weight', target_weight=None)` — Spectral initializer with robust fallbacks for disconnected/singular cases.
- `initial_partition_component_aware(G, weight='weight', balance_tol=0.03, seed=None)` — Detects components; packs or splits to meet balance.

Refinement and utilities:
- `refine_partition_fm(G, part, weight='weight', balance_tol=0.03)` — Fiduccia–Mattheyses style refinement honoring vweight balance.
- `refine_partition_kl(G, part, weight='weight')` — Simplified Kernighan–Lin refinement.
- `edge_cut(G, part, weight='weight')` — 2‑way cut with absolute edge weights.
- `edge_cut_kway(G, part, weight='weight')` — K‑way cut across labels.
- `kway_balance_info(G, part)` — Per‑part weights (vweight if present, else counts) and total.
- `rebalance_partition(G, part, weight='weight', balance_tol=0.03)` — Greedy post‑processing to enforce balance, helpful for disconnected graphs.

Driver (orchestration):
- `multilevel_bipartition(G, weight='weight', coarsen_limit=80, max_levels=20, seed=None, balance_tol=0.03, refine_method='FM', refine_passes=3, n_trials=8, initial_method='GGGP')`
	- Full 2‑way pipeline: coarsen → initialize (GGGP/Spectral/Component‑aware) → uncoarsen + multi‑pass refinement (FM/KL) → rebalancing.
	- Multi‑start (`n_trials`) selects the best cut.
- `k_way_partition(G, k, choose_by='vweight', **kwargs)`
	- Recursive bisection using `multilevel_bipartition` until `k` parts. Chooses the next block to split by total vweight (if available) or by size.

METIS backend:
- `partition_graph_metis(G, nparts=2, weight='weight', seed=None)`
	- Tries PyMetis first (recommended), then python‑metis. Automatically converts absolute edge weights to integer weights and forwards node vweights.
	- Works for 2‑way and K‑way (`nparts>=2`).

All public symbols are re‑exported via `src/libs/multilevel_squeme/__init__.py` for convenient imports.

## Concepts: cut and balance

- Cut (2‑way): sum of absolute edge weights crossing between the two parts.
- Cut (K‑way): sum of absolute edge weights whose endpoints are in different labels.
- Balance: how equally “load” is distributed across parts.
	- If nodes carry `vweight` (e.g., diagonal of the mass matrix), balance uses vweight sums.
	- Otherwise, balance uses node counts. The target per part is `total / K` (K=2 for bipartition).
	- `balance_tol` controls allowed relative deviation during splitting.

## Notebook: how to run and switch modes

Open `src/graph_partitioning_main.ipynb` and execute cells in order. Key configuration:

```python
# Modes: 'bipartition' | 'kway_recursive' | 'kway_metis'
PARTITION_MODE = 'bipartition'
NPARTS = 2  # set >2 for K-way
```

- bipartition: runs `multilevel_bipartition` for 2‑way.
- kway_recursive: runs `k_way_partition` (recursive bisection) for `NPARTS`.
- kway_metis: runs `partition_graph_metis` directly with `nparts=NPARTS`.

The notebook builds two graphs from `K.mtx` and `M.mtx`:
- `G_K` with absolute edge weights; balance by node count.
- `G_M` with absolute edge weights and `vweight` from the diagonal of `M` for vweight‑balanced splits.

Outputs shown per run:
- 2‑way: `cut` and `balance=(w0, w1)`.
- K‑way: `cut`, `parts=[0..K-1]`, `per=[weights per part]`, `total`.

## METIS integration

- Backends: PyMetis or python‑metis. Install one of them (PyMetis recommended).
- Edge weights: scaled to integers with absolute values.
- Vertex weights: forwarded if present (`G.nodes[u]['vweight']`).
- Usage in notebook: set `PARTITION_MODE='kway_metis'` and `NPARTS` accordingly, or call `partition_graph_metis` directly.

## Installation

Create a Python environment and install requirements:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Optional: install a METIS backend (one of):

```sh
pip install pymetis
# or
pip install metis  # python-metis
```

## Notes and tips

- Consistent weighting: The pipeline uses absolute edge weights for coarsening, gains, and cut — this usually stabilizes results vs signed weights.
- Disconnected graphs: The component‑aware initializer and final rebalancing help avoid zero‑cut artifacts and enforce balance.
- Tuning: For tighter balance or lower cuts, adjust `balance_tol`, `refine_passes`, and `n_trials`. For K‑way, recursive bisection balance is local per split; METIS direct K‑way often yields slightly tighter global balance.
