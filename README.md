# Hybrid Domain Decomposition

Reorders any square sparse matrix (`.mtx`) into $A' = P A P^\top$ by partitioning its graph with METIS, Quantum Annealing or QAOA. Everything runs on your machine.

## Install

```sh
git clone https://github.com/orlandomotapires/hybrid_domain_decomposition.git
cd hybrid_domain_decomposition

conda create -n hdd python=3.14 -y
conda activate hdd

pip install -e ".[gui]"
packaging/linux/install-launcher.sh      # add HDD Studio to the application menu (--remove to undo)
```

## Run

```sh
./run.sh                                       # open the desktop app
./run.sh --desktop --workspace ~/hdd-projects/blade

./run.sh simulations/simulation_01             # run one simulation
./run.sh --run_batch                           # run the batch study
./run.sh --tune simulations/simulation_01 --auto
```

## Test

```sh
pip install -e ".[gui,dev]"
QT_QPA_PLATFORM=offscreen python -m pytest
```

Everything else (how the pipeline works, the desktop app, the command line, tuning, workspaces, quantum backends) is in the [wiki](docs/wiki/README.md).

## License

[MIT](LICENSE)
