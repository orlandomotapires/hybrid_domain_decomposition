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

- **Desktop app:** **File → Import matrix…** copies a `.mtx` file into the library under the name you give it. **File → Generate demo matrix…** adds a synthetic test matrix (see below). Pick the matrix for a simulation on its **Input matrix** page.
- **By hand:** create `matrices/<matrix_id>/`, copy the `.mtx` file into it and write `matrix.json` as above. `<matrix_id>` may contain letters, digits, `_` and `-`.

### Generate a test matrix

**File → Generate demo matrix…** offers two kinds:

- **Random sparse:** a square matrix you size yourself.
  - **Size:** n, for an n × n matrix. The pipeline only partitions square matrices.
  - **Nonzeros** or **Density:** the same number seen two ways (density = nonzeros / n²). Edit either one and the other follows. The count includes the diagonal, which is always full, so there are at least n nonzeros. A symmetric pattern stores its off-diagonal entries in mirrored pairs, so an odd count drops by one; the dialog says so.
  - **Symmetry:**
    - *Symmetric*: A = Aᵀ and positive definite, like a stiffness matrix.
    - *Structurally symmetric*: the same pattern above and below the diagonal, with different values.
    - *Unsymmetric*: the upper and lower patterns are independent.
  - **Seed:** the same seed gives the same matrix.

  The nonzeros are placed near the diagonal, and then rows and columns are shuffled with one random permutation. The matrix looks unstructured, but a good reordering recovers the band, so the effect of partitioning and permutation is easy to see. Off-diagonal values are negative and every row's diagonal outweighs the rest of the row, so the matrix is nonsingular and its diagonal gives positive node weights. Up to 1,000,000 rows and 20,000,000 nonzeros.
- **FEM mesh:** the stiffness-like matrix of a 3D brick mesh (26 neighbours per node), numbered in a scrambled order. Set the nodes along each axis and the rows (degrees of freedom) per node.

If the matrix comes in fixed-size row blocks that must stay together (for example 3 degrees of freedom per node in 3D FEM), set the simulation's **Rows per graph node** (`dof_per_node`) to that size; otherwise leave it at 1.

## Delete a matrix

In the app, right-click the matrix in the project tree. A matrix can be deleted only when no simulation and no batch configuration uses it.

Matrix features used by [parameter tuning](parameter-tuning.md) are cached next to the matrix in `features.json` (not tracked).
