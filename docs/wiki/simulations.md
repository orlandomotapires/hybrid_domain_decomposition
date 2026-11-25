# Simulations

A simulation is one configured pipeline run: which matrix to reorder, its parameter presets, and its results. The repository comes with `simulation_01` to `simulation_03`.

## Layout

```text
simulations/
└── simulation_01/
    ├── data/
    │   ├── simulation_config.json        # input matrix, active preset, files each run writes
    │   ├── simulation_parameters.json    # the default parameter preset
    │   └── <preset>.json                 # optional extra presets
    ├── results/
    │   └── run_YYYYmmdd_HHMMSS_ffffff/   # one folder per run (not tracked by git)
    └── tuning/
        └── study_YYYYmmdd_HHMMSS/        # tuning studies (not tracked by git)
```

`simulation_config.json` names a matrix from the [matrix library](matrix-library.md) and the active preset:

```json
{
  "input_matrix": "simpleblade_t14mm_h60_5mm_base",
  "parameters_file_path": "simulation_parameters.json",
  "save_output": ["matrix_permuted", "run_metrics", "run_simulation_parameters", "permutation", "coarsened_graph"]
}
```

A preset holds the parameters of every stage: `general_parameters` (block size, seed), `coarsening_parameters`, `partitioning_parameters` (method, k, balance tolerance and the settings of each method) and `uncoarsening_parameters` (refinement). Every parameter is described in the [parameter reference](parameter-reference.md).

## Create a simulation

- **Desktop app:** **File → New simulation…** (Ctrl+Shift+N). Leave the name empty for the next `simulation_NN`, pick a matrix, and start from defaults adapted to that matrix or copy another simulation's parameters.
- **By hand:** copy an existing simulation without its results, then set `input_matrix`:

  ```sh
  mkdir -p simulations/simulation_04
  cp -r simulations/simulation_01/data simulations/simulation_04/
  ./run.sh simulations/simulation_04
  ```

In the app a simulation can also be renamed or deleted (Simulation menu); deleting removes its presets, runs and tuning studies.

## Presets

A preset is one parameter set. The app saves the editor's state as a new preset (**Save as preset…**), loads a preset into the editor, makes one active, compares any two (or the editor against a preset or another simulation), and deletes presets. The active preset is the one runs use.

## Before running

The simulation page checks two things as you edit:

- the parameters are valid (errors also appear under each field and in the **Problems** panel);
- the coarsening can reach its target range on this matrix. If not, every run would fail with "Unable to coarsen graph into the requested node-count range"; widen the limits, raise **Maximum levels** or lower the **Reduction ratio** on the **Coarsening** page, whose preview shows each level as you type.

For quantum methods, the **Partitioning** page estimates the number of QPU submissions and reads (or circuit jobs and shots) a run will need.
