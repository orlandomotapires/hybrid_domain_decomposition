# Hybrid Domain Decomposition

This repository implements a hybrid quantum-classical graph partitioning and sparse matrix permutation pipeline for domain decomposition.
It loads Matrix Market (`.mtx`) inputs ($K$ and $M$), builds weighted nodal coupling graphs, coarsens the graph via Heavy-Edge Matching, partitions the coarse graph (classically with METIS or with Quantum Annealing / QAOA), uncoarsens with Kernighan–Lin refinement, and permutes the original $K$ and $M$ matrices.

You can use it in three ways:

- **Live Web Studio (GitHub Pages)** — explore the interactive Studio online at **[https://orlandomotapires.github.io/hybrid_domain_decomposition/](https://orlandomotapires.github.io/hybrid_domain_decomposition/)**.
- **Local Web Studio (`./run.sh --ui`)** — launch the full local FastAPI + React Studio connected to your Python/quantum environment.
- **Command Line (`./run.sh`)** — run single matrix workspaces or multi-case batch studies directly from the terminal.

Both the Web Studio and the CLI read and write the exact same JSON configuration files under `matrices/` and `batch/`.

---

## Repository Structure

```text
hybrid_domain_decomposition/
├── src/                  # Pure scientific simulation engine (coarsening, partitioning, refinement, permutation)
├── backend/              # FastAPI REST server & background job orchestration for the Web Studio
├── frontend/             # React 18 + TypeScript + Vite + Tailwind Web Studio UI
├── matrices/             # Matrix workspaces (matrix_01, matrix_02, matrix_03), presets, and run outputs
├── batch/                # Multi-matrix, multi-scale batch orchestrator and benchmark runs
├── notebooks/            # Jupyter notebooks & plotting helpers for thesis analysis
├── tests/                # Python unit test suite
├── docs/                 # Thesis / paper PDF and reference documentation
└── run.sh                # Unified CLI entrypoint for Studio, single runs, batch runs, and QLM inspection
```

Each folder has its own README with implementation details:
- **[src/README.md](src/README.md)** — Scientific pipeline (`libs/`) & mathematical modules.
- **[backend/README.md](backend/README.md)** — FastAPI REST routes (`routes/`) and background services (`services/`).
- **[frontend/README.md](frontend/README.md)** — React Studio UI, Dark/Light theme generator, and GitHub Pages static fallback.
- **[matrices/README.md](matrices/README.md)** — How matrix workspaces (`matrix_01`, `matrix_02`, `matrix_03`) and parameter presets are structured.
- **[batch/README.md](batch/README.md)** — How to configure and run Cartesian batch benchmarks.
- **[src/libs/multilevel_scheme/partitioning/qa/README.md](src/libs/multilevel_scheme/partitioning/qa/README.md)** — D-Wave Leap and QLM / myQLM quantum backend setup.

---

## Installation

**Python** (simulation engine + Studio backend):

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

**Node.js ≥ 18 and npm** (needed only for building the Studio frontend locally). `./run.sh --ui` automatically installs frontend dependencies on first launch and builds `frontend/dist/`.

---

## Hybrid Domain Decomposition Studio (`--ui`)

```sh
./run.sh --ui                      # http://127.0.0.1:8000
./run.sh --ui --port 8080          # custom port
./run.sh --ui --host 0.0.0.0       # expose on the local network
./run.sh --ui --reload             # auto-reload the Python backend while developing
```

### Studio Tabs

| Tab | What it does |
| --- | --- |
| **Pipeline** | Configures the five pipeline stages for the selected matrix workspace (`matrix_01`, `matrix_02`, `matrix_03`, or custom): input matrices (select, upload `.mtx`, or generate a 3D demo mesh), coarsening (HEM strategy, scale presets, *Preview Coarsening* dry run), partitioning (METIS, QA emulated or D-Wave QPU, QAOA emulated or QLM QPU), refinement, and output artifacts. Also creates, clones, renames, and deletes matrix workspaces; manages presets; and compares configurations. |
| **Run** | Starts a simulation and streams its log live with level filters (`INFO` / `VERBOSE` / `WARNING` / `ERROR`), a 5-stage progress tracker, per-stage timing, and graph telemetry. |
| **Batch** | Edits `batch/batch_configuration.json` (matrices, coarsening scales, algorithm presets), previews the generated case matrix, launches batch runs, and inspects past batch logs. |
| **Results** | *Batch* mode: bandwidth / $nB^2$ / diagonal-band comparison tables, locality curves, and LaTeX table export. *Single Run* mode: $K$ and $M$ KPIs, side-by-side Run A vs Run B comparison, partitioned matrix/graph gallery, and `.zip` bundle download. |
| **Hardware** | Shows installed classical/quantum SDKs (`PyMETIS`, `dwave-neal`, `dwave-system`, `PennyLane`, `myQLM`), probes D-Wave QPU clique capacity, and inspects QLM QPUs. |
| **Wiki** | Built-in documentation for every parameter, method, formula, and metric. Every `(i)` icon in the Studio opens the matching Wiki entry. |

---

## Command-Line Usage

### 1. Run a Single Matrix Workspace

```sh
./run.sh matrices/matrix_01
```

Outputs are written to a timestamped folder under `matrices/matrix_01/results/run_<timestamp>/`.

### 2. Run a Batch Study

```sh
./run.sh --run_batch              # execute all configured cases
./run.sh --run_batch --dry-run    # list generated cases without running
./run.sh --run_batch --nohup      # run in background
```

### 3. Inspect a QLM Backend

```sh
./run.sh --qlm_inspect --help
```

### 4. Refresh the GitHub Pages Demo Snapshot

```sh
./run.sh --export-demo
```

Exports the current `matrices/` configurations, presets, and benchmark results into `frontend/public/demo-snapshot.json` for static GitHub Pages deployment.

### 5. Run Unit Tests

```sh
PYTHONPATH=src:. python -m unittest discover -s tests -v
```
