"""Plot widgets: sparsity patterns and curves, styled by the theme."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from ..theme import Theme
from ..theme.palette import style_plot

#: Above this many nonzeros the pattern is drawn as a density image instead of one marker each.
EXACT_POINT_LIMIT = 400_000
DENSITY_BINS = 1024


@dataclass
class SparsityData:
    n: int
    rows: np.ndarray
    cols: np.ndarray
    labels: np.ndarray | None = None  # part of each row; None draws a plain pattern
    title: str = ""


class ThemedPlot(pg.PlotWidget):
    """Plot widget that restyles itself when the theme changes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(self.Shape.NoFrame)
        item = self.getPlotItem()
        item.setMenuEnabled(False)
        item.hideButtons()
        item.setContentsMargins(4, 10, 14, 4)
        Theme.instance().changed.connect(self.restyle)

    def grid(self) -> bool:
        return True

    def restyle(self) -> None:
        theme = Theme.instance()
        self.setBackground(theme.tokens.plot.surface)
        style_plot(self.getPlotItem(), theme.tokens, grid=self.grid())
        font = theme.ui_font(small=True)
        for name in ("left", "bottom"):
            axis = self.getPlotItem().getAxis(name)
            axis.setTickFont(font)
            axis.label.setFont(font)
        self.redraw()

    def redraw(self) -> None:
        raise NotImplementedError

    def fit(self) -> None:
        self.getPlotItem().autoRange()

    def legend(self) -> pg.LegendItem:
        tokens = Theme.instance().tokens
        item = self.getPlotItem()
        if item.legend is not None:
            item.legend.scene().removeItem(item.legend)
            item.legend = None
        surface = QColor(tokens.plot.surface)
        surface.setAlpha(235)
        return item.addLegend(
            offset=(-12, 12),
            labelTextColor=tokens.plot.ink,
            labelTextSize=f"{tokens.type.small_pt:g}pt",
            pen=pg.mkPen(tokens.plot.grid),
            brush=pg.mkBrush(surface),
            verSpacing=-2,
        )


def part_colors(parts: list[int]) -> dict[int, str]:
    """Categorical slots for up to 8 parts; evenly spaced hues beyond that (never cycled)."""
    series = Theme.instance().tokens.plot.series
    if len(parts) <= len(series):
        return {part: series[i] for i, part in enumerate(parts)}
    colors = {}
    for i, part in enumerate(parts):
        color = QColor.fromHsvF(i / len(parts), 0.65, 0.85)
        colors[part] = color.name()
    return colors


