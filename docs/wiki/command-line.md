# Command line

Everything runs through `run.sh` at the repository root. It picks a Python that has the dependencies (see [Installation](installation.md)).

```sh
./run.sh                                   # open the desktop app (same as --desktop)
./run.sh --desktop [--workspace DIR] [--theme system|light|dark]
./run.sh <simulation_dir>                  # run one simulation
./run.sh --run_batch [--dry-run] [--nohup] [--stop-on-error]
./run.sh --tune <simulation_dir> [options]
./run.sh --qlm_inspect [options]
./run.sh --help
```

Simulation paths are relative to the [workspace](workspaces.md), for example `simulations/simulation_01`.

## One simulation

```sh
./run.sh simulations/simulation_01
```

Runs the simulation with its active parameter preset and writes `simulations/simulation_01/results/run_<timestamp>/` (see [How it works](how-it-works.md#what-a-run-writes)). The log goes to the terminal and to `run_log` in the run folder.

## Batch study

```sh
./run.sh --run_batch --dry-run         # list the cases without running them
./run.sh --run_batch                   # run every case
./run.sh --run_batch --nohup           # run in the background; output goes to the batch folder's batch.log
./run.sh --run_batch --stop-on-error   # stop at the first failed case
```

See [Batch studies](batch-studies.md) for the configuration and the output.

## Parameter tuning

```sh
./run.sh --tune simulations/simulation_01 --auto
./run.sh --tune simulations/simulation_01 --n-trials 30 --objectives edge_cut,imbalance
./run.sh --tune --resume simulations/simulation_01/tuning/study_<timestamp>
```

All options are in [Parameter tuning](parameter-tuning.md#command-line).

## QLM inspector

```sh
./run.sh --qlm_inspect                          # available QPUs and recent jobs
./run.sh --qlm_inspect --qpu qat.qpus:QSolidQPU10
./run.sh --qlm_inspect --job-id <id> --show-result
./run.sh --qlm_inspect --probe-qpu qat.qpus:QSolidQPU10 --probe-start 4 --probe-stop 20
./run.sh --qlm_inspect --usage-summary
```

Needs myQLM and QLM credentials; see [Quantum backends](quantum-backends.md). `--help` lists every option.

## Installed commands

`pip install -e .` also installs these commands into the environment:

| Command | Same as |
| --- | --- |
| `hdd-studio` | `./run.sh --desktop` |
| `hdd-run <simulation_dir>` | `./run.sh <simulation_dir>` |
| `hdd-tune …` | `./run.sh --tune …` |
| `hdd-qlm-inspect …` | `./run.sh --qlm_inspect …` |

## Environment variables

| Variable | Effect |
| --- | --- |
| `HDD_WORKSPACE` | The workspace folder (see [Workspaces](workspaces.md)) |
| `HDD_PYTHON` | The Python `run.sh` tries first |
| `HDD_HISTORY_PATH` | Where the tuning run history is written (default `tuning/history.jsonl`) |
| `HDD_DISABLE_HISTORY=1` | Do not append runs to the history |
| `HDD_SIMULATED_QA_NODE_LIMIT` | Largest coarse graph simulated annealing accepts (default 3000; its dense QUBO grows with the square of the node count) |
