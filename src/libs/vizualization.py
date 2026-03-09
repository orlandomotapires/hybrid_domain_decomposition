import matplotlib.pyplot as plt
from scipy import sparse


def plot_sparsity_panel(
    A,
    B,
    name_a: str = "K",
    name_b: str = "M",
    figsize=(12, 5),
    markersize: float = 0.5,
    *,
    show: bool = True,
    save_path: str | None = None,
    dpi: int = 200,
):
    """Plot sparsity patterns of two matrices side-by-side.

    Args:
        show: If True, calls plt.show(). For scripts/headless usage, set False.
        save_path: If provided, saves the figure to this path.
    """
    fig, axes = plt.subplots(1, 2, figsize=figsize, constrained_layout=True)

    for ax, mat, title in zip(axes, [A, B], [name_a, name_b]):
        if sparse.issparse(mat):
            ax.spy(mat, markersize=markersize, color="black")
        else:
            ax.spy(mat != 0, markersize=markersize, color="black")
        ax.set_title(f"Sparsity pattern: {title}")
        ax.set_xlabel("Column index")
        ax.set_ylabel("Row index")

    if save_path:
        fig.savefig(save_path, dpi=dpi)

    if show:
        plt.show()

    return fig, axes