"""Parameter editors bound to a :class:`SimulationDocument`, generated from the catalog."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hdd.services import catalog, simulations
from hdd.services.catalog import ParamSpec

from .documents import SimulationDocument, bind
from .widgets import FormGrid, InlineMessage, segmented
from .widgets.tables import DataTable, fmt


class _NoWheel:
    """Spin boxes and combos ignore the mouse wheel unless focused, so scrolling a page never edits it."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SpinBox(_NoWheel, QSpinBox):
    pass


class DoubleSpinBox(_NoWheel, QDoubleSpinBox):
    pass


class ComboBox(_NoWheel, QComboBox):
    pass


class FieldEditor(QWidget):
    """One parameter: the input widget plus, for optional parameters, the "no value" check box."""

    def __init__(self, spec: ParamSpec, commit: Callable[[Any], None]) -> None:
        super().__init__()
        self.spec = spec
        self._commit = commit
        self._updating = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.input = self._make_input()
        layout.addWidget(self.input)
        if spec.unit:
            unit = QLabel(spec.unit)
            unit.setProperty("role", "unit")
            layout.addWidget(unit)
        self.none_box: QCheckBox | None = None
        if spec.optional:
            self.none_box = QCheckBox(spec.optional)
            self.none_box.toggled.connect(self._on_none_toggled)
            layout.addWidget(self.none_box)
        layout.addStretch(1)

    def _make_input(self) -> QWidget:
        spec = self.spec
        if spec.kind == "int":
            box = SpinBox()
            box.setRange(int(spec.minimum if spec.minimum is not None else -(2**31)), int(min(spec.maximum or 2**31 - 1, 2**31 - 1)))
            box.setGroupSeparatorShown(True)
            box.setAlignment(Qt.AlignmentFlag.AlignRight)
            box.setFixedWidth(120)
            box.setKeyboardTracking(False)
            box.valueChanged.connect(lambda v: self._emit(int(v)))
            return box
        if spec.kind == "float":
            box = DoubleSpinBox()
            box.setDecimals(spec.decimals)
            box.setRange(spec.minimum if spec.minimum is not None else -1e18, spec.maximum if spec.maximum is not None else 1e18)
            box.setSingleStep(spec.step)
            box.setAlignment(Qt.AlignmentFlag.AlignRight)
            box.setFixedWidth(120)
            box.setKeyboardTracking(False)
            box.valueChanged.connect(lambda v: self._emit(float(v)))
            return box
        if spec.kind == "choice":
            box = ComboBox()
            for value, label in spec.choices:
                box.addItem(label, value)
            box.setFixedWidth(232)
            box.currentIndexChanged.connect(lambda i: self._emit(box.itemData(i)))
            return box
        if spec.kind == "toggle":
            widget, group = segmented([label for _v, label in spec.choices])
            self._group = group
            group.idClicked.connect(lambda i: self._emit(spec.choices[i][0]))
            return widget
        if spec.kind == "bool":
            box = QCheckBox()
            box.toggled.connect(lambda v: self._emit(bool(v)))
            return box
        box = QLineEdit()
        box.setFixedWidth(232)
        box.editingFinished.connect(lambda: self._emit(box.text().strip() or None))
        return box

    def _emit(self, value: Any) -> None:
        if not self._updating:
            self._commit(value)

    def _on_none_toggled(self, is_none: bool) -> None:
        self.input.setEnabled(not is_none)
        if self._updating:
            return
        if is_none:
            self._commit(None)
        else:
            self._commit(self.spec.default)

    def _current_input_value(self) -> Any:
        if isinstance(self.input, QSpinBox):
            return int(self.input.value())
        if isinstance(self.input, QDoubleSpinBox):
            return float(self.input.value())
        if isinstance(self.input, QLineEdit):
            return self.input.text().strip() or None
        return None

    def set_value(self, value: Any) -> None:
        self._updating = True
        try:
            if self.none_box is not None:
                self.none_box.setChecked(value is None)
                self.input.setEnabled(value is not None)
                if isinstance(self.input, (QSpinBox, QDoubleSpinBox)):
                    # An unset value shows a dash, not a number that is not in effect.
                    self.input.setSpecialValueText("—" if value is None else "")
                    if value is None:
                        self.input.setValue(self.input.minimum())
                        return
                if value is None:
                    value = self.spec.default
            if isinstance(self.input, QSpinBox):
                self.input.setValue(int(value or 0))
            elif isinstance(self.input, QDoubleSpinBox):
                self.input.setValue(float(value or 0.0))
            elif isinstance(self.input, QComboBox):
                index = self.input.findData(value)
                self.input.setCurrentIndex(max(index, 0))
            elif isinstance(self.input, QCheckBox):
                self.input.setChecked(bool(value))
            elif isinstance(self.input, QLineEdit):
                self.input.setText("" if value is None else str(value))
            elif self.spec.kind == "toggle":
                index = next((i for i, (v, _l) in enumerate(self.spec.choices) if v == value), 0)
                self._group.button(index).setChecked(True)
        finally:
            self._updating = False

    def focus(self) -> None:
        target = self.input if not isinstance(self.input, QWidget) or self.input.isEnabled() else self.none_box
        if target is not None:
            target.setFocus(Qt.FocusReason.OtherFocusReason)
            if isinstance(target, QAbstractSpinBox):
                target.selectAll()


