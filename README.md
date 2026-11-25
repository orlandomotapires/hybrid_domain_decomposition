# Hybrid Domain Decomposition

> **TL;DR** — Reorders any square sparse matrix (`.mtx`) into $A' = P A P^\top$ by partitioning its graph with METIS, Quantum Annealing or QAOA. Everything runs locally.
>
> ```sh
> conda create -n hdd python=3.14 -y && conda activate hdd
> pip install -r requirements.txt
> ./run.sh --ui                          # web Studio at http://127.0.0.1:8000
> ./run.sh simulations/simulation_01     # or run one simulation from the terminal
> ```
>
> Desktop app: `pip install -e ".[gui]"` then `./run.sh --desktop`.

This repository implements a hybrid quantum-classical graph partitioning and sparse matrix permutation pipeline for domain decomposition.
It is matrix-agnostic: give it any square sparse matrix $A$ in Matrix Market (`.mtx`) format and it builds the matrix graph, coarsens it via Heavy-Edge Matching, partitions the coarse graph (classically with METIS or with Quantum Annealing / QAOA), uncoarsens with Kernighan–Lin refinement, and returns the reordered matrix $A' = P A P^\top$ plus the permutation $P$.

You can use it in two ways:

- **Local Web Studio (`./run.sh --ui`)** — launch the FastAPI + React Studio on your machine, connected to your Python/quantum environment.
- **Command Line (`./run.sh`)** — run single simulations or multi-case batch studies directly from the terminal.

The Studio is not hosted online: every simulation runs on your machine, so clone the repository and follow the TL;DR above:

```sh
git clone https://github.com/orlandomotapires/hybrid_domain_decomposition.git
cd hybrid_domain_decomposition
```

Both the Web Studio and the CLI read and write the exact same files under `simulations/`, `matrices/` and `batch/`.

---

## Repository Structure

```text
hybrid_domain_decomposition/
├── src/                  # Pure scientific simulation engine (coarsening, partitioning, refinement, permutation)
├── backend/              # FastAPI REST server & background job orchestration for the Web Studio
├── frontend/             # React 18 + TypeScript + Vite + Tailwind Web Studio UI
├── simulations/          # Simulations (simulation_01, …): config, parameter presets, and run outputs
├── matrices/             # Shared matrix library: one folder per matrix, used by simulations and batches
├── batch/                # Multi-matrix, multi-scale batch orchestrator and benchmark runs
├── notebooks/            # Jupyter notebooks & plotting helpers for thesis analysis
├── tests/                # Python unit test suite
├── docs/                 # Thesis / paper PDF and reference documentation
└── run.sh                # Unified CLI entrypoint for Studio, single runs, batch runs, tuning, and QLM inspection
```

Each folder has its own README with implementation details:

- **[src/README.md](src/README.md)** — Scientific pipeline (`libs/`) & mathematical modules.
- **[backend/README.md](backend/README.md)** — FastAPI REST routes (`routes/`) and background services (`services/`).
- **[frontend/README.md](frontend/README.md)** — React Studio UI and Dark/Light theme generator.
- **[simulations/README.md](simulations/README.md)** — How simulations (`simulation_01`, …), parameter presets and results are structured.
- **[matrices/README.md](matrices/README.md)** — The shared matrix library and how to add a matrix.
- **[batch/README.md](batch/README.md)** — How to configure and run Cartesian batch benchmarks.
- **[src/libs/multilevel_scheme/partitioning/qa/README.md](src/libs/multilevel_scheme/partitioning/qa/README.md)** — D-Wave Leap and QLM / myQLM quantum backend setup.

---

## Installation

**Python** (simulation engine + Studio backend):

```sh
conda create -n hdd python=3.14 -y
conda activate hdd
pip install -r requirements.txt
```

**Node.js ≥ 18 and npm** (needed only for building the Studio frontend locally). `./run.sh --ui` automatically installs frontend dependencies on first launch and builds `frontend/dist/`.

---

## HDD Studio Desktop (`--desktop`)

A native desktop application (Qt 6) for Ubuntu 24.04 is replacing the web Studio. It opens a
workspace, shows it as a project tree (matrices, simulations with their stages, presets, tuning
studies, runs, batches), edits simulation parameters with per-field validation, undo/redo and a
live coarsening preview, manages presets (save, load, activate, compare), runs simulations with a
live log, and plots sparsity patterns and locality curves. Editing batch configurations and
running tuning studies are still being ported; until then use the web Studio for those.

```sh
pip install -e ".[gui]"            # PySide6 and pyqtgraph
./run.sh --desktop                 # opens the last workspace (default: this repository)
./run.sh --desktop --workspace ~/hdd-projects/blade
packaging/linux/install-launcher.sh          # add HDD Studio to the application menu
packaging/linux/install-launcher.sh --remove # remove it
```

Jobs started from the desktop app keep a record and a log in `<workspace>/.hdd/jobs/`, so they
are listed again after a restart. Closing the app stops running jobs (it asks first).

---

## Hybrid Domain Decomposition Studio (`--ui`)

