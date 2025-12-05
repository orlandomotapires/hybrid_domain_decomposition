"""
Validation Pipeline for Quantum Graph Partitioning

This module provides comprehensive validation for each step of the QGP pipeline:
1. Matrix to Graph conversion
2. Coarsening phase
3. QUBO formulation
4. Recursive annealing
5. Partition lifting
6. Matrix permutation
"""

from .matrix_to_graph_validation import validate_matrix_to_graph
from .coarsening_validation import validate_coarsening_phase, validate_coarsening_chain
from .qubo_validation import validate_qubo_phase, validate_qubo_formulation
from .annealing_validation import (
    validate_recursive_annealing_phase,
    validate_anneal_bipartition,
    validate_recursive_kway_partition
)
from .lifting_validation import validate_lifting_phase
from .permutation_validation import validate_matrix_permutation
from .full_pipeline_validation import validate_full_pipeline

__all__ = [
    # New 6-step validation functions
    'validate_matrix_to_graph',
    'validate_coarsening_phase',
    'validate_qubo_phase',
    'validate_recursive_annealing_phase',
    'validate_lifting_phase',
    'validate_matrix_permutation',
    'validate_full_pipeline',
    # Legacy validation functions (more detailed)
    'validate_coarsening_chain',
    'validate_qubo_formulation',
    'validate_anneal_bipartition',
    'validate_recursive_kway_partition',
]
