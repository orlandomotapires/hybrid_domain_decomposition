import matplotlib.pyplot as plt
from scipy import sparse

def plot_sparsity_panel(A, B, name_a="K", name_b="M", figsize=(12, 5), markersize=0.5):
    """Plot sparsity patterns of two matrices side-by-side."""
    fig, axes = plt.subplots(1, 2, figsize=figsize, constrained_layout=True)

    for ax, mat, title in zip(axes, [A, B], [name_a, name_b]):
        if sparse.issparse(mat):
            ax.spy(mat, markersize=markersize, color="black")
        else:
            ax.spy(mat != 0, markersize=markersize, color="black")
        ax.set_title(f"Sparsity pattern: {title}")
        ax.set_xlabel("Column index")
        ax.set_ylabel("Row index")

    plt.show()
    return fig, axes