# Matrix Workspaces (`matrices/`)

Each subfolder inside `matrices/` (such as `matrix_01`, `matrix_02`, `matrix_03`) is a self-contained workspace for a pair of sparse matrices ($K$ and $M$). The pipeline is completely agnostic to the physical origin of the matrices (whether exported from ANSYS, FEniCS, Abaqus, Suitesparse, or generated synthetically).

## Workspace Layout

```text
matrices/
└── matrix_01/
    ├── data/
    │   ├── simulation_config.json        # Active parameter preset file, input .mtx filenames, enabled save_output artifacts
    │   ├── simulation_parameters.json    # Default parameter preset (general, coarsening, partitioning, refinement)
    │   ├── <custom_preset>.json          # Optional additional parameter presets created in the Studio
    │   └── matrices/                     # Matrix Market (.mtx) files for K and M (gitignored for large meshes)
    └── results/
        └── run_YYYYmmdd_HHMMSS_ffffff/   # Timestamped outputs from each simulation run (gitignored)
```

## Adding a New Matrix Workspace

- **Via the Web Studio:** Click **+ New** in the top bar of the **Pipeline** tab, enter a name (e.g. `matrix_04`), and upload your `.mtx` files or generate a demo 3D mesh in Stage 1.
- **Via the CLI:** Copy an existing folder (`cp -r matrices/matrix_01 matrices/matrix_04`), place your `.mtx` files in `matrices/matrix_04/data/matrices/`, update `input_matrices` in `data/simulation_config.json`, and run `./run.sh matrices/matrix_04`.

