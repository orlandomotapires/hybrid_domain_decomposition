"""Example plots for the visual prototype (pyqtgraph)."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from ..theme import Theme
from ..theme.palette import series_color, style_plot
from . import sample_data


class _ThemedPlot(pg.PlotWidget):
    """Plot widget that follows the application theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(self.Shape.NoFrame)
        self.getPlotItem().setMenuEnabled(False)
        self.getPlotItem().hideButtons()
        self.getPlotItem().setContentsMargins(4, 10, 14, 4)
        Theme.instance().changed.connect(self.restyle)

    def restyle(self) -> None:
        tokens = Theme.instance().tokens
        self.setBackground(tokens.plot.surface)
        style_plot(self.getPlotItem(), tokens, grid=self._grid())
        font = Theme.instance().ui_font(small=True)
        for name in ("left", "bottom"):
            axis = self.getPlotItem().getAxis(name)
            axis.setTickFont(font)
            axis.label.setFont(font)
        self.redraw()

    def _grid(self) -> bool:
        return True

    def redraw(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def fit(self) -> None:
        self.getPlotItem().autoRange()

    def _legend(self) -> pg.LegendItem:
        tokens = Theme.instance().tokens
        plot_item = self.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.scene().removeItem(plot_item.legend)
            plot_item.legend = None
        surface = QColor(tokens.plot.surface)
        surface.setAlpha(235)
        return plot_item.addLegend(
            offset=(-12, 12),
            labelTextColor=tokens.plot.ink,
            labelTextSize=f"{tokens.type.small_pt:g}pt",
            pen=pg.mkPen(tokens.plot.grid),
            brush=pg.mkBrush(surface),
            verSpacing=-2,
        )


class SparsityPlot(_ThemedPlot):
    """Sparsity pattern coloured by partition; couplings between parts drawn in ink."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ordering = "permuted"
        self._data = sample_data.decomposition()
        plot_item = self.getPlotItem()
        plot_item.setAspectLocked(True)
        plot_item.invertY(True)
        plot_item.setLabel("bottom", "Column")
        plot_item.setLabel("left", "Row")
        self.restyle()

    def _grid(self) -> bool:
        return False

    def ordering(self) -> str:
        return self._ordering

    def set_ordering(self, ordering: str) -> None:
        if ordering not in ("original", "permuted"):
            raise ValueError(ordering)
        self._ordering = ordering
        self.redraw()

    def redraw(self) -> None:
        tokens = Theme.instance().tokens
        data = self._data
        plot_item = self.getPlotItem()
        plot_item.clear()
        legend = self._legend()
        position = data.positions(self._ordering)
        row_pos, col_pos = position[data.rows], position[data.cols]
        cut = data.is_cut()
        for part in range(data.k):
            mask = (data.part[data.rows] == part) & ~cut
            item = pg.ScatterPlotItem(
                x=col_pos[mask],
                y=row_pos[mask],
                size=3,
                symbol="s",
                pen=None,
                brush=pg.mkBrush(series_color(tokens, part)),
                pxMode=True,
            )
            plot_item.addItem(item)
            legend.addItem(self._key(series_color(tokens, part)), f"Part {part + 1}")
        cut_item = pg.ScatterPlotItem(
            x=col_pos[cut], y=row_pos[cut], size=3, symbol="s", pen=None, brush=pg.mkBrush(tokens.plot.ink), pxMode=True
        )
        plot_item.addItem(cut_item)
        legend.addItem(self._key(tokens.plot.ink), "Coupling between parts")
        plot_item.setRange(xRange=(-0.5, data.n - 0.5), yRange=(-0.5, data.n - 0.5), padding=0.02)

    @staticmethod
    def _key(color: str) -> pg.ScatterPlotItem:
        """Legend swatch, larger than the 3 px data marks so the colour is readable."""
        return pg.ScatterPlotItem(size=9, symbol="s", pen=None, brush=pg.mkBrush(color))

    def fit(self) -> None:
        n = self._data.n
        self.getPlotItem().setRange(xRange=(-0.5, n - 0.5), yRange=(-0.5, n - 0.5), padding=0.02)


class LocalityPlot(_ThemedPlot):
    """Share of nonzeros inside a band around the diagonal, before and after the permutation."""

    WIDTHS = np.linspace(0.0, 12.0, 97)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = sample_data.decomposition()
        plot_item = self.getPlotItem()
        plot_item.setLabel("bottom", "Half-bandwidth (% of n)")
        plot_item.setLabel("left", "Nonzeros inside the band (%)")
        plot_item.setMouseEnabled(x=True, y=False)
        self._readout = pg.TextItem(anchor=(0, 1))
        self._cursor = pg.InfiniteLine(angle=90, movable=False)
        self._curves: dict[str, np.ndarray] = {}
        self._proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)
        self.restyle()

    def redraw(self) -> None:
        tokens = Theme.instance().tokens
        plot_item = self.getPlotItem()
        plot_item.clear()
        legend = self._legend()
        self._curves = {
            "original": self._data.locality_curve("original", self.WIDTHS),
            "permuted": self._data.locality_curve("permuted", self.WIDTHS),
        }
        original = plot_item.plot(self.WIDTHS, self._curves["original"], pen=pg.mkPen(tokens.plot.reference, width=2))
        permuted = plot_item.plot(self.WIDTHS, self._curves["permuted"], pen=pg.mkPen(series_color(tokens, 0), width=2))
        legend.addItem(permuted, "Permuted")
        legend.addItem(original, "Original")
        self._cursor.setPen(pg.mkPen(tokens.plot.axis, width=1))
        self._cursor.setVisible(False)
        self._readout.setColor(tokens.plot.ink)
        self._readout.setFont(Theme.instance().ui_font(small=True))
        self._readout.setVisible(False)
        plot_item.addItem(self._cursor, ignoreBounds=True)
        plot_item.addItem(self._readout, ignoreBounds=True)
        self.fit()

    def fit(self) -> None:
        self.getPlotItem().setRange(xRange=(0, float(self.WIDTHS[-1])), yRange=(0, 100), padding=0.03)

    def readout_text(self, width_pct: float) -> str:
        """Text of the hover read-out at a given half-bandwidth."""
        index = int(np.abs(self.WIDTHS - width_pct).argmin())
        width = self.WIDTHS[index]
        return (
            f"Band {width:.2f} % of n\n"
            f"Permuted {self._curves['permuted'][index]:.1f} %\n"
            f"Original {self._curves['original'][index]:.1f} %"
        )

    def _on_mouse_moved(self, event) -> None:
        view_box = self.getPlotItem().getViewBox()
        scene_pos = event[0]
        inside = view_box.sceneBoundingRect().contains(scene_pos)
        self._cursor.setVisible(inside)
        self._readout.setVisible(inside)
        if not inside:
            return
        x = float(np.clip(view_box.mapSceneToView(scene_pos).x(), self.WIDTHS[0], self.WIDTHS[-1]))
        self._cursor.setPos(x)
        self._readout.setText(self.readout_text(x))
        (x_min, x_max), (y_min, _y_max) = view_box.viewRange()
        anchor_right = x > (x_min + x_max) / 2
        self._readout.setAnchor((1, 1) if anchor_right else (0, 1))
        offset = (x_max - x_min) * 0.01
        self._readout.setPos(x - offset if anchor_right else x + offset, y_min + (100 - y_min) * 0.04)