class ParameterForm(QWidget):
    """A form for a list of specs, kept in sync with the document both ways."""

    def __init__(self, doc: SimulationDocument, specs: tuple[ParamSpec, ...]) -> None:
        super().__init__()
        self.doc = doc
        self.specs = specs
        self.grid = FormGrid()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.grid)
        self.editors: dict[str, FieldEditor] = {}
        self._rows: dict[str, int] = {}
        for spec in specs:
            editor = FieldEditor(spec, lambda value, s=spec: self.doc.set_value(s, value))
            self._rows[spec.key] = self.grid.add_row(spec.label, editor, "", spec.help)
            self.editors[spec.key] = editor
        bind(self, doc.changed, self._on_changed)
        bind(self, doc.validated, self._show_issues)
        self.refresh()
        self._show_issues()

    def refresh(self) -> None:
        for spec in self.specs:
            self.editors[spec.key].set_value(self.doc.value(spec))
            visible = spec.visible(self.doc.params) if spec.visible else True
            self.grid.set_row_visible(self._rows[spec.key], visible)

    def _on_changed(self, key: str) -> None:
        self.refresh()

    def _show_issues(self) -> None:
        for spec in self.specs:
            issue = self.doc.issue_for(spec.key)
            self.grid.set_error(self._rows[spec.key], issue.message if issue else None)
            if not (spec.visible(self.doc.params) if spec.visible else True):
                self.grid.set_row_visible(self._rows[spec.key], False)

    def focus(self, key: str) -> bool:
        editor = self.editors.get(key)
        if editor is None:
            return False
        editor.focus()
        return True


class StrategyForm(QWidget):
    """The method-specific parameters; rebuilt when the method changes."""

    def __init__(self, doc: SimulationDocument) -> None:
        super().__init__()
        self.doc = doc
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._strategy: str | None = None
        self.form: ParameterForm | None = None
        bind(self, doc.changed, lambda _key: self._rebuild())
        self._rebuild()

    def _rebuild(self) -> None:
        strategy = self.doc.strategy()
        if strategy == self._strategy:
            return
        self._strategy = strategy
        if self.form is not None:
            self.form.setParent(None)
            self.form.deleteLater()
        specs = catalog.STRATEGY_SPECS.get(strategy, ())
        self.form = ParameterForm(self.doc, specs) if specs else None
        if self.form is not None:
            self._layout.addWidget(self.form)
        self.setVisible(bool(specs))


class IssueList(QWidget):
    """The document's findings that are not tied to a visible field (or all of them)."""

    def __init__(self, doc: SimulationDocument, keys: set[str] | None = None, *, ok_text: str | None = None) -> None:
        super().__init__()
        self.doc, self.keys, self.ok_text = doc, keys, ok_text
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        bind(self, doc.validated, self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        shown = [i for i in self.doc.issues if self.keys is None or i.key is None or i.key in self.keys]
        for issue in shown:
            self._layout.addWidget(InlineMessage(issue.severity, issue.message))
        if not shown and self.ok_text:
            self._layout.addWidget(InlineMessage("ok", self.ok_text))


class EstimateNote(QWidget):
    """Remote workload of the current method, updated as parameters change."""

    def __init__(self, doc: SimulationDocument) -> None:
        super().__init__()
        self.doc = doc
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._message: InlineMessage | None = None
        bind(self, doc.validated, self.refresh)
        self.refresh()

    def refresh(self) -> None:
        if self._message is not None:
            self._message.setParent(None)
            self._message.deleteLater()
            self._message = None
        if self.doc.errors():
            return
        e = self.doc.estimates()
        text = None
        if "expected_qpu_submissions" in e:
            where = "emulator" if e.get("simulated") else "D-Wave QPU"
            text = f"Estimate: {e['expected_qpu_submissions']:,} annealing problems and {e['expected_qpu_reads']:,} reads on the {where}."
        elif "expected_qlm_jobs" in e:
            where = "emulator" if e.get("simulated") else "QLM QPU"
            text = f"Estimate: {e['expected_qlm_jobs']:,} circuit jobs and {e['total_circuit_shots']:,} shots on the {where}."
        if text:
            self._message = InlineMessage("info", text)
            self._layout.addWidget(self._message)


class MatrixPicker(QWidget):
    """Input matrix of the simulation, chosen from the library."""

    def __init__(self, doc: SimulationDocument, matrix_ids: list[str]) -> None:
        super().__init__()
        self.doc = doc
        self.grid = FormGrid()
        self.combo = ComboBox()
        for matrix_id in matrix_ids:
            self.combo.addItem(matrix_id, matrix_id)
        current = doc.config.get("input_matrix")
        if current and self.combo.findData(current) < 0:
            self.combo.addItem(f"{current} (missing)", current)
        self._row = self.grid.add_row("Library matrix", self.combo, tooltip="Simulations read their matrix from the workspace library.")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.grid)
        self._updating = False
        self.combo.currentIndexChanged.connect(self._on_index)
        bind(self, doc.changed, lambda key: self.refresh() if key in ("", "config.input_matrix") else None)
        bind(self, doc.validated, self._show_issue)
        self.refresh()
        self._show_issue()

    def refresh(self) -> None:
        self._updating = True
        self.combo.setCurrentIndex(max(self.combo.findData(self.doc.config.get("input_matrix")), 0))
        self._updating = False

    def _on_index(self, index: int) -> None:
        if not self._updating:
            self.doc.set_config("input_matrix", self.combo.itemData(index), "Change input matrix")

    def _show_issue(self) -> None:
        issue = self.doc.issue_for("config.input_matrix")
        self.grid.set_error(self._row, issue.message if issue else None)


