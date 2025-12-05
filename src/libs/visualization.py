"""
Visualization Module

Provides functions to visualize matrix sparsity patterns and partition structures.
"""

import matplotlib.pyplot as plt


def plot_matrix_sparsity(matrix, title, partition=None, figsize=(10, 10), 
                         markersize=0.5, show_boundaries=True):
    """
    Plot sparsity pattern of a matrix with optional partition boundaries.
    
    Args:
        matrix: Sparse matrix to visualize
        title: Plot title
        partition: Optional dict {node_id: partition_id} to show boundaries
        figsize: Figure size (width, height)
        markersize: Size of markers for non-zero entries
        show_boundaries: If True and partition provided, draw boundary lines
    
    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    # Plot sparsity pattern
    ax.spy(matrix, markersize=markersize, color='black')
    ax.set_title(title, fontsize=14)
    ax.set_xlabel('Column Index')
    ax.set_ylabel('Row Index')
    
    # Add partition boundary lines if provided
    if partition is not None and show_boundaries:
        # Calculate partition boundaries
        boundaries = []
        current_count = 0
        for part_id in sorted(set(partition.values())):
            count = sum(1 for p in partition.values() if p == part_id)
            current_count += count
            boundaries.append(current_count)
        
        # Draw lines
        for boundary in boundaries[:-1]:  # Skip last boundary (matrix edge)
            ax.axhline(y=boundary, color='red', linestyle='--', linewidth=1, alpha=0.7)
            ax.axvline(x=boundary, color='red', linestyle='--', linewidth=1, alpha=0.7)
    
    plt.tight_layout()
    return fig


def visualize_partition_results(
    original_matrix,
    permuted_matrix,
    partition,
    k_target,
    matrix_name="K",
    show_original=True,
    show_permuted=True,
    figsize=(10, 10),
    markersize=0.5
):
    """
    Visualize original and reordered matrix sparsity patterns side by side.
    
    Args:
        original_matrix: Original sparse matrix before reordering
        permuted_matrix: Permuted sparse matrix after reordering
        partition: Partition dict {node_id: partition_id}
        k_target: Number of partitions
        matrix_name: Name of matrix (e.g., "K" or "M")
        show_original: If True, show original matrix plot
        show_permuted: If True, show permuted matrix plot
        figsize: Figure size for each plot
        markersize: Size of markers for non-zero entries
    
    Returns:
        Tuple of (fig_original, fig_permuted) or individual figures if only one shown
    """
    fig_original = None
    fig_permuted = None
    
    if show_original:
        print(f"Plotting original {matrix_name} matrix...")
        fig_original = plot_matrix_sparsity(
            original_matrix,
            f"Original {matrix_name} Matrix - Sparsity Pattern",
            partition=None,
            figsize=figsize,
            markersize=markersize
        )
        plt.show()
    
    if show_permuted:
        print(f"Plotting reordered {matrix_name} matrix with partition boundaries...")
        fig_permuted = plot_matrix_sparsity(
            permuted_matrix,
            f"Reordered {matrix_name} Matrix - {k_target} Partitions (Red lines show boundaries)",
            partition=partition,
            figsize=figsize,
            markersize=markersize,
            show_boundaries=True
        )
        plt.show()
    
    # Print explanation
    if show_permuted and partition is not None:
        print(f"\n✓ Red dashed lines show the {k_target} partition boundaries")
        print(f"✓ Notice the block structure: nodes within same partition have denser connections")
    
    return fig_original, fig_permuted


def visualize_all_matrices(
    matrix_k_original,
    matrix_k_permuted,
    partition,
    k_target,
    matrix_m_original=None,
    matrix_m_permuted=None,
    figsize=(10, 10),
    markersize=0.5
):
    """
    Visualize all matrices (K and optionally M) before and after reordering.
    
    Args:
        matrix_k_original: Original K matrix
        matrix_k_permuted: Permuted K matrix
        partition: Partition dict {node_id: partition_id}
        k_target: Number of partitions
        matrix_m_original: Optional original M matrix
        matrix_m_permuted: Optional permuted M matrix
        figsize: Figure size for each plot
        markersize: Size of markers for non-zero entries
    
    Returns:
        Dict with all generated figures
    """
    print("=" * 80)
    print("MATRIX VISUALIZATION")
    print("=" * 80)
    
    figures = {}
    
    # Visualize K matrix
    print("\n[1/2] K Matrix Visualization")
    print("-" * 80)
    fig_k_orig, fig_k_perm = visualize_partition_results(
        original_matrix=matrix_k_original,
        permuted_matrix=matrix_k_permuted,
        partition=partition,
        k_target=k_target,
        matrix_name="K",
        show_original=True,
        show_permuted=True,
        figsize=figsize,
        markersize=markersize
    )
    figures['k_original'] = fig_k_orig
    figures['k_permuted'] = fig_k_perm
    
    # Visualize M matrix if provided
    if matrix_m_original is not None and matrix_m_permuted is not None:
        print("\n[2/2] M Matrix Visualization")
        print("-" * 80)
        fig_m_orig, fig_m_perm = visualize_partition_results(
            original_matrix=matrix_m_original,
            permuted_matrix=matrix_m_permuted,
            partition=partition,
            k_target=k_target,
            matrix_name="M",
            show_original=True,
            show_permuted=True,
            figsize=figsize,
            markersize=markersize
        )
        figures['m_original'] = fig_m_orig
        figures['m_permuted'] = fig_m_perm
    else:
        print("\n[2/2] M Matrix Visualization (skipped - not provided)")
    
    print("\n" + "=" * 80)
    print("✅ Visualization completed!")
    print("=" * 80)
    
    return figures
