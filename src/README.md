# Runtime And Source Layout

This document summarizes the runtime flow, the core pipeline files, and the Studio API.

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

The Studio does not reimplement this flow: [job_manager.py](api/services/job_manager.py) launches a Python subprocess that calls `run_simulation` from [runtime.py](libs/runtime/runtime.py) (batches launch [batch/run_batch.py](../batch/run_batch.py)) and parses its log output.

## Core Pipeline Modules

- [main.py](main.py) — CLI entry point.
- [libs/runtime/runtime.py](libs/runtime/runtime.py) — orchestrates a run and writes outputs.
- [libs/runtime/utils.py](libs/runtime/utils.py) — configuration validation, matrix IO, and artifact writers (`AVAILABLE_SAVE_OUTPUTS`).
- [libs/runtime/log.py](libs/runtime/log.py) — timestamped `[<time> <LEVEL>]` logger (INFO / VERBOSE / WARNING / ERROR) used by `run_log` and parsed by the Studio's log stream.
- [libs/domain_decomposition.py](libs/domain_decomposition.py) — end-to-end pipeline (graph, coarsen, partition, uncoarsen, permute).
- [libs/permutation.py](libs/permutation.py) — applies the computed ordering to K and M.
- [libs/profiling/matrix_metrics.py](libs/profiling/matrix_metrics.py) — computes metrics and plots for original vs permuted matrices.
- [libs/multilevel_scheme/coarsening/](libs/multilevel_scheme/coarsening/) — heavy-edge-matching coarsening (`random`, `sorted`, `modified`, `light`).
- [libs/multilevel_scheme/partitioning/](libs/multilevel_scheme/partitioning/) — METIS, QA, and QAOA partitioning backends (see [qa/README.md](libs/multilevel_scheme/partitioning/qa/README.md)).
- [libs/multilevel_scheme/uncoarsening/](libs/multilevel_scheme/uncoarsening/) — uncoarsening and Kernighan–Lin-style refinement.

## Studio API (`api/`)

A FastAPI app that serves the REST API and the built frontend (`frontend/dist/`). Start it with `./run.sh --ui`; the interactive docs are at `/docs`.

- [api/app.py](api/app.py) — app factory, CLI (`--host`, `--port`, `--reload`), and SPA static serving (`index.html` is sent with `no-cache` headers).
- [api/routes/demonstrators.py](api/routes/demonstrators.py) — `/api/demonstrators`: list / create / clone / rename / delete demonstrators; read and save config and parameters; manage presets; validate parameters; upload `.mtx` files or generate demo meshes; dry-run coarsening preview.
- [api/routes/execution.py](api/routes/execution.py) — `/api/execution`: start, list, poll (incremental logs), cancel, and delete simulation jobs.
- [api/routes/batch.py](api/routes/batch.py) — `/api/batch`: read and save `batch_configuration.json`, launch batches, list past batch runs.
- [api/routes/results.py](api/routes/results.py) — `/api/results`: runs for each demonstrator, run detail and KPIs, on-demand plot images, `.zip` bundle download, batch analysis with LaTeX tables.
- [api/routes/quantum_hw.py](api/routes/quantum_hw.py) — `/api/hardware`: SDK readiness, D-Wave clique-capacity probe, QLM QPU inspection.
- [api/services/job_manager.py](api/services/job_manager.py) — background subprocess jobs, log-level parsing, stage and telemetry extraction, per-stage timing, and loading of past runs from disk.
- [api/services/matrix_service.py](api/services/matrix_service.py) — `.mtx` header inspection and synthetic 3D FEM K/M generation.
- [api/services/plot_service.py](api/services/plot_service.py) — curve and KPI extraction, cached plot rendering, LaTeX table builders.
