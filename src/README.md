# Scientific Simulation Engine (`src/`)

`src/` contains the pure mathematical and algorithmic implementation of the multilevel domain decomposition and sparse matrix permutation pipeline. Web-server code lives separately in [`../backend/`](../backend/README.md).

## Runtime Flow

1. **[main.py](main.py)** parses the target matrix workspace directory (e.g. `matrices/matrix_01`).
2. **[libs/runtime/runtime.py](libs/runtime/runtime.py)** loads `data/simulation_config.json` and the active parameter preset JSON, validates all inputs, and resolves `.mtx` paths.
3. **[libs/domain_decomposition.py](libs/domain_decomposition.py)** executes the 5-stage pipeline:
   - **Stage 1 — Graph Construction:** Aggregates nodal $(d \times d)$ blocks of the stiffness matrix $K$ into a weighted undirected graph $G_0 = (V_0, E_0, c, w)$.
   - **Stage 2 — Coarsening:** Contracts $G_0 \to G_1 \to \dots \to G_L$ using Heavy-Edge Matching (`random`, `heavy_edge`, `modified`, `light_edge`) until the vertex count reaches `[coarsen_inferior_limit, coarsen_superior_limit]`.
   - **Stage 3 — Coarse Partitioning:** Partitions the coarse graph $G_L$ into $k$ subdomains using classical METIS (`metis_partitioning`), recursive QUBO Quantum Annealing (`quantum_annealing`), or recursive Ising QAOA (`quantum_approximation_optimizer`).
   - **Stage 4 — Uncoarsening & Refinement:** Projects the partition back level-by-level to $G_0$, applying multi-way Kernighan–Lin boundary refinement (`cut` or `cut_balance`) at every level.
   - **Stage 5 — Matrix Permutation & Profiling:** Builds the global DOF permutation vector $P$, computes $K' = P K P^\top$ and $M' = P M P^\top$, and evaluates structural bandwidth and diagonal locality metrics.
4. **[libs/runtime/runtime.py](libs/runtime/runtime.py)** writes the enabled artifacts (`save_output`) to `matrices/<name>/results/run_<timestamp>/`.

## Core Modules

- **[main.py](main.py)** — CLI entry point.
- **[libs/domain_decomposition.py](libs/domain_decomposition.py)** — End-to-end multilevel graph partitioning and matrix permutation orchestrator.
- **[libs/permutation.py](libs/permutation.py)** — Applies node-level partition orderings to DOF-level sparse matrices $K$ and $M$.
- **[libs/profiling/matrix_metrics.py](libs/profiling/matrix_metrics.py)** — Computes bandwidth, average bandwidth, $nB^2$ figure-of-merit, and near-diagonal band concentration curves.
- **[libs/runtime/runtime.py](libs/runtime/runtime.py)** — File I/O, run directory creation, and artifact export.
- **[libs/runtime/utils.py](libs/runtime/utils.py)** — Schema validation (`validate_and_normalize_simulation_config`, `validate_and_normalize_simulation_parameters`) and Matrix Market helpers.
- **[libs/runtime/log.py](libs/runtime/log.py)** — Timestamped `[<time> <LEVEL>]` logger (`INFO`, `VERBOSE`, `WARNING`, `ERROR`).
- **[libs/multilevel_scheme/coarsening/](libs/multilevel_scheme/coarsening/)** — Heavy-Edge Matching coarsening strategies.
- **[libs/multilevel_scheme/partitioning/](libs/multilevel_scheme/partitioning/)** — Classical METIS, Quantum Annealing (`qa/`), and QAOA (`qaoa/`) solvers (see [qa/README.md](libs/multilevel_scheme/partitioning/qa/README.md)).
- **[libs/multilevel_scheme/uncoarsening/](libs/multilevel_scheme/uncoarsening/)** — Multilevel projection and Kernighan–Lin boundary refinement.
