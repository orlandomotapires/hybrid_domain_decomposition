# Simulations (`simulations/`)

A **simulation** is one configured pipeline run: which matrix to permute, its parameter presets, and its results. The desktop app lists each simulation (`simulation_01`, `simulation_02`, …) under **Simulations** in the project tree, with one page per pipeline stage.

## Layout

```text
simulations/
└── simulation_01/
    ├── data/
    │   ├── simulation_config.json        # Input matrix, active parameter preset, enabled save_output artifacts
    │   ├── simulation_parameters.json    # Default parameter preset (general, coarsening, partitioning, refinement)
    │   └── <custom_preset>.json          # Optional extra presets created in the Studio
    └── results/
        └── run_YYYYmmdd_HHMMSS_ffffff/   # One folder per run (gitignored)
```

`simulation_config.json` points at a matrix in the shared library ([`matrices/`](../matrices/README.md)):

```json
{
  "input_matrix": "simpleblade_t14mm_h60_5mm_base",
  "parameters_file_path": "simulation_parameters.json",
  "save_output": ["matrix_permuted", "run_metrics", "run_simulation_parameters", "permutation", "coarsened_graph"]
}
```

Each run also writes `run_inputs.json`, which records exactly which matrix file it used.

## Creating a Simulation

- **Desktop app:** **File → New simulation…** (Ctrl+Shift+N). Leave the name empty for the next `simulation_NN`, pick a matrix, and optionally copy parameters from another simulation.
- **CLI:** Copy an existing folder without its results (`mkdir -p simulations/simulation_04 && cp -r simulations/simulation_01/data simulations/simulation_04/`), set `input_matrix`, then run `./run.sh simulations/simulation_04`.
