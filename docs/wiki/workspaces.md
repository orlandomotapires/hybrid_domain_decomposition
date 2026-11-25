# Workspaces

A workspace is the folder that holds a project's data:

```text
<workspace>/
├── matrices/       the matrix library
├── simulations/    simulations, their presets, runs and studies
├── batch/          batch configuration and runs
├── tuning/         run history used to warm-start tuning
└── .hdd/           workspace marker and the desktop app's job records
```

The repository itself is a workspace, so nothing needs setting up. Use a separate workspace to keep a project's data out of the repository.

## Choose the workspace

The workspace is resolved in this order:

1. the `HDD_WORKSPACE` environment variable;
2. the nearest folder, from the current directory upwards, that contains `.hdd/workspace.json`;
3. the repository the code runs from.

```sh
HDD_WORKSPACE=~/hdd-projects/blade ./run.sh                              # desktop app
HDD_WORKSPACE=~/hdd-projects/blade ./run.sh simulations/simulation_01    # one simulation
./run.sh --desktop --workspace ~/hdd-projects/blade
```

Every job a run starts (simulations, batches, tuning trials) reads and writes only in that workspace. Simulation paths on the command line are relative to it.

## In the desktop app

- **File → New workspace…** creates the folders and the marker in an empty folder and opens it.
- **File → Open workspace…** and **File → Open recent** switch workspaces. Running jobs can keep running in the workspace you leave.
- The app reopens the last workspace you used; the status bar shows which one is open.

Job records and logs are kept in `<workspace>/.hdd/jobs/`.