class SparsityView(ThemedPlot):
    """Nonzero pattern; coloured by the part of each row, couplings between parts in ink."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: SparsityData | None = None
        item = self.getPlotItem()
        item.setAspectLocked(True)
        item.invertY(True)
        item.setLabel("bottom", "Column")
        item.setLabel("left", "Row")
        self.restyle()

    def grid(self) -> bool:
        return False

    def set_data(self, data: SparsityData | None) -> None:
        self._data = data
        self.redraw()

    def data(self) -> SparsityData | None:
        return self._data

    @staticmethod
    def _key(color: str) -> pg.ScatterPlotItem:
        return pg.ScatterPlotItem(size=9, symbol="s", pen=None, brush=pg.mkBrush(color))

    def redraw(self) -> None:
        item = self.getPlotItem()
        item.clear()
        data = self._data
        if data is None:
            if item.legend is not None:
                item.legend.scene().removeItem(item.legend)
                item.legend = None
            return
        tokens = Theme.instance().tokens
        item.setTitle(data.title, color=tokens.plot.ink, size=f"{tokens.type.base_pt:g}pt")
        if data.rows.size > EXACT_POINT_LIMIT:
            self._draw_density(data)
        else:
            self._draw_points(data)
        self.fit()

    def _draw_points(self, data: SparsityData) -> None:
        tokens = Theme.instance().tokens
        item = self.getPlotItem()
        legend = self.legend()
        # About one marker per matrix row on screen: big markers merge into blobs on large matrices.
        width_px = max(self.getPlotItem().getViewBox().width(), 300.0)
        size = float(np.clip(width_px / max(data.n, 1), 1.0, 5.0))
        if data.labels is None:
            item.addItem(pg.ScatterPlotItem(x=data.cols, y=data.rows, size=size, symbol="s", pen=None,
                                            brush=pg.mkBrush(tokens.plot.series[0])))
            legend.scene().removeItem(legend)
            item.legend = None
            return
        row_part, col_part = data.labels[data.rows], data.labels[data.cols]
        cut = row_part != col_part
        parts = sorted(int(p) for p in np.unique(data.labels))
        colors = part_colors(parts)
        for part in parts:
            mask = (row_part == part) & ~cut
            item.addItem(pg.ScatterPlotItem(x=data.cols[mask], y=data.rows[mask], size=size, symbol="s", pen=None,
                                            brush=pg.mkBrush(colors[part])))
            if len(parts) <= 8:
                legend.addItem(self._key(colors[part]), f"Part {part + 1}")
        if cut.any():
            item.addItem(pg.ScatterPlotItem(x=data.cols[cut], y=data.rows[cut], size=size, symbol="s", pen=None,
                                            brush=pg.mkBrush(tokens.plot.ink)))
            legend.addItem(self._key(tokens.plot.ink), "Coupling between parts")

    def _draw_density(self, data: SparsityData) -> None:
        tokens = Theme.instance().tokens
        bins = min(DENSITY_BINS, data.n)
        counts, _, _ = np.histogram2d(data.rows, data.cols, bins=bins, range=[[0, data.n], [0, data.n]])
        alpha = np.clip(np.log1p(counts) / max(np.log1p(counts).max(), 1e-9), 0, 1)
        color = QColor(tokens.plot.series[0])
        rgba = np.zeros((bins, bins, 4), dtype=np.ubyte)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = color.red(), color.green(), color.blue()
        rgba[..., 3] = (alpha * 255).astype(np.ubyte)
        image = pg.ImageItem(np.transpose(rgba, (1, 0, 2)))
        image.setRect(0, 0, data.n, data.n)
        self.getPlotItem().addItem(image)
        if self.getPlotItem().legend is not None:
            self.getPlotItem().legend.scene().removeItem(self.getPlotItem().legend)
            self.getPlotItem().legend = None

    def fit(self) -> None:
        if self._data is not None:
            n = self._data.n
            self.getPlotItem().setRange(xRange=(-0.5, n - 0.5), yRange=(-0.5, n - 0.5), padding=0.02)


@dataclass
class CurveSeries:
    label: str
    values: np.ndarray
    color: str | None = None  # None = categorical slot by order
    reference: bool = False  # drawn in the de-emphasised grey


class CurveView(ThemedPlot):
    """Lines over a shared x axis, with a vertical read-out under the cursor."""

    def __init__(self, x_label: str, y_label: str, parent: QWidget | None = None, *, integer_x: bool = False, markers: bool = False) -> None:
        super().__init__(parent)
        self._markers = markers
        if integer_x:
            self.getPlotItem().getAxis("bottom").setTickSpacing(1, 1)
        self._x = np.zeros(0)
        self._series: list[CurveSeries] = []
        self._y_range: tuple[float, float] | None = None
        item = self.getPlotItem()
        item.setLabel("bottom", x_label)
        item.setLabel("left", y_label)
        item.setMouseEnabled(x=True, y=False)
        self._cursor = pg.InfiniteLine(angle=90, movable=False)
        self._readout = pg.TextItem(anchor=(0, 1))
        self._proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)
        self._references: list[tuple[str, float]] = []
        self.restyle()

    def set_reference_lines(self, limits: tuple[int | None, int | None]) -> None:
        """Horizontal lines marking a target range."""
        lower, upper = limits
        self._references = [(label, float(v)) for label, v in (("Lower limit", lower), ("Upper limit", upper)) if v is not None]
        self.redraw()

    def set_curves(self, x: np.ndarray, series: list[CurveSeries], y_range: tuple[float, float] | None = None) -> None:
        self._x, self._series, self._y_range = np.asarray(x, dtype=float), series, y_range
        self.redraw()

    def series(self) -> list[CurveSeries]:
        return list(self._series)

    def redraw(self) -> None:
        tokens = Theme.instance().tokens
        item = self.getPlotItem()
        item.clear()
        if not self._series:
            if item.legend is not None:
                item.legend.scene().removeItem(item.legend)
                item.legend = None
            return
        legend = self.legend()
        slot = 0
        for s in self._series:
            if s.reference:
                color = tokens.plot.reference
            elif s.color:
                color = s.color
            else:
                color = tokens.plot.series[slot]
                slot += 1
            if self._markers:
                line = item.plot(self._x, s.values, pen=pg.mkPen(color, width=2), symbol="o", symbolSize=8,
                                 symbolBrush=pg.mkBrush(color), symbolPen=pg.mkPen(tokens.plot.surface, width=2))
            else:
                line = item.plot(self._x, s.values, pen=pg.mkPen(color, width=2))
            legend.addItem(line, s.label)
        for label, value in self._references:
            line = pg.InfiniteLine(pos=value, angle=0, movable=False, pen=pg.mkPen(tokens.plot.reference, width=1, style=Qt.PenStyle.DashLine),
                                   label=f"{label} ({value:,.0f})", labelOpts={"position": 0.02, "color": tokens.plot.muted, "anchors": [(0, 1), (0, 1)]})
            item.addItem(line)
        self._cursor.setPen(pg.mkPen(tokens.plot.axis, width=1))
        self._cursor.setVisible(False)
        self._readout.setColor(tokens.plot.ink)
        self._readout.setFont(Theme.instance().ui_font(small=True))
        self._readout.setVisible(False)
        item.addItem(self._cursor, ignoreBounds=True)
        item.addItem(self._readout, ignoreBounds=True)
        self.fit()

    def fit(self) -> None:
        if self._x.size:
            if self._y_range:
                self.getPlotItem().setRange(xRange=(float(self._x[0]), float(self._x[-1])), yRange=self._y_range, padding=0.03)
            else:
                self.getPlotItem().autoRange()

    def readout_text(self, x: float) -> str:
        index = int(np.abs(self._x - x).argmin())
        lines = [f"x = {self._x[index]:.2f}"] + [f"{s.label}  {s.values[index]:.2f}" for s in self._series]
        return "\n".join(lines)

    def _on_mouse_moved(self, event) -> None:
        if not self._series:
            return
        view_box = self.getPlotItem().getViewBox()
        pos = event[0]
        inside = view_box.sceneBoundingRect().contains(pos)
        self._cursor.setVisible(inside)
        self._readout.setVisible(inside)
        if not inside:
            return
        x = float(np.clip(view_box.mapSceneToView(pos).x(), self._x[0], self._x[-1]))
        self._cursor.setPos(x)
        self._readout.setText(self.readout_text(x))
        (x_min, x_max), (y_min, y_max) = view_box.viewRange()
        right = x > (x_min + x_max) / 2
        self._readout.setAnchor((1, 1) if right else (0, 1))
        offset = (x_max - x_min) * 0.01
        self._readout.setPos(x - offset if right else x + offset, y_min + (y_max - y_min) * 0.04)
