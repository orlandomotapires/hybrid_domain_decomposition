# Runtime And Source Layout

This document summarizes the runtime flow and the core pipeline files.

## Runtime Flow

The main runtime path is:

1. [main.py](main.py) reads the demonstrator directory argument.
2. [runtime.py](libs/runtime/runtime.py) loads `simulation_config.json` and the referenced parameters file, validates inputs, and resolves matrix paths.
3. [domain_decomposition.py](libs/domain_decomposition.py) runs:
   - matrix to graph conversion (K-based graph)
   - graph coarsening
   - coarse partitioning
   - uncoarsening and refinement
   - permutation of both K and M matrices
4. [runtime.py](libs/runtime/runtime.py) writes only the outputs listed in `save_output` to `demonstrators/<name>/results/<timestamp>/`.

## Core Pipeline Modules

- [main.py](main.py) — CLI entry point.
- [libs/runtime/runtime.py](libs/runtime/runtime.py) — orchestrates a run and writes outputs.
- [libs/runtime/utils.py](libs/runtime/utils.py) — configuration validation, matrix IO, and artifact writers.
- [libs/domain_decomposition.py](libs/domain_decomposition.py) — end-to-end pipeline (graph, coarsen, partition, uncoarsen, permute).
- [libs/permutation.py](libs/permutation.py) — applies the computed ordering to K and M.
- [libs/post_processing/matrix_metrics.py](libs/post_processing/matrix_metrics.py) — computes metrics and plots for original vs permuted matrices.
- [libs/multilevel_scheme/coarsening/](libs/multilevel_scheme/coarsening/) — graph coarsening implementations.
- [libs/multilevel_scheme/partitioning/](libs/multilevel_scheme/partitioning/) — METIS, QA, and QAOA partitioning backends.
- [libs/multilevel_scheme/uncoarsening/](libs/multilevel_scheme/uncoarsening/) — uncoarsening and refinement steps.