OUTPUT_LABELS = {
    "matrix_permuted": "Permuted matrix (.mtx)",
    "run_metrics": "Run metrics (.json, .txt)",
    "run_simulation_parameters": "Parameters used (.json)",
    "permutation": "Permutation (.txt)",
    "coarsened_graph": "Coarsened graph (.mtx)",
}


class OutputsEditor(QWidget):
    def __init__(self, doc: SimulationDocument, available: list[str]) -> None:
        super().__init__()
        self.doc = doc
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.boxes: dict[str, QCheckBox] = {}
        for key in available:
            box = QCheckBox(OUTPUT_LABELS.get(key, key))
            box.toggled.connect(lambda _v, k=key: self._commit())
            layout.addWidget(box)
            self.boxes[key] = box
        bind(self, doc.changed, lambda key: self.refresh() if key in ("", "config.save_output") else None)
        self.refresh()

    def refresh(self) -> None:
        selected = set(self.doc.config.get("save_output") or [])
        for key, box in self.boxes.items():
            box.blockSignals(True)
            box.setChecked(key in selected)
            box.blockSignals(False)

    def _commit(self) -> None:
        selected = sorted(k for k, b in self.boxes.items() if b.isChecked())
        self.doc.set_config("save_output", selected, "Change saved outputs")


class CoarseningPreview(QWidget):
    """Level-by-level dry run of the coarsening, refreshed shortly after each change."""

    def __init__(self, doc: SimulationDocument, run_task: Callable, on_levels: Callable[[dict | None], None]) -> None:
        super().__init__()
        self.doc = doc
        self._run_task = run_task
        self._on_levels = on_levels
        self.table = DataTable(["Level", "Nodes", "Edges", "Ratio", "Kept"], numeric={0, 1, 2, 3}, max_visible_rows=12, stretch=None)
        self.status = QWidget()
        self._status_layout = QVBoxLayout(self.status)
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.run)
        bind(self, doc.changed, self._on_changed)
        self.run()

    def _on_changed(self, key: str) -> None:
        if key == "" or key.startswith(("coarsening_parameters", "general_parameters", "partitioning_parameters.common", "config.input_matrix")):
            self._timer.start()

    def _set_status(self, severity: str, text: str) -> None:
        while self._status_layout.count():
            item = self._status_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._status_layout.addWidget(InlineMessage(severity, text))

    def run(self) -> None:
        if self.doc.errors():
            self._set_status("warning", "Fix the parameter errors to preview the coarsening.")
            self.table.set_rows([])
            self._on_levels(None)
            return
        params = dict(self.doc.params)
        params["_matrix"] = self.doc.config.get("input_matrix")
        sim = self.doc.simulation_id
        self._set_status("info", "Computing preview…")
        self._run_task(lambda: simulations.preview_coarsening(sim, params), self._show, lambda exc: self._set_status("error", str(exc)), self)

    def _show(self, preview: dict[str, Any]) -> None:
        if preview["reachable"]:
            self._set_status("ok", f"The coarsest graph will have {preview['final_coarse_nodes']:,} nodes after "
                                   f"{preview['accepted_levels_count'] - 1} levels ({preview['elapsed_ms']:.0f} ms).")
        else:
            self._set_status("error", f"The requested range cannot be reached. {preview['stop_reason']}")
        self.table.set_rows([
            [lv["level"], lv["nodes"], lv["edges"], fmt(lv["reduction_ratio"], 2) if lv["level"] else "—", "Yes" if lv["accepted"] else "No"]
            for lv in preview["levels"]
        ])
        self._on_levels(preview)
