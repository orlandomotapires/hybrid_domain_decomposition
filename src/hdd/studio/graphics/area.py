"""The central graphics area: plots of whatever is selected in the project tree."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QFileDialog, QHBoxLayout, QLabel, QMenu, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget

from hdd.services import catalog, results
from libs.runtime.matrix_library import resolve_matrix
from libs.runtime.utils import load_mtx

from ..tasks import TaskRunner
from ..theme import Theme
from .views import CurveSeries, CurveView, ScatterView, SparsityData, SparsityView

PLOT_LABELS = {
    "original_matrix_partitioned": "Original matrix",
    "permuted_matrix_partitioned": "Permuted matrix",
    "original_graph_partitioned": "Original graph",
    "coarsened_graph_partitioned": "Coarsened graph",
    "uncoarsened_graph_partitioned": "Uncoarsened graph",
}


def load_matrix_pattern(matrix_id: str) -> SparsityData:
    coo = load_mtx(resolve_matrix(matrix_id), label=matrix_id).tocoo()
    return SparsityData(int(coo.shape[0]), coo.row.astype(np.int64), coo.col.astype(np.int64), None, matrix_id)


def load_run_plot(result_dir: str, plot_name: str) -> SparsityData:
    data = results.plot_data(result_dir, plot_name)
    return SparsityData(data.n, data.rows, data.cols, data.labels, PLOT_LABELS[plot_name])


class GraphicsArea(QWidget):
    def __init__(self, tasks: TaskRunner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tasks = tasks
        self._result_dir: str | None = None
        self._limits: tuple[int | None, int | None] = (None, None)
        self._matrix_shown: str | None = None

        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.sparsity = SparsityView()
        self.curves = CurveView("Half-bandwidth (% of n)", "Nonzeros inside the band (%)")
        self.trajectory = CurveView("Level", "Nodes", integer_x=True, markers=True)
        self.bands = CurveView("Half-bandwidth (% of n)", "Nonzeros inside the band (%)", markers=True)
        self.convergence = CurveView("Trial", "Best score so far", integer_x=True, markers=True)
        self.pareto = ScatterView()
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setProperty("role", "muted")
        self.message.setWordWrap(True)
        self.stack = QStackedWidget()
        for widget in (self.sparsity, self.curves, self.trajectory, self.bands, self.convergence, self.pareto, self.message):
            self.stack.addWidget(widget)

        self.plot_choice = QComboBox()
        for key, label in PLOT_LABELS.items():
            self.plot_choice.addItem(label, key)
        self.plot_choice.setCurrentIndex(1)
        self.plot_choice.setFixedWidth(180)
        self.plot_choice.currentIndexChanged.connect(lambda _i: self._load_run_plot())
        self.fit_button = QToolButton()
        self.fit_button.setToolTip("Fit to window")
        self.fit_button.setIconSize(QSize(16, 16))
        Theme.instance().bind_icon(self.fit_button, "fit")
        self.fit_button.clicked.connect(lambda: self.stack.currentWidget().fit() if hasattr(self.stack.currentWidget(), "fit") else None)
        self.export_button = QToolButton()
        self.export_button.setToolTip("Export the plot")
        self.export_button.setIconSize(QSize(16, 16))
        self.export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        Theme.instance().bind_icon(self.export_button, "image")
        self.export_menu = QMenu(self)
        self.export_menu.aboutToShow.connect(self._fill_export_menu)
        self.export_button.setMenu(self.export_menu)

        strip = QWidget()
        strip.setObjectName("TabStrip")
        strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(strip)
        row.setContentsMargins(4, 0, 6, 0)
        row.setSpacing(6)
        row.addWidget(self.tabs)
        row.addStretch(1)
        row.addWidget(self.plot_choice)
        row.addWidget(self.fit_button)
        row.addWidget(self.export_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(strip)
        layout.addWidget(self.stack, 1)
        self.tabs.currentChanged.connect(self._on_tab)
        self.clear()

    def set_tasks(self, tasks: TaskRunner) -> None:
        self._tasks = tasks
        self.clear()

    # ------------------------------------------------------------------ tabs
    def _set_tabs(self, names: list[str]) -> None:
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for name in names:
            self.tabs.addTab(name)
        self.tabs.blockSignals(False)

    def _on_tab(self, index: int) -> None:
        name = self.tabs.tabText(index)
        self.stack.setCurrentWidget(
            {"Locality curve": self.curves, "Comparison": self.curves, "Coarsening": self.trajectory, "Band concentration": self.bands,
             "Convergence": self.convergence, "Pareto front": self.pareto}.get(name, self.sparsity)
        )
        self.plot_choice.setVisible(name == "Sparsity" and self._result_dir is not None)

    def current_view(self) -> str:
        widget = self.stack.currentWidget()
        return {id(self.message): "message", id(self.curves): "curves", id(self.trajectory): "trajectory", id(self.bands): "bands",
                id(self.convergence): "convergence", id(self.pareto): "pareto"}.get(
            id(widget), "sparsity"
        )

    # ----------------------------------------------------------------- show
    def clear(self, text: str = "Select a matrix or a run to see its plots.") -> None:
        self._result_dir = None
        self._matrix_shown = None
        self._set_tabs([])
        self.plot_choice.setVisible(False)
        self.fit_button.setVisible(False)
        self.export_button.setVisible(False)
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)

    def _busy(self, text: str) -> None:
        self.message.setText(text)
        self.stack.setCurrentWidget(self.message)

    def show_coarsening(self, preview: dict | None) -> None:
        """Nodes per level of a coarsening preview, with the target range as reference lines."""
        if preview is None:
            self.clear("Fix the parameter errors to preview the coarsening.")
            return
        levels = [lv for lv in preview["levels"] if lv["accepted"]]
        x = np.array([lv["level"] for lv in levels], dtype=float)
        series = [CurveSeries("Nodes", np.array([lv["nodes"] for lv in levels], dtype=float))]
        self._result_dir = None
        self._set_tabs(["Coarsening"])
        self.plot_choice.setVisible(False)
        self.fit_button.setVisible(True)
        self.export_button.setVisible(True)
        self.trajectory.set_curves(x, series)
        self.trajectory.set_reference_lines(self._limits)
        self.stack.setCurrentWidget(self.trajectory)

    def set_coarsening_limits(self, lower: int | None, upper: int | None) -> None:
        self._limits = (lower, upper)

    def show_matrix(self, matrix_id: str) -> None:
        if self._matrix_shown == matrix_id and self.stack.currentWidget() is self.sparsity:
            return
        self._matrix_shown = matrix_id
        self._result_dir = None
        self._set_tabs(["Sparsity"])
        self.plot_choice.setVisible(False)
        self.fit_button.setVisible(True)
        self.export_button.setVisible(True)
        self._busy("Loading matrix…")
        self._tasks.run(
            lambda: load_matrix_pattern(matrix_id),
            self._show_sparsity,
            lambda exc: self.clear(f"Could not read matrix {matrix_id}: {exc}"),
            key="graphics",
        )

    def show_run(self, result_dir: str, detail: dict[str, Any]) -> None:
        self._matrix_shown = None
        self._result_dir = result_dir
        tabs = []
        if detail.get("can_render_plots"):
            tabs.append("Sparsity")
        if detail.get("curves"):
            tabs.append("Locality curve")
        if not tabs:
            self.clear("This run saved no plottable outputs. Enable the matrix, permutation and graph outputs to see plots.")
            return
        self._set_tabs(tabs)
        self.fit_button.setVisible(True)
        self.export_button.setVisible(True)
        curves = detail.get("curves") or []
        if curves:
            x = np.array([p["percent"] for p in curves])
            permuted = np.array([100 * p["permuted"] for p in curves])
            original = np.array([100 * p["original"] for p in curves])
            top = float(max(permuted.max(), original.max(), 1.0))
            self.curves.set_curves(
                x,
                [CurveSeries("Permuted", permuted), CurveSeries("Original", original, reference=True)],
                y_range=(0, top * 1.05),
            )
        if "Sparsity" in tabs:
            self._load_run_plot()
        self.tabs.setCurrentIndex(0)
        self._on_tab(0)

    def _load_run_plot(self) -> None:
        if not self._result_dir:
            return
        result_dir, plot = self._result_dir, self.plot_choice.currentData()
        self._busy("Loading plot…")
        self._tasks.run(
            lambda: load_run_plot(result_dir, plot),
            self._show_sparsity,
            lambda exc: self._busy(f"Could not draw this plot: {exc}"),
            key="graphics",
        )

    def _show_sparsity(self, data: SparsityData) -> None:
        self.sparsity.set_data(data)
        if self.tabs.count() and self.tabs.tabText(self.tabs.currentIndex()) == "Sparsity":
            self.stack.setCurrentWidget(self.sparsity)

    # ------------------------------------------------------------- comparison
    def show_comparison(self, runs: list[dict[str, Any]]) -> None:
        """Locality curves of several runs: each run in its own colour, the original ordering in grey."""
        runs = [r for r in runs if r.get("curves")]
        if not runs:
            self.clear("The selected runs have no metrics to compare.")
            return
        x = np.array([p["percent"] for p in runs[0]["curves"]])
        series = [CurveSeries(r["label"], np.array([100 * p["permuted"] for p in r["curves"]][: len(x)])) for r in runs]
        series.append(CurveSeries("Original", np.array([100 * p["original"] for p in runs[0]["curves"]][: len(x)]), reference=True))
        top = max(float(s.values.max()) for s in series)
        self._result_dir = None
        self._matrix_shown = None
        self._set_tabs(["Comparison"])
        self.plot_choice.setVisible(False)
        self.fit_button.setVisible(True)
        self.export_button.setVisible(True)
        self.curves.set_curves(x, series, y_range=(0, max(top, 1.0) * 1.05))
        self.stack.setCurrentWidget(self.curves)

    def show_band_concentration(self, curve: dict[str, Any] | None, title: str = "") -> None:
        """One coarsening scale of a batch: share of nonzeros near the diagonal for each method."""
        if not curve or not curve.get("points"):
            self.clear("No completed cases for this matrix and scale.")
            return
        points = curve["points"]
        x = np.array([p["percent"] for p in points], dtype=float)
        tokens = Theme.instance().tokens
        series = []
        for method in curve["methods"]:
            key = catalog.method_key(method)
            color = tokens.plot.series[catalog.METHOD_SLOT[key]] if key in catalog.METHOD_SLOT else None
            series.append(CurveSeries(catalog.method_label(method, short=True), np.array([100 * p.get(method, np.nan) for p in points]), color))
        series.append(CurveSeries("Original", np.array([100 * p.get("Original", np.nan) for p in points]), reference=True))
        top = np.nanmax([np.nanmax(s.values) for s in series])
        self._result_dir = None
        self._matrix_shown = None
        self._set_tabs(["Band concentration"])
        self.plot_choice.setVisible(False)
        self.fit_button.setVisible(True)
        self.export_button.setVisible(True)
        self.bands.set_curves(x, series, y_range=(0, float(max(top, 1.0)) * 1.05))
        self.bands.getPlotItem().setTitle(title, color=tokens.plot.ink, size=f"{tokens.type.base_pt:g}pt")
        self.stack.setCurrentWidget(self.bands)

    # ----------------------------------------------------------------- export
    def _fill_export_menu(self) -> None:
        self.export_menu.clear()
        view = self.stack.currentWidget()
        if view is self.message:
            return
        for text, suffix in (("Image (PNG)…", "png"), ("Image (SVG)…", "svg")):
            action = QAction(text, self.export_menu)
            action.triggered.connect(lambda _c=False, s=suffix: self._ask_and_export(s))
            self.export_menu.addAction(action)
        if view is not self.sparsity:
            action = QAction("Data (CSV)…", self.export_menu)
            action.triggered.connect(lambda: self._ask_and_export("csv"))
            self.export_menu.addAction(action)
        if view is self.sparsity and self._result_dir:
            self.export_menu.addSeparator()
            action = QAction("Publication figure (PNG, 160 dpi)…", self.export_menu)
            action.triggered.connect(lambda: self._ask_and_export("figure"))
            self.export_menu.addAction(action)

    def _ask_and_export(self, kind: str) -> None:
        suffix = "png" if kind == "figure" else kind
        name = self.tabs.tabText(self.tabs.currentIndex()).lower().replace(" ", "_") or "plot"
        path, _ = QFileDialog.getSaveFileName(self, "Export", str(Path.home() / f"{name}.{suffix}"), f"{suffix.upper()} (*.{suffix})")
        if path:
            self.export(kind, path)

    def export(self, kind: str, path: str) -> Path:
        """Write the current view: ``png``/``svg`` as shown, ``csv`` data of a curve view, ``figure`` the matplotlib rendering."""
        import pyqtgraph.exporters as exporters

        view = self.stack.currentWidget()
        target = Path(path)
        if kind == "figure":
            source = results.render_plot_png(self._result_dir, self.plot_choice.currentData())
            shutil.copyfile(source, target)
        elif kind == "csv":
            if not isinstance(view, CurveView):
                raise ValueError("Only curves can be exported as CSV")
            series = view.series()
            with target.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([view.getPlotItem().getAxis("bottom").labelText] + [s.label for s in series])
                for i, x in enumerate(view.x_values()):
                    writer.writerow([x] + [s.values[i] for s in series])
        elif kind == "svg":
            # pyqtgraph's SVG exporter fails on scatter plots; Qt's SVG painter keeps the vectors.
            from PySide6.QtCore import QRect, QSize
            from PySide6.QtGui import QPainter
            from PySide6.QtSvg import QSvgGenerator

            generator = QSvgGenerator()
            generator.setFileName(str(target))
            generator.setSize(QSize(view.width(), view.height()))
            generator.setViewBox(QRect(0, 0, view.width(), view.height()))
            generator.setTitle(self.tabs.tabText(self.tabs.currentIndex()))
            painter = QPainter(generator)
            view.render(painter)
            painter.end()
        else:
            exporter = exporters.ImageExporter(view.getPlotItem())
            exporter.parameters()["width"] = max(1600, int(view.width() * 2))
            exporter.export(str(target))
        return target

    # ----------------------------------------------------------------- tuning
    def show_study(self, study: dict[str, Any], objective_labels: dict[str, str]) -> None:
        """Pareto front of a two-objective study, else the best score per trial."""
        config, summary, trials = study.get("config") or {}, study.get("summary") or {}, study.get("trials") or []
        objectives = config.get("objectives") or []
        ok = [t for t in trials if t.get("status") == "ok" and t.get("values")]
        self._result_dir = None
        self._matrix_shown = None
        self.plot_choice.setVisible(False)
        self.fit_button.setVisible(True)
        self.export_button.setVisible(True)
        if config.get("aggregation") == "pareto" and len(objectives) >= 2 and ok:
            x_key, y_key = objectives[0], objectives[1]
            self.pareto.set_labels(objective_labels.get(x_key, x_key), objective_labels.get(y_key, y_key))
            self.pareto.set_points([(t["values"][x_key], t["values"][y_key], t["number"]) for t in ok], set(summary.get("pareto_front") or []))
            self._set_tabs(["Pareto front"])
            self.stack.setCurrentWidget(self.pareto)
            return
        curve = [v for v in (summary.get("best_curve") or [])]
        points = [(i, v) for i, v in enumerate(curve) if v is not None]
        if not points:
            self.clear("No successful trials yet.")
            return
        self.convergence.set_curves(np.array([p[0] for p in points], dtype=float), [CurveSeries("Best score", np.array([p[1] for p in points]))])
        self._set_tabs(["Convergence"])
        self.stack.setCurrentWidget(self.convergence)
