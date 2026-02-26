"""
Full Pipeline Validation
Orchestrates all 6 validation steps in sequence.
"""
from .matrix_to_graph_validation import validate_matrix_to_graph
from .coarsening_validation import validate_coarsening_phase
from .qubo_validation import validate_qubo_phase
from .annealing_validation import validate_recursive_annealing_phase
from .lifting_validation import validate_lifting_phase
from .permutation_validation import validate_matrix_permutation


def validate_full_pipeline(
    # Step 1: Matrix to Graph
    matrix_k,
    matrix_m,
    graph_k,
    diag_k,
    # Step 2: Coarsening
    coarse_chain,
    maps=None,
    # Step 3: QUBO (optional, set to None if not applicable)
    Q=None,
    qubo_graph=None,  # Graph used for QUBO formulation (if different from coarsest)
    num_partitions_qubo=2,
    # Step 4: Recursive Annealing
    coarse_partition=None,
    num_partitions=None,
    # Step 5: Lifting
    final_partition=None,
    # Step 6: Matrix Permutation
    permuted_matrix_k=None,
    permuted_matrix_m=None,
    permutation=None,
    partition_for_permutation=None,  # Partition used to create permutation (may differ from final_partition)
    # Control
    verbose=False,
    skip_steps=None
):
    """
    Validate the entire QGP (Quantum Graph Partitioning) pipeline.
    
    This function runs all 6 validation steps in sequence:
    1. Matrix to Graph conversion
    2. Coarsening phase
    3. QUBO formulation (optional)
    4. Recursive annealing
    5. Partition lifting
    6. Matrix permutation
    
    Args:
        matrix_k: Original K sparse matrix
        matrix_m: Original M sparse matrix (can be None)
        graph_k: Converted graph from K matrix
        diag_k: Diagonal values used for node weights
        coarse_chain: List of coarsened graphs
        Q: QUBO matrix (optional, for step 3)
        num_partitions_qubo: Number of partitions for QUBO (typically 2)
        coarse_partition: Partition on coarsest graph
        num_partitions: Number of partitions (k)
        final_partition: Lifted partition on original graph
        permuted_matrix_k: Permuted K matrix
        permuted_matrix_m: Permuted M matrix (optional)
        permutation: Permutation array
        verbose: If True, print detailed validation for each step
        skip_steps: List of step numbers to skip (e.g., [3] to skip QUBO validation)
    
    Raises:
        ValueError: If any validation step fails
    """
    if skip_steps is None:
        skip_steps = []
    
    print("=" * 80)
    print("FULL PIPELINE VALIDATION")
    print("=" * 80)
    print()
    
    # Step 1: Matrix to Graph
    if 1 not in skip_steps:
        validate_matrix_to_graph(
            matrix_k=matrix_k,
            matrix_m=matrix_m,
            graph_k=graph_k,
            diag_k=diag_k,
            verbose=verbose
        )
        print()
    else:
        print("⊘ STEP 1 SKIPPED: Matrix to Graph conversion")
        print()
    
    # Step 2: Coarsening
    if 2 not in skip_steps:
        validate_coarsening_phase(
            original_graph=graph_k,
            coarse_chain=coarse_chain,
            maps=maps,
            verbose=verbose
        )
        print()
    else:
        print("⊘ STEP 2 SKIPPED: Coarsening phase")
        print()
    
    # Step 3: QUBO (optional)
    if 3 not in skip_steps:
        if Q is not None:
            # Use provided qubo_graph if available, otherwise use coarsest graph
            graph_for_qubo = qubo_graph if qubo_graph is not None else coarse_chain[-1]
            validate_qubo_phase(
                graph=graph_for_qubo,
                Q=Q,
                num_partitions=num_partitions_qubo,
                verbose=verbose
            )
            print()
        else:
            print("⊘ STEP 3 SKIPPED: QUBO formulation (Q not provided)")
            print()
    else:
        print("⊘ STEP 3 SKIPPED: QUBO formulation")
        print()
    
    # Step 4: Recursive Annealing
    if 4 not in skip_steps:
        if coarse_partition is not None and num_partitions is not None:
            coarsest_graph = coarse_chain[-1]
            validate_recursive_annealing_phase(
                graph=coarsest_graph,
                partition=coarse_partition,
                num_partitions=num_partitions,
                verbose=verbose
            )
            print()
        else:
            raise ValueError("❌ Step 4 validation requires coarse_partition and num_partitions")
    else:
        print("⊘ STEP 4 SKIPPED: Recursive annealing")
        print()
    
    # Step 5: Lifting
    if 5 not in skip_steps:
        if final_partition is not None:
            validate_lifting_phase(
                original_graph=graph_k,
                coarse_chain=coarse_chain,
                coarse_partition=coarse_partition,
                final_partition=final_partition,
                maps=maps,
                verbose=verbose
            )
            print()
        else:
            raise ValueError("❌ Step 5 validation requires final_partition")
    else:
        print("⊘ STEP 5 SKIPPED: Partition lifting")
        print()
            
    # Step 6: Matrix Permutation
    if 6 not in skip_steps:
        if permuted_matrix_k is not None and permutation is not None:
            # Use partition_for_permutation if provided, otherwise fall back to final_partition
            partition_to_validate = partition_for_permutation if partition_for_permutation is not None else final_partition
            validate_matrix_permutation(
                original_matrix=matrix_k,
                permuted_matrix=permuted_matrix_k,
                permutation=permutation,
                partition=partition_to_validate,
                verbose=verbose
            )
            print()
            
            # Also validate M matrix if provided
            if permuted_matrix_m is not None and matrix_m is not None:
                if verbose:
                    print("=" * 80)
                    print("STEP 6b: MATRIX M PERMUTATION VALIDATION")
                    print("=" * 80)
                validate_matrix_permutation(
                    original_matrix=matrix_m,
                    permuted_matrix=permuted_matrix_m,
                    permutation=permutation,
                    partition=partition_to_validate,
                    verbose=verbose
                )
                print()
        else:
            raise ValueError("❌ Step 6 validation requires permuted_matrix_k and permutation")
    else:
        print("⊘ STEP 6 SKIPPED: Matrix permutation")
        print()
    
    # Final summary
    print("=" * 80)
    print("✅ FULL PIPELINE VALIDATION PASSED")
    print("=" * 80)
    steps_validated = [i for i in range(1, 7) if i not in skip_steps]
    print(f"All {len(steps_validated)} validation steps passed successfully.")
    if skip_steps:
        print(f"Skipped steps: {skip_steps}")
