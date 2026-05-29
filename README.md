# Hybrid Domain Decomposition

This repository implements a FEM matrix permutation pipeline for domain decomposition experiments.
It loads Matrix Market inputs, builds weighted graphs, coarsens the graph, partitions the coarse graph, uncoarsens with refinement, and permutes the original K and M matrices.

The runtime currently supports Matrix Market `.mtx` inputs.

Command examples assume Linux and a POSIX-compatible shell such as `bash`.

## Installation

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

If you use D-Wave or QLM backends, see [src/libs/multilevel_scheme/partitioning/qa/README.md](src/libs/multilevel_scheme/partitioning/qa/README.md) before starting a remote run.

## Run A Single Simulation

Run the simulation from the repository root so the relative paths in the demonstrator folder resolve correctly.

1. Check the demonstrator inputs.

```sh
ls demonstrators/demonstrator_01
ls demonstrators/demonstrator_01/data
python -m json.tool demonstrators/demonstrator_01/data/simulation_config.json
python -m json.tool demonstrators/demonstrator_01/data/simulation_parameters.json
```

2. Start a run.

```sh
./run.sh demonstrators/demonstrator_01
```

3. Inspect the results folder.

```sh
ls -dt demonstrators/demonstrator_01/results/run_* | head
tail -n 40 "$(ls -dt demonstrators/demonstrator_01/results/run_* | head -n 1)/run_log"
```

## Run A Batch

Edit `batch/batch_configuration.json` to adjust the geometries, coarsening presets, and algorithm presets.
Then run the batch runner from the repository root:

```sh
./run.sh --run_batch
```

Optional flags:

- `--dry-run` to list the generated cases only
- `--nohup` to run in the background and write all output to `batch.log` in the batch folder
- `--stop-on-error` to stop the batch if any case fails

Batch outputs are written under `batch/runs/batch_YYYYmmdd_HHMMSS/`.

## Results

### Single Simulation Results

Each run creates a timestamped folder under `demonstrators/<name>/results/`.
Typical artifacts include:

- `run_log`
- `run_metrics.json` and `run_metrics.txt`
- `run_simulation_parameters.json`
- `permutation.txt`
- `matrix_k_permuted.mtx` and `matrix_m_permuted.mtx`

These artifacts contain the main results for a single simulation: permutation quality checks, bandwidth and NNZ metrics, and the permuted matrices.

### Batch Results

Each batch directory contains:

- `batch_manifest.json` with case status and result directory pointers
- `batch_summary.json` with aggregated K and M metrics per case
- `case_logs/` and `async_results/` for per-case logs and async workers
- `batch.log` for the overall batch run

These files capture the main results of the batch across all cases.

## Notebook Analysis

Use [notebooks/plots_notebook.ipynb](notebooks/plots_notebook.ipynb) to evaluate batch results.
Set `BATCH_RUN_NAME` and `DEMONSTRATOR`, then run the cells to generate tables and plots from `batch_summary.json` and the per-case result directories.

By default the notebook writes images to `results_images/` relative to the notebook working directory (typically `notebooks/results_images/`).

## Repository Structure

- `run.sh` — wrapper for simulations, batch runs, and QLM inspection.
- `batch/`
  - `run_batch.py` — batch-study entry point.
  - `batch_configuration.json` — presets for geometries, sizes, and algorithms.
  - `runs/` — generated batch manifests, logs, summaries, and async outputs.
- `demonstrators/`
  - `demonstrator_01/`, `demonstrator_02/` — each with `data/` and `results/`.
- `notebooks/`
  - `plots_notebook.ipynb` and `notebook_functions.py`.
- `src/` — runtime and algorithm implementations (see [src/README.md](src/README.md)).
- `requirements.txt`, `pyproject.toml` — Python dependencies and tooling.

## Simulation Inputs

Each demonstrator provides:

- `data/simulation_config.json`
  - selects the parameters file
  - defines input matrix file names
  - controls which outputs are written

- `data/<parameters file>.json`
  - `general_parameters`
  - `coarsening_parameters`
  - `partitioning_parameters`
  - `uncoarsening_parameters`

Important partitioning fields:

- `partitioning_parameters.partitioning_strategy`
  - `metis_partitioning`
  - `quantum_annealing`
  - `quantum_approximation_optimizer`

- `partitioning_parameters.common`
  - `k_target`
  - `balance_tolerance`

- `partitioning_parameters.strategies.quantum_annealing`
  - `qubo_balance_lambda`
  - `num_reads`
  - `num_starts`
  - `balance_violation_lambda`
  - `simulated`
  - optional D-Wave fields such as `qpu_solver_name`, `qpu_region`, `qpu_problem_label`

- `partitioning_parameters.strategies.quantum_approximation_optimizer`
  - `qubo_balance_lambda`
  - `num_starts`
  - `balance_violation_lambda`
  - `circuit_depth`
  - `num_steps`
  - `adam_learning_rate`
  - `num_shots`
  - `simulated`
  - optional QLM field `qlm_qpu_name`
