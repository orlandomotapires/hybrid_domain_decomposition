"""Hand-built settings pages for the visual prototype, one per project-tree node kind."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..theme import Theme
from ..widgets import FormGrid, InlineMessage, PropertyTable, Section, segmented
from . import sample_data


def _number(value: float, decimals: int = 0) -> str:
    """Format with a thousands separator, matching the numeric fields."""
    return f"{value:,.{decimals}f}"


class Page(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(14, 12, 14, 14)
        self.box.setSpacing(6)

    def add(self, widget: QWidget) -> QWidget:
        self.box.addWidget(widget)
        return widget

    def finish(self) -> "Page":
        self.box.addStretch(1)
        return self


def _spin(value: int, minimum: int = 0, maximum: int = 1_000_000) -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    box.setGroupSeparatorShown(True)
    return box


def _double(value: float, decimals: int = 2, minimum: float = 0.0, maximum: float = 1e6, step: float = 0.01) -> QDoubleSpinBox:
    box = QDoubleSpinBox()
    box.setDecimals(decimals)
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setValue(value)
    return box


def _combo(options: list[str], current: int = 0) -> QComboBox:
    box = QComboBox()
    box.addItems(options)
    box.setCurrentIndex(current)
    return box


def _buttons(*buttons: QPushButton) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(8)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return row


def _button(text: str, *, primary: bool = False, icon: str | None = None) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setProperty("role", "primary")
    if icon:
        Theme.instance().bind_icon(button, icon, "on_accent" if primary else "default")
    return button


def _table(headers: tuple[str, ...], rows: list[tuple], numeric_from: int = 0) -> QTableWidget:
    """Compact read-only table sized to its content; columns from ``numeric_from`` are right-aligned."""
    theme = Theme.instance()
    table = QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    row_height = theme.tokens.metrics.row_height
    table.verticalHeader().setDefaultSectionSize(row_height)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(_number(value) if isinstance(value, int) else str(value))
            if c >= numeric_from:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setFont(theme.numeric_font())
            table.setItem(r, c, item)
    for c in range(numeric_from, len(headers)):
        table.horizontalHeaderItem(c).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    table.setFixedHeight(header.sizeHint().height() + len(rows) * row_height + 2)
    return table


# ---------------------------------------------------------------------- pages
def coarsening_page() -> Page:
    page = Page()
    page.add(InlineMessage("ok", "Parameters are valid. The coarsest graph will have 48 nodes (target range: 32 to 64)."))

    strategy = Section("Strategy")
    form = FormGrid()
    form.add_row(
        "Matching strategy",
        _combo(["Heavy-edge, sorted", "Heavy-edge, random", "Modified", "Light"]),
        tooltip="How node pairs are chosen for contraction at each level.",
    )
    form.add_row("Reduction ratio", _double(0.50, 2, 0.05, 0.95, 0.05), tooltip="Minimum node reduction per level.")
    strategy.add(form)
    page.add(strategy)

    limits = Section("Limits")
    form = FormGrid()
    form.add_row("Lower limit", _spin(32, 2), "nodes")
    form.add_row("Upper limit", _spin(64, 2), "nodes")
    form.add_row("Maximum levels", _spin(10, 1, 64))
    form.add_row("Maximum node weight", _double(0.0, 2, 0.0, 1e9, 1.0), tooltip="0 = derived automatically from the graph.")
    limits.add(form)
    page.add(limits)

    preview = Section("Preview per level")
    preview.add(_table(sample_data.COARSENING_HEADERS, sample_data.coarsening_levels()))
    preview.add(_buttons(_button("Refresh preview", icon="refresh")))
    page.add(preview)
    return page.finish()


def partitioning_page() -> Page:
    page = Page()
    method = Section("Method")
    form = FormGrid()
    form.add_row("Method", _combo(["METIS", "Quantum annealing", "QAOA"], 1))
    form.add_row("Number of parts (k)", _spin(4, 2, 1024))
    form.add_row("Balance tolerance", _double(0.02, 3, 0.0, 1.0, 0.005))
    method.add(form)
    method.add(
        InlineMessage(
            "warning",
            "With 48 nodes in the coarsest graph, a tolerance of 0.02 allows at most 12 nodes per part. "
            "If no balanced solution is found, the tolerance is relaxed by 1 node.",
        )
    )
    page.add(method)

    annealing = Section("Quantum annealing")
    form = FormGrid()
    form.add_row("Reads per bisection", _spin(1000, 1), tooltip="num_reads")
    form.add_row("Restarts", _spin(4, 1), tooltip="num_starts")
    backend, _group = segmented(["Emulated", "D-Wave hardware"], 0)
    form.add_row("Backend", backend)
    solver = QLineEdit()
    solver.setPlaceholderText("Set when hardware is selected")
    solver.setEnabled(False)
    form.add_row("QPU solver", solver)
    annealing.add(form)
    annealing.add(InlineMessage("info", "Estimate: 3 bisections and 3,000 reads on the emulator. No QPU submissions."))
    page.add(annealing)
    return page.finish()


def refinement_page() -> Page:
    page = Page()
    section = Section("Refinement per level")
    form = FormGrid()
    form.add_row("Objective", _combo(["Edge cut"]))
    form.add_row("Balance weight (λ)", _double(1.0, 2, 0.0, 100.0, 0.1))
    form.add_row("Passes per level", _spin(4, 0, 100))
    form.add_row("Moves per pass", _spin(200, 1))
    check = QCheckBox("Validate node weights after projecting each level")
    check.setChecked(True)
    section.add(form)
    section.add(check)
    page.add(section)
    return page.finish()


def run_page() -> Page:
    data = sample_data.decomposition()
    widths = np.array([1.0])
    within_original = float(data.locality_curve("original", widths)[0])
    within_permuted = float(data.locality_curve("permuted", widths)[0])

    page = Page()
    page.add(InlineMessage("ok", "Run completed in 1.2 s. Permutation verified (P A Pᵀ preserves the nonzeros)."))

    quality = Section("Partition quality")
    quality.add(
        PropertyTable(
            [
                ("Parts (k)", _number(data.k), ""),
                ("Edge cut", _number(data.edge_cut), "edges"),
                ("Imbalance", _number(0.0, 2), "%"),
                ("Interface nodes", _number(data.interface_nodes), "nodes"),
            ]
        )
    )
    page.add(quality)

    structure = Section("Matrix structure")
    structure.add(
        PropertyTable(
            [
                ("Dimension (n)", _number(data.n), ""),
                ("Nonzeros", _number(data.nnz), ""),
                ("Bandwidth, original", _number(data.bandwidth_original), ""),
                ("Bandwidth, permuted", _number(data.bandwidth_permuted), ""),
                ("Nonzeros within 1 % of the diagonal, original", _number(within_original, 1), "%"),
                ("Nonzeros within 1 % of the diagonal, permuted", _number(within_permuted, 1), "%"),
            ]
        )
    )
    page.add(structure)

    timing = Section("Time per stage", expanded=False)
    timing.add(
        PropertyTable(
            [
                ("Graph build", _number(0.02, 2), "s"),
                ("Coarsening", _number(0.04, 2), "s"),
                ("Partitioning", _number(1.05, 2), "s"),
                ("Refinement", _number(0.07, 2), "s"),
                ("Permutation", _number(0.01, 2), "s"),
            ]
        )
    )
    page.add(timing)
    page.add(_buttons(_button("Open folder", icon="folder"), _button("Export…", icon="export"), _button("Compare…", icon="compare")))
    return page.finish()


def matrix_page() -> Page:
    data = sample_data.decomposition()
    page = Page()
    section = Section("Matrix")
    section.add(
        PropertyTable(
            [
                ("Format", "Matrix Market, coordinate", ""),
                ("Dimension (n)", _number(data.n), ""),
                ("Nonzeros", _number(data.nnz), ""),
                ("Density", _number(data.nnz / data.n**2 * 100, 2), "%"),
                ("Symmetry", "Symmetric", ""),
                ("Bandwidth", _number(data.bandwidth_original), ""),
            ]
        )
    )
    page.add(section)
    used = Section("Used by")
    used.add(QLabel("simulation_01, simulation_03"))
    page.add(used)
    page.add(_buttons(_button("Import matrix…", icon="import"), _button("Delete", icon="delete")))
    return page.finish()


def simulation_page() -> Page:
    page = Page()
    page.add(InlineMessage("ok", "Parameters are valid."))
    section = Section("Summary")
    section.add(
        PropertyTable(
            [
                ("Input matrix", "demo_fem_600", ""),
                ("Active preset", "simulation_parameters.json", ""),
                ("Method", "Quantum annealing (emulated)", ""),
                ("Parts (k)", "4", ""),
                ("Runs", "3", ""),
            ]
        )
    )
    page.add(section)
    page.add(_buttons(_button("Run", primary=True, icon="run"), _button("Validate", icon="validate")))
    return page.finish()


def placeholder_page(label: str) -> Page:
    page = Page()
    note = QLabel(f"The “{label}” page is built in the next phases. This version only shows the visual identity.")
    note.setProperty("role", "muted")
    note.setWordWrap(True)
    page.add(note)
    return page.finish()


BUILDERS = {
    "coarsening": coarsening_page,
    "partitioning": partitioning_page,
    "refinement": refinement_page,
    "run": run_page,
    "matrix": matrix_page,
    "input": matrix_page,
    "simulation": simulation_page,
}


def build_page(kind: str, label: str) -> Page:
    builder = BUILDERS.get(kind)
    return builder() if builder else placeholder_page(label)
