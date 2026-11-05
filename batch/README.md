# Batch Study Orchestrator (`batch/`)

Automates multi-matrix, multi-scale, and multi-algorithm benchmarking sweeps across the domain decomposition pipeline. A batch works directly on matrices from the shared library (`matrices/`) and does not use any simulation's settings.

## Files

- **[batch_configuration.json](batch_configuration.json)** — Defines:
  - `matrices`: Library matrices to run (`{"key": "<matrix_id>"}`, a folder in `matrices/`)
  - `base_parameters`: Full simulation-parameters block every case starts from (DOFs per node, refinement settings, …)
  - `coarsening_presets`: Target coarse node intervals (`small` `[4, 5]`, `medium` `[100, 175]`, `big` `[1500, 2500]`)
  - `algorithm_presets`: Partitioning backends (`metis`, `qa_emulated`, `qa_hardware`, `qaoa_emulated`, `qaoa_hardware`) and their `allowed_sizes`
  - `common_defaults`: Overrides applied to every case on top of `base_parameters` (`general_parameters`, `coarsening_parameters`, `partitioning_common`, `uncoarsening_parameters`)
  - `save_output` (optional): Artifacts each case writes (default: all)
- **[run_batch.py](run_batch.py)** — Executes the Cartesian product of cases in memory and writes each case's results to `batch/runs/batch_<timestamp>/cases/<case_key>/`, plus the aggregated manifest and summary. Case keys are `<matrix>__<algorithm>__<scale>`.
- **`runs/`** — Output directories containing `batch_manifest.json`, `batch_summary.json`, `batch.log`, `cases/` (per-case results) and async per-case logs. The log ends with `Batch finished: …`; failed cases are reported as `FAILED:` lines, which the Studio shows as errors.

## Usage

From the repository root:

```sh
./run.sh --run_batch --dry-run    # preview all generated cases
./run.sh --run_batch              # run the full batch study
./run.sh --run_batch --nohup      # run in background
```

You can also configure, launch, and analyze batch studies interactively in the **Batch Run** and **Results** tabs of the Web Studio (`./run.sh --ui`).

