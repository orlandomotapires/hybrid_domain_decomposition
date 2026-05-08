# Runtime And Source Layout

This document summarizes the runtime flow and the main source files.

## Runtime Flow

The main runtime path is:

1. [main.py](/home/operation/Thesis/hybrid_domain_decomposition/src/main.py) reads the simulation directory argument.
2. [runtime.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/runtime/runtime.py) loads `simulation_config.json` and the referenced parameters file.
3. [domain_decomposition.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/domain_decomposition.py) runs:
   - matrix to graph conversion using K only
   - graph coarsening
   - coarse partitioning
   - uncoarsening and refinement
   - matrix permutation for both K and M
4. [runtime.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/runtime/runtime.py) writes only the outputs listed in `save_output`.

Each run creates a timestamped folder under `simulations/<name>/results/`.

## Important Files

- [main.py](/home/operation/Thesis/hybrid_domain_decomposition/src/main.py)
  - minimal CLI wrapper around the simulation runtime.

- [run_batch.py](/home/operation/Thesis/hybrid_domain_decomposition/src/run_batch.py)
  - batch-study entry point for generated parameter sweeps.

- [runtime.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/runtime/runtime.py)
  - resolves paths, validates JSON inputs, runs the decomposition, and saves output artifacts.

- [domain_decomposition.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/domain_decomposition.py)
  - central pipeline that connects graph construction, coarsening, partitioning, refinement, and permutation.

- [utils.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/runtime/utils.py)
  - configuration validation, matrix IO, graph helpers, and result writers.

- [permutation.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/permutation.py)
  - applies the computed partition ordering to both K and M.

- [matrix_metrics.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/post_processing/matrix_metrics.py)
  - computes structural metrics and plots for original versus permuted matrices.

- [coarsening.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/coarsening/coarsening.py)
  - builds the coarsening chain used to reduce the partitioning problem size.

- [partitioning.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/partitioning.py)
  - public partitioning entry points and recursive orchestration.

- [uncoarsening.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/uncoarsening/uncoarsening.py)
  - projects the coarse partition back through the hierarchy and refines it.

- [README.md](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/qa/README.md)
  - backend-specific documentation for METIS, D-Wave quantum annealing, and QLM/PennyLane QAOA.