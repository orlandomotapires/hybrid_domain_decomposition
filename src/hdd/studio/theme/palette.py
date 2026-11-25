"""Plot styling shared by every chart: pyqtgraph on screen, matplotlib for export.

Colour is assigned by job, not by taste:
- categorical series take ``tokens.plot.series`` slots in fixed order, never cycled;
- a method always wears the same slot, in every chart;
- a baseline that only gives context wears ``tokens.plot.reference`` (grey).
"""

from __future__ import annotations

from .tokens import Tokens

#: Fixed slot per partitioning method, so a method keeps its colour across charts.
METHOD_SLOT: dict[str, int] = {
    "metis_partitioning": 0,
    "quantum_annealing": 1,
    "quantum_approximation_optimizer": 2,
}


def series_color(tokens: Tokens, slot: int) -> str:
    """Colour of categorical ``slot``. Slots are never cycled: fold or facet extra series."""
    series = tokens.plot.series
    if not 0 <= slot < len(series):
        raise IndexError(
            f"categorical slot {slot} is outside the {len(series)}-slot palette; "
            "fold extra series into 'other' or use small multiples instead of cycling colours"
        )
    return series[slot]


def method_color(tokens: Tokens, method: str) -> str:
    return series_color(tokens, METHOD_SLOT[method])


def style_plot(plot_item, tokens: Tokens, *, grid: bool = True) -> None:
    """Apply chart chrome (surface, axes, grid) to a pyqtgraph ``PlotItem``."""
    import pyqtgraph as pg

    plot = tokens.plot
    plot_item.getViewBox().setBackgroundColor(plot.surface)
    for name in ("left", "bottom", "right", "top"):
        axis = plot_item.getAxis(name)
        axis.setPen(pg.mkPen(plot.axis, width=1))
        axis.setTextPen(pg.mkPen(plot.muted))
    plot_item.showGrid(x=grid, y=grid, alpha=0.35 if grid else 0)


def matplotlib_rc(tokens: Tokens) -> dict[str, object]:
    """``rcParams`` overrides giving matplotlib figures the same look (used for export)."""
    from cycler import cycler

    plot = tokens.plot
    return {
        "figure.facecolor": plot.surface,
        "axes.facecolor": plot.surface,
        "savefig.facecolor": plot.surface,
        "axes.edgecolor": plot.axis,
        "axes.labelcolor": plot.muted,
        "axes.titlecolor": plot.ink,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": cycler(color=list(plot.series)),
        "grid.color": plot.grid,
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "xtick.color": plot.muted,
        "ytick.color": plot.muted,
        "text.color": plot.ink,
        "lines.linewidth": 2.0,
        "legend.frameon": False,
        "font.family": "sans-serif",
    }
