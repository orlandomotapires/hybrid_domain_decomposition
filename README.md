# FEM Graph Partitioning Toolkit (Multilevel + METIS)

This repository provides a modular multilevel graph partitioning toolkit for FEM graphs (converted from Matrix Market `.mtx`), with direct METIS integration. It ships a runnable notebook to reproduce results and compare strategies (recursive vs direct K‑way, vs METIS).

Concept Board link: https://fraunhofer.conceptboard.com/board/x7ec-yo4e-gsdk-nxpq-15sy

## Repository structure

- `data/`
	- FEM matrices used in the notebook demos:
		- `hybrid_ma.classical.fem.matrix_k.mtx`
		- `hybrid_ma.classical.fem.matrix_m.mtx`
- `src/`
	- `graph_partitioning_main.ipynb` — End‑to‑end demo: load matrices → build graphs → run multilevel partitioners → compare vs METIS.
	- `libs/`
		- `utils.py` — Matrix IO and matrix→graph conversion; print helpers.
		- `multilevel_squeme/` — Core library (see its README for a deep dive):
			- `coarsening.py` — Heavy‑Edge Matching (HEM) and contraction.
			- `partitioning.py` — Initializers: GGGP, Spectral, Component‑aware.
			- `refinement.py` — 2‑way FM/KL, K‑way FM‑like refinement, balance helpers, cut utilities.
			- `driver.py` — Orchestrates pipelines: 2‑way, recursive K‑way, direct K‑way.
			- `metis_backend.py` — Bridges to PyMetis / python‑metis.
- `requirements.txt` — Python deps; one METIS backend is optional (PyMetis recommended).

## High‑level architecture and main APIs

Matrix/graph utilities (`src/libs/utils.py`)
- `load_mtx(path, name)` — Load `.mtx` into `scipy.sparse.csr_matrix`.
- `matrix_to_graph(A, ..., node_vweight='diag'|None, ...)` — Build a weighted NetworkX graph; can set per‑node `vweight`.
- `summarize_generic(G, part, label)` — Print K‑agnostic cut/balance summary.

Multilevel scheme (`src/libs/multilevel_squeme/`)
- Coarsening: `heavy_edge_matching`, `coarsen_graph` (aggregates `vweight`).
- Initial partitioning (2‑way): `initial_partition_gggp`, `initial_partition_spectral`, `initial_partition_component_aware`.
- Refinement (2‑way): `refine_partition_fm`, `refine_partition_kl`; Rebalance (2‑way): `rebalance_partition`.
- K‑way utilities: `edge_cut_kway`, `kway_balance_info`.
- K‑way refinement and rebalance: `refine_partition_kway_fm`, `rebalance_partition_kway` (per‑part tolerance relative to target).
- Drivers:
	- `multilevel_bipartition(...)` — Full 2‑way pipeline with multi‑start and multi‑pass refinement.
	- `k_way_partition(G, k, ...)` — Recursive bisection to K parts via repeated bipartitions.
	- `multilevel_kway_partition(G, k, ...)` — Direct K‑way multilevel with K‑way refinement and final K‑way rebalance; initializes coarsest labels via METIS when available.
- METIS backend: `partition_graph_metis(G, nparts, ...)` — Calls PyMetis (preferred) or python‑metis; converts float weights to ints; forwards `vweight`.

## Notebook usage (modes and knobs)

Open `src/graph_partitioning_main.ipynb` and run sequentially. Key config:

```python
# Modes: 'bipartition' | 'kway_recursive' | 'kway_direct' | 'kway_metis'
PARTITION_MODE = 'kway_direct'
NPARTS = 5
```

- bipartition: `multilevel_bipartition` (only for `NPARTS==2`).
- kway_recursive: `k_way_partition` (stacked 2‑way pipeline).
- kway_direct: `multilevel_kway_partition` (K‑way refinement + final K‑way rebalance, METIS‑seeded on coarsest if possible).
- kway_metis: `partition_graph_metis`.

Important parameters:
- `balance_tol`: relative tolerance per part around its target (`total/K`).
- `refine_passes`, `n_trials`: refinement and multi‑start budget.
- `coarsen_limit`, `max_levels`: hierarchy depth controls.

## Cut, balance, and weights

- Edge cut uses absolute edge weights everywhere (coarsening, refinement gain, scoring).
- Balance uses node `vweight` when provided; otherwise node count. Target per part is `total/K`.
- Direct K‑way uses per‑part tolerance relative to target (similar spirit to METIS `ubvec`).

## METIS vs our implementations (why results differ)

- Coarsening: METIS uses tuned matching variants and tie‑breakers; our HEM is simpler.
- Initialization: direct K‑way in METIS uses K‑aware seeding. We now seed the coarsest graph via METIS when available.
- Refinement: METIS uses boundary queues and best‑prefix FM; our K‑way FM‑like is greedy without best‑prefix yet (see module README for roadmap).
- Balance handling: METIS integrates balance throughout moves; our direct K‑way enforces per‑part bounds and runs a final K‑way rebalance.

Despite these differences, with aligned `balance_tol` and sufficient `refine_passes`/`n_trials`, results are often in the same ballpark, especially in direct K‑way mode.

## Install

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Optional METIS backend (choose one):

```sh
pip install pymetis
# or
pip install metis  # python-metis
```

## Where to read more

- See `src/libs/multilevel_squeme/README.md` for a detailed algorithmic deep dive, parameters, tips, limitations, and roadmap.
