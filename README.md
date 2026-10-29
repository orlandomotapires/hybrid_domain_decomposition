# Hybrid Domain Decomposition

This repository implements a FEM matrix permutation pipeline for domain decomposition experiments.
It loads Matrix Market inputs, builds weighted graphs, coarsens the graph, partitions the coarse graph (classically with METIS or with quantum annealing / QAOA), uncoarsens with refinement, and permutes the original K and M matrices.

You can use it in two ways:

- **Hybrid Domain Decomposition Studio** — a web interface to configure, run, monitor, and analyze simulations (`./run.sh --ui`).
- **Command line** — run single demonstrators or batch studies directly with `run.sh`.

Both use the same Python pipeline and the same JSON files under `demonstrators/` and `batch/`, so anything saved in the Studio can be run from the CLI, and the other way around.

The runtime currently supports Matrix Market `.mtx` inputs.

Command examples assume Linux and a POSIX-compatible shell such as `bash`.

## Installation

**Python** (pipeline + Studio backend):

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

**Node.js ≥ 18 and npm** (needed only for the Studio frontend). `./run.sh --ui` installs the frontend dependencies on first launch and builds the bundle every time it starts.

If you use D-Wave or QLM backends, see [src/libs/multilevel_scheme/partitioning/qa/README.md](src/libs/multilevel_scheme/partitioning/qa/README.md) before starting a remote run.

## Hybrid Domain Decomposition Studio (`--ui`)

```sh
./run.sh --ui                      # http://127.0.0.1:8000
./run.sh --ui --port 8080          # custom port
./run.sh --ui --host 0.0.0.0       # expose on the local network
./run.sh --ui --reload             # auto-reload the Python backend while developing
```

Then open the printed URL in your browser.

> [!NOTE]
> `./run.sh --ui` runs `npm run build` on every launch, so edits under `frontend/src/` show up after a restart. `--reload` only watches the **Python** files; for live frontend editing use the Vite dev server described in [frontend/README.md](frontend/README.md). If the browser still shows an old version, hard-refresh with `Ctrl + Shift + R`.

### Studio tabs

| Tab | What it does |
| --- | --- |
| **Pipeline** | Configures the five pipeline stages for the selected demonstrator: input matrices (select, upload `.mtx`, or generate a demo 3D FEM mesh with 240 or 600 nodes), coarsening (HEM strategy, scale presets, limits, *Preview Coarsening* dry run), partitioning (METIS, QA emulated or D-Wave, QAOA emulated or QLM, plus a live estimate of QPU jobs and shots), refinement, and output artifacts. Also creates, clones, renames, and deletes demonstrators; saves, deletes, and compares parameter presets (*Compare Configs*); and shows the raw JSON. |
| **Run** | Starts a simulation and streams its log live, with level filters (INFO / VERBOSE / WARNING / ERROR). Shows a 5-stage progress tracker with timing for each stage and graph telemetry (fine and coarse graph size, levels, parts). Keeps a run history that survives server restarts. |
| **Batch** | Edits `batch/batch_configuration.json` (geometries, coarsening scales, algorithm presets and the scales each one allows), lists the generated case matrix, launches the batch, and lists past batch runs. |
| **Results** | *Batch* mode: bandwidth / nB² / diagonal-band comparison table, locality curves for each scale, and ready-to-copy thesis LaTeX tables. *Single Run* mode: K and M KPIs, a side-by-side Run A vs Run B comparison, a gallery of partitioned matrices and graphs, and a one-click `.zip` download of the run. |
| **Hardware** | Shows which SDKs are installed (METIS, PennyLane, D-Wave, myQLM, …), probes D-Wave QPU clique capacity, and inspects a QLM QPU. |
| **Wiki** | Built-in documentation for every parameter, method, metric, and tool. Every `(i)` icon in the Studio links to the matching Wiki entry. |

Other features:

