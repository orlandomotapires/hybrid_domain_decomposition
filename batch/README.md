# Batch Study Orchestrator (`batch/`)

Automates multi-matrix, multi-scale, and multi-algorithm benchmarking sweeps across the domain decomposition pipeline.

## Files

- **[batch_configuration.json](batch_configuration.json)** — Defines:
  - `geometries`: Target matrix workspaces (`matrix_01`, `matrix_02`, `matrix_03`, …)
  - `coarsening_presets`: Target coarse node intervals (`small` `[4, 5]`, `medium` `[100, 175]`, `big` `[1500, 2500]`)
  - `algorithm_presets`: Partitioning backends (`metis`, `qa_emulated`, `qa_hardware`, `qaoa_emulated`, `qaoa_hardware`) and their `allowed_sizes`
  - `common_defaults`: Shared seed, coarsening strategy, and balance tolerance
- **[run_batch.py](run_batch.py)** — Executes the Cartesian product of cases in memory (without mutating the base JSON files in `matrices/`) and writes aggregated results to `batch/runs/batch_<timestamp>/`.
- **`runs/`** — Output directories containing `batch_manifest.json`, `batch_summary.json`, `batch.log`, and per-case logs.

## Usage

From the repository root:

```sh
./run.sh --run_batch --dry-run    # preview all generated cases
./run.sh --run_batch              # run the full batch study
./run.sh --run_batch --nohup      # run in background
```

You can also configure, launch, and analyze batch studies interactively in the **Batch** and **Results** tabs of the Web Studio (`./run.sh --ui`).