```sh
./run.sh --ui                      # http://127.0.0.1:8000
./run.sh --ui --port 8080          # custom port
./run.sh --ui --host 0.0.0.0       # expose on the local network
./run.sh --ui --reload             # auto-reload the Python backend while developing
```

### Studio Tabs

The five core tabs sit in the main bar under the title; **Hardware** and **Wiki** are reference pages in the top-right corner.

| Tab                  | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Single Run** | One tab per simulation (`simulation_01`, `simulation_02`, …). Configures its five pipeline stages: input matrix (pick any square matrix from the shared library, upload a `.mtx`, or generate a demo matrix), coarsening (HEM strategy, scale presets, *Preview Coarsening* dry run), partitioning (METIS, QA emulated or D-Wave QPU, QAOA emulated or QLM QPU), refinement, and output artifacts. Also creates, renames, and deletes simulations; manages presets; and compares configurations.                                                                                                                                                                                     |
| **Batch Run**  | Edits `batch/batch_configuration.json`: which library matrices to run, coarsening scales, shared parameters, and every algorithm's parameters. Previews the generated cases with duration/QPU estimates and launches the batch. Batches use library matrices directly and ignore per-simulation settings.                                                                                                                                                                                                                                                                                                                                                                                   |
| **Tuning**     | Parameter selection for the selected simulation. *Automatic*: rules from the matrix features plus a coarsening dry-run grid propose a feasible parameter set. *Iterative tuning*: an Optuna study (Bayesian TPE, genetic NSGA-II, CMA-ES, Sobol or random) runs the pipeline repeatedly; tick one or more objectives (edge cut, imbalance, band quality, bandwidth, run time; several = Pareto front or weighted sum) and mark each parameter, including `k_target` and the partitioning strategy, as fixed or free. *Studies*: convergence / Pareto charts, trial table, apply any trial to the simulation, resume, or ask for one suggestion at a time and report the run you made. |
| **Runs**       | Live log of the selected run with level filters (`INFO` / `VERBOSE` / `WARNING` / `ERROR`; any line reporting a failure is an `ERROR`), a 5-stage progress tracker, batch progress and ETA, and the history of every run.                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **Results**    | *Batch* mode: bandwidth / $nB^2$ / diagonal-band comparison tables and locality curves. *Single Run* mode: $K$ and $M$ KPIs, side-by-side Run A vs Run B comparison, partitioned matrix/graph gallery, and `.zip` bundle download.                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Hardware**   | Shows installed classical/quantum SDKs (`PyMETIS`, `dwave-neal`, `dwave-system`, `PennyLane`, `myQLM`), probes D-Wave QPU clique capacity, and inspects QLM QPUs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Wiki**       | Built-in documentation for every parameter, method, formula, and metric. Every `(i)` icon in the Studio opens the matching Wiki entry.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

---

## Workspaces

Project data (`matrices/`, `simulations/`, `batch/`, `tuning/`) lives in a *workspace*. By default the
workspace is this repository, so nothing changes for existing use. To keep data elsewhere, point
`HDD_WORKSPACE` at another folder; the Studio, the command line and every job they start will read
and write only there:

```bash
HDD_WORKSPACE=~/hdd-projects/blade ./run.sh --ui
HDD_WORKSPACE=~/hdd-projects/blade ./run.sh simulations/simulation_01
```

Simulation paths given on the command line are relative to the workspace.

## Command-Line Usage

### 1. Run a Single Simulation

```sh
./run.sh simulations/simulation_01
```

The simulation's `simulation_config.json` names its matrix (`input_matrix`, a folder in `matrices/`). Outputs are written to a timestamped folder under `simulations/simulation_01/results/run_<timestamp>/`.

### 2. Run a Batch Study

```sh
./run.sh --run_batch              # execute all configured cases
./run.sh --run_batch --dry-run    # list generated cases without running
./run.sh --run_batch --nohup      # run in background
```

### 3. Select or Tune Parameters

```sh
./run.sh --tune simulations/simulation_01 --auto                      # Mode A: print auto-selected parameters
./run.sh --tune simulations/simulation_01 --n-trials 30 \
        --objectives edge_cut,imbalance                               # Mode B: Pareto study (NSGA-II)
./run.sh --tune simulations/simulation_01 --objectives edge_cut \
        --free k_target,partitioning_strategy --sampler tpe          # single objective, k and method free
./run.sh --tune --resume simulations/simulation_01/tuning/study_<ts>  # continue a study
```

Studies are saved in `simulations/<sim>/tuning/study_<timestamp>/` (`study_config.json`, Optuna `study.db`, `trials.jsonl`, `summary.json`, `best_parameters.json`, and one normal run folder per trial). Every run, from any entry point, is also appended to `tuning/history.jsonl`, which later studies use as a warm start. See [src/libs/tuning/](src/libs/tuning/__init__.py).

### 4. Inspect a QLM Backend

```sh
./run.sh --qlm_inspect --help
```

### 5. Run Unit Tests

```sh
PYTHONPATH=src:. python -m unittest discover -s tests -v
```

Desktop interface tests (headless):

```sh
pip install -e ".[gui,dev]"
QT_QPA_PLATFORM=offscreen PYTHONPATH=src:. python -m pytest tests/gui
```
