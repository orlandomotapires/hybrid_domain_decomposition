# Updated Matrix Reordering Usage

## New Organized Directory Structure

The `reorder_and_save_matrices()` function now creates an organized directory structure:

```
results/
└── hybrid_ma.classical.fem.matrix_01/          # Matrix-specific folder
    ├── method_metis_k32_coarse_sorted_limit300_lambda2_reads1000_tol2.0_20251208_143022/
    │   ├── matrix_k_reordered.mtx
    │   ├── matrix_m_reordered.mtx
    │   ├── permutation.txt
    │   └── run_metadata.txt
    └── method_quantum_k16_coarse_modified_limit500_lambda1.5_reads2000_tol5.0_20251208_144513/
        ├── matrix_k_reordered.mtx
        ├── permutation.txt
        └── run_metadata.txt
```

## Updated Notebook Cell Example

Replace the matrix reordering cell (Cell 15) with:

```python
# Matrix reordering and export with organized structure
from libs.matrix_reordering import reorder_and_save_matrices

# Load M matrix if available
m_matrix_path = os.path.join(data_dir, "hybrid_ma.classical.fem.matrix_m.mtx")
try:
    A_M = load_mtx(m_matrix_path, 'M')
    has_m_matrix = A_M is not None
    if has_m_matrix:
        print(f"Loaded M matrix: shape={A_M.shape}, nnz={A_M.nnz}")
except:
    A_M = None
    has_m_matrix = False
    print("M matrix not found or couldn't be loaded")

# Prepare parameter dictionaries for metadata
coarsening_params = {
    'strategy': strategy,
    'limit': coarsen_limit,
    'max_levels': max_levels,
    'coarsen_ratio': coarsen_ratio,
    'max_node_weight': max_node_weight
}

annealing_params = {
    'balance_lambda': BALANCE_LAMBDA,
    'num_reads': NUM_READS,
    'balance_tolerance': BALANCE_TOLERANCE
}

# Reorder and save matrices with organized directory structure
result = reorder_and_save_matrices(
    matrix_k=A_K,
    partition=chosen_partition,
    k_target=K_TARGET,
    output_dir=os.path.join(os.getcwd(), "..", "results"),
    partition_method="metis",  # or "quantum" depending on chosen_partition
    matrix_m=A_M if has_m_matrix else None,
    save_permutation=True,
    verbose=True,
    original_matrix_filename=k_matrix_path,  # Pass the original filename
    coarsening_params=coarsening_params,
    annealing_params=annealing_params
)

print(f"\nResults saved to: {result['run_dir']}")

# Extract results for validation
permutation = result['permutation']
A_K_permuted = result['matrix_k_permuted']
A_M_permuted = result['matrix_m_permuted']
```

## Key Features

1. **Matrix-specific folders**: Each input matrix gets its own folder (e.g., `hybrid_ma.classical.fem.matrix_01`)
2. **Run-specific subfolders**: Each run gets a unique folder with parameters and timestamp
3. **Metadata file**: Each run includes a `run_metadata.txt` with all parameters
4. **Simplified filenames**: Within each run folder, files are simply named:
   - `matrix_k_reordered.mtx`
   - `matrix_m_reordered.mtx`
   - `permutation.txt`
   - `run_metadata.txt`

## Benefits

- ✅ Easy comparison between different parameter configurations
- ✅ No file overwrites - each run is preserved
- ✅ Clear organization by input matrix
- ✅ Full traceability with metadata files
- ✅ Timestamp ensures uniqueness even with identical parameters