- **Dark / Light mode**: the sun / moon button in the header. Your choice is saved in the browser.
- **Feasibility warnings**: the Studio warns when the coarse graph is too large for the selected quantum backend (for example, more than about 18 qubits for statevector QAOA, or more than about 175 nodes for a D-Wave clique embedding) and offers a one-click fix.
- **Unsaved-changes bar**: a sticky *Save* / *Run* bar at the bottom of the Pipeline tab. Parameters are validated by the backend before they are saved.

The REST API behind the Studio is documented automatically at `http://127.0.0.1:8000/docs` (FastAPI / OpenAPI).

## Run A Single Simulation (CLI)

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

Runs started from the CLI also appear in the Studio's **Run** history and **Results → Single Run**.

## Run A Batch (CLI)

Edit `batch/batch_configuration.json` (or use the Studio's **Batch** tab) to adjust the geometries, coarsening presets, and algorithm presets.
Then run the batch runner from the repository root:

```sh
./run.sh --run_batch
```

Optional flags:

- `--dry-run` to list the generated cases only
- `--nohup` to run in the background and write all output to `batch.log` in the batch folder
- `--stop-on-error` to stop the batch if any case fails

Batch outputs are written under `batch/runs/batch_YYYYmmdd_HHMMSS/`.

## Inspect A QLM Backend (CLI)

```sh
./run.sh --qlm_inspect --help
```

The same check is available in the Studio's **Hardware** tab.

## Results

### Single Simulation Results

Each run creates a timestamped folder under `demonstrators/<name>/results/`.
Typical artifacts (selected through `save_output`) include:

- `run_log`
- `run_metrics.json` and `run_metrics.txt`
- `run_simulation_parameters.json`
- `permutation.txt`
- `matrix_k_permuted.mtx` and `matrix_m_permuted.mtx`
- the coarsened graph (`coarsened_graph`)

These artifacts contain the main results for a single simulation: permutation quality checks, bandwidth and NNZ metrics, and the permuted matrices.
The Studio renders plots from these files on demand (cached in the run folder) and can download the whole folder as a `.zip`.

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
The Studio's **Results** tab uses the same plotting functions and LaTeX table logic, so you don't need the notebook for routine analysis.

## Repository Structure

- `run.sh` — wrapper for the Studio, simulations, batch runs, and QLM inspection.
- `frontend/` — Studio UI (React + TypeScript + Vite + Tailwind). See [frontend/README.md](frontend/README.md).
- `batch/`
  - `run_batch.py` — batch-study entry point.
  - `batch_configuration.json` — presets for geometries, sizes, and algorithms.
  - `runs/` — generated batch manifests, logs, summaries, and async outputs.
- `demonstrators/`
  - `demonstrator_01/`, `demonstrator_02/`, `demonstrator_03/` — each with `data/` (config, parameter presets, `matrices/`) and `results/`. New demonstrators can be created from the Studio.
- `notebooks/`
  - `plots_notebook.ipynb` and `notebook_functions.py`.
- `src/` — pipeline implementation and Studio API (see [src/README.md](src/README.md)).
- `requirements.txt`, `pyproject.toml` — Python dependencies and tooling.

## Simulation Inputs

Each demonstrator provides:

- `data/simulation_config.json`
  - selects the parameters file (`parameters_file_path`)
  - defines input matrix file names (`input_matrices`)
  - controls which outputs are written (`save_output`)

- `data/<parameters file>.json` (several presets can sit side by side; the Studio's *Save as Preset* creates new ones)
  - `general_parameters` — `dof_per_node`, `seed`
  - `coarsening_parameters` — `strategy` (`random`, `sorted`, `modified`, `light`), `coarsen_inferior_limit`, `coarsen_superior_limit`, `max_levels`, `coarsen_ratio`, `max_node_weight`
  - `partitioning_parameters`
  - `uncoarsening_parameters` — `refine_objective` (`cut` or `cut_balance`), `refine_balance_lambda`, `refine_max_passes_per_level`, `refine_max_moves_per_pass`

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

Each field is explained in the Studio's **Wiki** tab.
