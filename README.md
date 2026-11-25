# Hybrid Domain Decomposition

A hybrid quantum-classical pipeline that reorders a sparse matrix for domain decomposition. Give it any square sparse matrix $A$ in Matrix Market (`.mtx`) format and it returns the reordered matrix $A' = P A P^\top$ and the permutation $P$.

The graph of $A$ is partitioned classically with METIS, or on quantum hardware and emulators with Quantum Annealing (D-Wave) or QAOA (QLM). Everything runs on your machine.

## Quick start

```sh
git clone https://github.com/orlandomotapires/hybrid_domain_decomposition.git
cd hybrid_domain_decomposition
conda create -n hdd python=3.14 -y && conda activate hdd
pip install -e ".[gui]"

./run.sh                               # open the desktop app
./run.sh simulations/simulation_01     # or run one simulation from the terminal
```

`pip install -r requirements.txt` installs only the pipeline, for command-line use.

## How it works

Each run goes through five stages:

1. **Input matrix**: a square sparse matrix from the shared library in `matrices/`, turned into its graph.
2. **Coarsening**: Heavy-Edge Matching shrinks the graph until it fits the partitioner.
3. **Partitioning**: METIS, Quantum Annealing (emulated or D-Wave QPU) or QAOA (emulated or QLM QPU) splits the coarse graph into $k$ parts.
4. **Refinement**: the partition is projected back level by level and improved with Kernighan–Lin.
5. **Output**: the permutation $P$, the reordered matrix, band and locality metrics, and plots.

The method is described in [docs/](docs/Hybrid_Quantum_Classical_Graph_Partitioning_Algorithm_for_Domain_Decomposition.pdf).

## Interfaces

The desktop app and the command line read and write the same files, so you can switch between them.

### Desktop app

A native Qt 6 app for Ubuntu 26.04. It shows the workspace as a project tree (matrices, simulations and their stages, presets, tuning studies, runs, batches, quantum hardware) and lets you:

- edit simulations, with per-field validation, undo/redo and a live coarsening preview;
- save, load and compare presets;
- run simulations with a live log and stage progress;
- compare runs and export plots as PNG, SVG or CSV;
- edit the batch configuration and launch batches;
- run tuning studies and apply their best parameters;
- probe the D-Wave and QLM backends;
- read the documentation of any parameter with F1.

```sh
./run.sh                                       # opens the last workspace (default: this repository)
./run.sh --desktop --workspace ~/hdd-projects/blade
packaging/linux/install-launcher.sh            # add HDD Studio to the application menu (--remove to undo)
```

Jobs run as separate processes that keep a record and a log in `<workspace>/.hdd/jobs/`. When you quit with jobs running, the app offers to leave them running; opening the workspace again shows their progress, or their result if they finished meanwhile.

### Command line

```sh
./run.sh simulations/simulation_01                 # one simulation
./run.sh --run_batch                               # every configured batch case
./run.sh --run_batch --dry-run                     # list the cases without running
./run.sh --run_batch --nohup                       # run the batch in the background
./run.sh --tune simulations/simulation_01 --auto   # print auto-selected parameters
./run.sh --qlm_inspect --help                      # inspect a QLM backend
```

A simulation's `simulation_config.json` names its matrix (`input_matrix`, a folder in `matrices/`). Results go to `simulations/<sim>/results/run_<timestamp>/`.

## Parameter tuning

```sh
./run.sh --tune simulations/simulation_01 --n-trials 30 --objectives edge_cut,imbalance    # Pareto study (NSGA-II)
./run.sh --tune simulations/simulation_01 --objectives edge_cut \
        --free k_target,partitioning_strategy --sampler tpe                               # single objective, k and method free
./run.sh --tune --resume simulations/simulation_01/tuning/study_<timestamp>               # continue a study
```

Studies are saved in `simulations/<sim>/tuning/study_<timestamp>/`, with one normal run folder per trial. Every run, from any interface, is also appended to `tuning/history.jsonl`, which later studies use as a warm start. See [src/libs/tuning/](src/libs/tuning/__init__.py).

## Workspaces

Project data (`matrices/`, `simulations/`, `batch/`, `tuning/`) lives in a workspace. By default that is this repository. To keep data elsewhere, set `HDD_WORKSPACE`; every interface and every job it starts then reads and writes only there:

```sh
HDD_WORKSPACE=~/hdd-projects/blade ./run.sh
HDD_WORKSPACE=~/hdd-projects/blade ./run.sh simulations/simulation_01
```

Simulation paths on the command line are relative to the workspace.

## Repository layout

| Folder | Contents |
| --- | --- |
| [src/](src/README.md) | Scientific pipeline (`libs/`), application layer (`hdd/services`) and desktop app (`hdd/studio`) |
| [simulations/](simulations/README.md) | Simulations: configuration, presets and run results |
| [matrices/](matrices/README.md) | Shared matrix library, one folder per matrix |
| [batch/](batch/README.md) | Batch configuration and benchmark runs |
| `tuning/` | Run history used to warm-start tuning studies |
| `notebooks/` | Analysis notebooks and plotting helpers |
| `packaging/` | Ubuntu application-menu launcher |
| `tests/` | Test suite |
| `docs/` | Paper |

Setting up the D-Wave Leap and QLM / myQLM backends is covered in [the QA backend README](src/libs/multilevel_scheme/partitioning/qa/README.md).

## Tests

```sh
pip install -e ".[gui,dev]"
QT_QPA_PLATFORM=offscreen python -m pytest
```

## License

[MIT](LICENSE)
