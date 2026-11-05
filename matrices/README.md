# Shared Matrix Library (`matrices/`)

The pipeline is matrix-agnostic: any **square sparse matrix** can be partitioned and reordered. Each folder in `matrices/` holds one matrix in Matrix Market (`.mtx`) format, described by a `matrix.json`. Any simulation (`simulations/`) or batch study (`batch/`) can use any matrix, so a matrix is stored once however many simulations use it. Where it comes from does not matter (FEM stiffness or mass matrices from ANSYS/FEniCS/Abaqus, graph Laplacians, SuiteSparse, or generated).

## Layout

```text
matrices/
└── simpleblade_t14mm_h60_5mm_base/
    ├── matrix.json                                 # {"name", "file", "description"?}  (tracked)
    └── Ksparse_SimpleBlade_t14mm_h60_5mm_Base.mtx  # the matrix (gitignored)
```

`matrix.json` names the file inside the folder:

```json
{
  "name": "SimpleBlade t14mm h60 5mm base",
  "file": "Ksparse_SimpleBlade_t14mm_h60_5mm_Base.mtx"
}
```

The `.mtx` files are gitignored because they can be large. After cloning, copy them into their folders, or add new matrices as described below.

## Adding a Matrix

- **Web Studio:** In **Single Run → Stage 1 Input Matrix**, click **Upload .mtx** (name it and choose the file), or a **Demo matrix** button to generate a synthetic test matrix. It is added here and selected for the current simulation.
- **By hand:** Create `matrices/<matrix_id>/`, copy the `.mtx` file into it, and write `matrix.json` as above. `<matrix_id>` may contain letters, digits, `_` and `-`.

If the matrix comes in fixed-size row blocks that must stay together (e.g. 3 DOFs per mesh node in 3D FEM), set the simulation's **Block size** (`dof_per_node`) to that size; otherwise leave it at 1.

A matrix can be deleted from the Studio only when no simulation and no batch configuration uses it.
