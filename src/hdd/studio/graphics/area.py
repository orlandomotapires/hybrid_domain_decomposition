"""The central graphics area: plots of whatever is selected in the project tree."""

from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget

from hdd.services import results
from libs.runtime.matrix_library import resolve_matrix
from libs.runtime.utils import load_mtx

from ..tasks import TaskRunner
from ..theme import Theme
from .views import CurveSeries, CurveView, SparsityData, SparsityView

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
        self.message = QLabel()
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setProperty("role", "muted")
        self.message.setWordWrap(True)
        self.stack = QStackedWidget()
        for widget in (self.sparsity, self.curves, self.trajectory, self.message):
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
        self.stack.setCurrentWidget({"Locality curve": self.curves, "Coarsening": self.trajectory}.get(name, self.sparsity))
        self.plot_choice.setVisible(name == "Sparsity" and self._result_dir is not None)

    def current_view(self) -> str:
        widget = self.stack.currentWidget()
        return {id(self.message): "message", id(self.curves): "curves", id(self.trajectory): "trajectory"}.get(id(widget), "sparsity")

    # ----------------------------------------------------------------- show
    def clear(self, text: str = "Select a matrix or a run to see its plots.") -> None:
        self._result_dir = None
        self._matrix_shown = None
        self._set_tabs([])
        self.plot_choice.setVisible(False)
        self.fit_button.setVisible(False)
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
