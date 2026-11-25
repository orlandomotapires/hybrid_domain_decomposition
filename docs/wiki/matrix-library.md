# Matrix library

The pipeline works on any square sparse matrix: FEM stiffness or mass matrices (ANSYS, FEniCS, Abaqus), graph Laplacians, SuiteSparse matrices, or generated ones. Each matrix is stored once in `matrices/` and any simulation or batch can use it.

## Layout

```text
matrices/
└── simpleblade_t14mm_h60_5mm_base/
    ├── matrix.json                                 # {"name", "file", "description"?}  (tracked by git)
    └── Ksparse_SimpleBlade_t14mm_h60_5mm_Base.mtx  # the matrix, Matrix Market format (not tracked)
```

```json
{
  "name": "SimpleBlade t14mm h60 5mm base",
  "file": "Ksparse_SimpleBlade_t14mm_h60_5mm_Base.mtx"
}
```

The `.mtx` files are not in git because they can be large: after cloning, copy them into their folders.

## Add a matrix

- **Desktop app:** **File → Import matrix…** copies a `.mtx` file into the library under the name you give it. **File → Generate demo matrix…** adds a synthetic test matrix. Pick the matrix for a simulation on its **Input matrix** page.
- **By hand:** create `matrices/<matrix_id>/`, copy the `.mtx` file into it and write `matrix.json` as above. `<matrix_id>` may contain letters, digits, `_` and `-`.

If the matrix comes in fixed-size row blocks that must stay together (for example 3 degrees of freedom per node in 3D FEM), set the simulation's **Rows per graph node** (`dof_per_node`) to that size; otherwise leave it at 1.

## Delete a matrix

In the app, right-click the matrix in the project tree. A matrix can be deleted only when no simulation and no batch configuration uses it.

Matrix features used by [parameter tuning](parameter-tuning.md) are cached next to the matrix in `features.json` (not tracked).
