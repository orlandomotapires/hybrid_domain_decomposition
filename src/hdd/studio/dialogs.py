"""Dialogs: new simulation and parameter comparison."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from hdd.services import catalog

from .widgets import FormGrid
from .widgets.tables import DataTable, fmt


class NewSimulationDialog(QDialog):
    def __init__(self, matrix_ids: list[str], simulation_ids: list[str], suggested_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New simulation")
        self.name = QLineEdit(suggested_name)
        self.matrix = QComboBox()
        for matrix_id in matrix_ids:
            self.matrix.addItem(matrix_id, matrix_id)
        self.clone = QComboBox()
        self.clone.addItem("Start from defaults adapted to the matrix", None)
        for sim in simulation_ids:
            self.clone.addItem(f"Copy the parameters of {sim}", sim)
        form = FormGrid()
        form.add_row("Name", self.name)
        form.add_row("Input matrix", self.matrix)
        form.add_row("Parameters", self.clone)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("role", "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(form)
        if not matrix_ids:
            note = QLabel("The matrix library is empty. Import a matrix first.")
            note.setProperty("role", "error")
            layout.addWidget(note)
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        return {"name": self.name.text().strip() or None, "matrix": self.matrix.currentData(), "clone_from": self.clone.currentData()}


class CompareDialog(QDialog):
    """Differences between two parameter sets chosen from ``sources`` (label -> loader)."""

    def __init__(self, sources: dict[str, Callable[[], dict[str, Any]]], left: str, right: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare parameters")
        self.resize(760, 520)
        self._sources = sources
        self.left = QComboBox()
        self.right = QComboBox()
        for box, chosen in ((self.left, left), (self.right, right)):
            box.addItems(list(sources))
            box.setCurrentText(chosen)
            box.currentIndexChanged.connect(self.refresh)
        form = FormGrid()
        form.add_row("Compare", self.left)
        form.add_row("With", self.right)
        self.summary = QLabel()
        self.summary.setProperty("role", "muted")
        self.table = DataTable(["Parameter", "Left", "Right"], max_visible_rows=14, stretch=0)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(form)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons)
        self.refresh()

    def differences(self) -> list[tuple[str, Any, Any]]:
        left = self._sources[self.left.currentText()]()
        right = self._sources[self.right.currentText()]()
        return catalog.diff(left, right)

    def refresh(self) -> None:
        try:
            rows = self.differences()
        except Exception as exc:  # a preset file may be unreadable
            self.summary.setText(f"Could not compare: {exc}")
            self.table.set_rows([])
            return
        self.summary.setText("The two parameter sets are identical." if not rows else f"{len(rows)} parameters differ.")
        self.table.set_rows([[catalog.label_for_key(key), fmt(a, 4) if isinstance(a, float) else fmt(a), fmt(b, 4) if isinstance(b, float) else fmt(b)] for key, a, b in rows])
