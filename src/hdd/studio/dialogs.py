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
        self.clone.addItem("Defaults for the matrix", None)
        self.clone.setToolTip("Start from defaults adapted to the matrix, or copy another simulation's parameters")
        for sim in simulation_ids:
            self.clone.addItem(f"Copy from {sim}", sim)
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


SPACE_GROUP_FOR_STRATEGY = {"quantum_annealing": "qa.", "quantum_approximation_optimizer": "qaoa."}


class NewStudyDialog(QDialog):
    """Objectives, sampler, budget and search space of a new tuning study."""

    def __init__(self, meta: dict[str, Any], defaults: dict[str, Any], parent: QWidget | None = None) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QCheckBox, QHeaderView, QSpinBox, QTableWidget, QTableWidgetItem

        from .widgets import Section, segmented

        super().__init__(parent)
        self.setWindowTitle("New tuning study")
        self.resize(780, 780)
        self._meta, self._defaults = meta, defaults
        strategy = defaults["parameters"]["partitioning_parameters"]["partitioning_strategy"]
        prefix = SPACE_GROUP_FOR_STRATEGY.get(strategy)
        labels = {p["key"]: p["label"] for p in meta["parameters"]}
        from hdd.services.catalog import choice_label

        self.objectives: dict[str, QCheckBox] = {}
        objectives = Section("Objectives")
        for objective in meta["objectives"]:
            box = QCheckBox(objective["label"])
            box.setToolTip(objective["description"])
            box.setChecked(objective["key"] in ("edge_cut", "imbalance"))
            objectives.add(box)
            self.objectives[objective["key"]] = box
        aggregation, self._aggregation = segmented(["Pareto front", "Weighted sum"], 0)
        form = FormGrid()
        form.add_row("Combine objectives", aggregation, tooltip="Pareto keeps every non-dominated trade-off; a weighted sum ranks by one score.")
        objectives.add(form)

        search = Section("Search")
        self.sampler = QComboBox()
        for sampler in meta["samplers"]:
            self.sampler.addItem(sampler["label"], sampler["key"])
            self.sampler.setItemData(self.sampler.count() - 1, sampler["description"], Qt.ItemDataRole.ToolTipRole)
        self.trials = QSpinBox()
        self.trials.setRange(1, 10000)
        self.trials.setValue(30)
        self.repeats = QSpinBox()
        self.repeats.setRange(1, 20)
        self.repeats.setValue(1)
        self.start = QCheckBox("Start the study now")
        self.start.setChecked(True)
        grid = FormGrid()
        grid.add_row("Sampler", self.sampler)
        grid.add_row("Trials", self.trials)
        grid.add_row("Runs per trial", self.repeats, tooltip="Repeat each trial with different seeds and average the objectives.")
        search.add(grid)
        search.add(self.start)

        space = Section("Parameters to explore")
        self.space = {k: dict(v) for k, v in defaults["search_space"].items()
                      if "." not in k or (prefix is not None and k.startswith(prefix))}
        self.table = QTableWidget(len(self.space), 4)
        self.table.setHorizontalHeaderLabels(["Parameter", "Explore", "From", "To"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._keys = list(self.space)
        for row, key in enumerate(self._keys):
            entry = self.space[key]
            name = QTableWidgetItem(labels.get(key) or labels.get(key.split(".")[-1], key))
            name.setFlags(name.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name.setToolTip(key)
            self.table.setItem(row, 0, name)
            free = QTableWidgetItem()
            free.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            free.setCheckState(Qt.CheckState.Checked if entry.get("free") else Qt.CheckState.Unchecked)
            self.table.setItem(row, 1, free)
            if "choices" in entry:
                choices = QTableWidgetItem("; ".join(choice_label(c) for c in entry["choices"]))
                choices.setToolTip(choices.text())
                choices.setFlags(choices.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 2, choices)
                self.table.setSpan(row, 2, 1, 2)
            else:
                for column, bound in ((2, "low"), (3, "high")):
                    item = QTableWidgetItem(str(entry.get(bound)))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table.setItem(row, column, item)
        self.table.setMinimumHeight(min(len(self._keys), 12) * 24 + 30)
        space.add(self.table)
        self.error = QLabel()
        self.error.setProperty("role", "error")
        self.error.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create study")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty("role", "primary")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(6)
        for widget in (objectives, search, space, self.error):
            layout.addWidget(widget)
        layout.addStretch(1)
        layout.addWidget(buttons)

    def request(self) -> dict[str, Any]:
        """The study request for ``hdd.services.tuning.create_study``. Raises ValueError on bad bounds."""
        from PySide6.QtCore import Qt

        objectives = [k for k, box in self.objectives.items() if box.isChecked()]
        if not objectives:
            raise ValueError("Choose at least one objective.")
        space = {}
        for row, key in enumerate(self._keys):
            entry = dict(self.space[key])
            entry["free"] = self.table.item(row, 1).checkState() == Qt.CheckState.Checked
            if "choices" not in entry:
                kind = int if isinstance(entry.get("low"), int) and isinstance(entry.get("high"), int) else float
                try:
                    low, high = kind(self.table.item(row, 2).text()), kind(self.table.item(row, 3).text())
                except ValueError as exc:
                    raise ValueError(f"{self.table.item(row, 0).text()}: the range must be numbers.") from exc
                if low > high:
                    raise ValueError(f"{self.table.item(row, 0).text()}: 'From' must not exceed 'To'.")
                entry.update(low=low, high=high)
            space[key] = entry
        if not any(v["free"] for v in space.values()):
            raise ValueError("Tick at least one parameter to explore.")
        return {
            "objectives": objectives,
            "aggregation": "pareto" if self._aggregation.checkedId() == 0 else "weighted",
            "sampler": self.sampler.currentData(),
            "n_trials": self.trials.value(),
            "repeats": self.repeats.value(),
            "search_space": space,
            "parameters": self._defaults["parameters"],
        }

    def _accept(self) -> None:
        try:
            self.request()
        except ValueError as exc:
            self.error.setText(str(exc))
            return
        self.accept()
