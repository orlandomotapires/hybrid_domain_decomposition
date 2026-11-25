"""Batch configuration editor: matrices × methods × coarsening scales, shared and per-method parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hdd.services import batch, catalog
from hdd.services.catalog import method_label

from .batch_doc import BatchDocument
from .documents import bind
from .editors import ComboBox, DoubleSpinBox, SpinBox
from .pages import PARAMETER_LABELS, Page, _button, _buttons
from .theme import Theme
from .widgets import FormGrid, InlineMessage, PropertyTable
from .widgets.forms import NUMBER_WIDTH
from .widgets.tables import fmt


@dataclass
class BatchActions:
    save: Callable[[], bool]
    revert: Callable[[], None]
    run: Callable[[], None]
    open_path: Callable[[str], None]


SHARED_FIELDS = (
    # (path in common_defaults, label, kind, minimum, maximum, decimals)
    (("partitioning_common", "k_target"), "Number of parts (k)", "int", 1, 4096, 0),
    (("partitioning_common", "balance_tolerance"), "Balance tolerance", "float", 0.0, 100.0, 3),
    (("general_parameters", "seed"), "Random seed", "int", 0, 2**31 - 1, 0),
    (("coarsening_parameters", "coarsen_ratio"), "Reduction ratio", "float", 0.05, 1.0, 2),
    (("coarsening_parameters", "max_levels"), "Maximum levels", "int", 1, 200, 0),
)


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(Theme.instance().tokens.metrics.row_height + 4)
    table.setShowGrid(False)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return table


def _fit_height(table: QTableWidget) -> None:
    table.setFixedHeight(table.horizontalHeader().sizeHint().height() + max(table.rowCount(), 1) * table.verticalHeader().defaultSectionSize() + 2)


def _check_item(checked: bool, enabled: bool = True) -> QTableWidgetItem:
    item = QTableWidgetItem()
    flags = Qt.ItemFlag.ItemIsUserCheckable
    if enabled:
        flags |= Qt.ItemFlag.ItemIsEnabled
    item.setFlags(flags)
    item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    return item


def _text_item(text: str, tooltip: str = "") -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
    if tooltip:
        item.setToolTip(tooltip)
    return item


def _number_box(kind: str, minimum: float, maximum: float, decimals: int = 3):
    if kind == "int":
        box = SpinBox()
        box.setRange(int(minimum), int(min(maximum, 2**31 - 1)))
        box.setGroupSeparatorShown(True)
    else:
        box = DoubleSpinBox()
        box.setDecimals(decimals)
        box.setRange(float(minimum), float(maximum))
    box.setAlignment(Qt.AlignmentFlag.AlignRight)
    box.setFixedWidth(NUMBER_WIDTH)
    return box


def _strategy_spec(strategy: str, key: str):
    return next((s for s in catalog.STRATEGY_SPECS.get(strategy, ()) if s.path[-1] == key), None)


def build_batch_config(doc: BatchDocument, library: list[dict[str, Any]], actions: BatchActions) -> Page:
    page = Page()
    syncers: list[Callable[[], None]] = []

    # ----------------------------------------------------------- plan
    plan_table = PropertyTable()
    problems_box = QWidget()
    problems_layout = QVBoxLayout(problems_box)
    problems_layout.setContentsMargins(0, 0, 0, 0)
    problems_layout.setSpacing(4)

    def sync_plan() -> None:
        plan = doc.plan()
        totals = plan["totals"]
        rows = [("Cases", fmt(len(plan["cases"])), ""), ("Run in the background", fmt(totals["async_count"]), "")]
        rows.append(("Estimated duration", fmt(totals["seconds"] / 60, 1) if totals["estimated"] else "No earlier runs to estimate from", "min" if totals["estimated"] else ""))
        if totals["submissions"]:
            rows.append(("Remote QPU submissions", fmt(totals["submissions"]), ""))
        plan_table.set_rows(rows)
        while problems_layout.count():
            item = problems_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for message in doc.problems():
            problems_layout.addWidget(InlineMessage("error", message))
        if totals["over_capacity"]:
            problems_layout.addWidget(InlineMessage("warning", f"{totals['over_capacity']} cases ask for a coarse graph larger than their backend accepts; they will fail."))

    syncers.append(sync_plan)
    page.section("Plan", plan_table, problems_box)

    # ------------------------------------------------------- matrices
    info = {m["id"]: m for m in library}
    matrix_ids = sorted(set(info) | {m.get("key") for m in doc.config.get("matrices", [])})
    matrices_table = _table(["Matrix", "Rows", "Nonzeros"])
    matrices_table.horizontalHeaderItem(1).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    matrices_table.horizontalHeaderItem(2).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    matrices_table.setRowCount(len(matrix_ids))
    for row, matrix_id in enumerate(matrix_ids):
        details = (info.get(matrix_id) or {}).get("info") or {}
        missing = matrix_id not in info
        name = QTableWidgetItem(matrix_id + ("  (not in the library)" if missing else ""))
        name.setToolTip(matrix_id)
        name.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        name.setData(Qt.ItemDataRole.UserRole, matrix_id)
        matrices_table.setItem(row, 0, name)
        for column, value in ((1, details.get("rows")), (2, details.get("nnz"))):
            item = _text_item(fmt(value) if value is not None else "—")
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setFont(Theme.instance().numeric_font())
            matrices_table.setItem(row, column, item)
    _fit_height(matrices_table)

    def sync_matrices() -> None:
        chosen = {m.get("key") for m in doc.config.get("matrices", [])}
        matrices_table.blockSignals(True)
        for row in range(matrices_table.rowCount()):
            item = matrices_table.item(row, 0)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in chosen else Qt.CheckState.Unchecked)
        matrices_table.blockSignals(False)

    def on_matrix(item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        matrix_id, checked = item.data(Qt.ItemDataRole.UserRole), item.checkState() == Qt.CheckState.Checked

        def change(config: dict) -> None:
            current = [m for m in config.get("matrices", []) if m.get("key") != matrix_id]
            if checked:
                current.append({"key": matrix_id})
                current.sort(key=lambda m: matrix_ids.index(m["key"]) if m["key"] in matrix_ids else 0)
            config["matrices"] = current

        doc.edit(f"{'Add' if checked else 'Remove'} matrix {matrix_id}", change)

    matrices_table.itemChanged.connect(on_matrix)
    syncers.append(sync_matrices)
    page.section("Matrices", matrices_table)

    # ----------------------------------------------- methods × scales
    scales = [p.get("key") for p in doc.config.get("coarsening_presets", [])]
    algorithms = doc.config.get("algorithm_presets", [])
    grid = _table(["Method"] + [s.capitalize() for s in scales] + ["Background"])
    grid.setRowCount(len(algorithms))
    for row, alg in enumerate(algorithms):
        params = alg.get("strategy_parameters") or {}
        grid.setItem(row, 0, _text_item(method_label(alg.get("partitioning_strategy"), params.get("simulated"), short=True),
                                        f"{method_label(alg.get('partitioning_strategy'), params.get('simulated'))} ({alg.get('key', '')})"))
    for column, scale in enumerate(scales, start=1):
        grid.horizontalHeaderItem(column).setToolTip(f"Run the method at the {scale} coarsening scale")
    grid.horizontalHeaderItem(len(scales) + 1).setToolTip(
        "Remote QPU cases that are submitted and collected later, so the rest of the batch does not wait for the queue."
    )
    _fit_height(grid)

    def sync_grid() -> None:
        grid.blockSignals(True)
        async_keys = set(doc.config.get("async_remote_case_keys", []))
        for row, alg in enumerate(doc.config.get("algorithm_presets", [])):
            allowed = set(alg.get("allowed_sizes", []))
            for column, scale in enumerate(scales, start=1):
                grid.setItem(row, column, _check_item(scale in allowed))
            remote = batch.is_remote_hardware(alg.get("partitioning_strategy", ""), alg.get("strategy_parameters"))
            item = _check_item(alg.get("key") in async_keys, enabled=remote)
            if not remote:
                item.setToolTip("Only remote QPU methods can run in the background.")
            grid.setItem(row, len(scales) + 1, item)
        grid.blockSignals(False)

    def on_grid(item: QTableWidgetItem) -> None:
        row, column = item.row(), item.column()
        if column == 0:
            return
        alg_key = algorithms[row].get("key")
        checked = item.checkState() == Qt.CheckState.Checked
        if column <= len(scales):
            scale = scales[column - 1]

            def change(config: dict) -> None:
                alg = next(a for a in config["algorithm_presets"] if a.get("key") == alg_key)
                allowed = [s for s in alg.get("allowed_sizes", []) if s != scale]
                alg["allowed_sizes"] = [s for s in scales if s in allowed or (checked and s == scale)]

            doc.edit(f"{'Include' if checked else 'Exclude'} {alg_key} at {scale} scale", change)
        else:
            def change(config: dict) -> None:
                keys = [k for k in config.get("async_remote_case_keys", []) if k != alg_key]
                config["async_remote_case_keys"] = keys + ([alg_key] if checked else [])

            doc.edit(f"{'Run' if checked else 'Do not run'} {alg_key} in the background", change)

    grid.itemChanged.connect(on_grid)
    syncers.append(sync_grid)
    page.section("Cases", grid)

    # ------------------------------------------------- coarsening scales
    scale_form = FormGrid()
    scale_boxes: list[tuple[Any, Any]] = []
    for index, scale in enumerate(scales):
        low, high = _number_box("int", 1, 10**7), _number_box("int", 1, 10**7)
        holder = QWidget()
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        dash = QLabel("to")
        dash.setProperty("role", "unit")
        unit = QLabel("nodes")
        unit.setProperty("role", "unit")
        for widget in (low, dash, high, unit):
            line.addWidget(widget)
        line.addStretch(1)
        scale_form.add_row(f"{scale.capitalize()}", holder, tooltip="Coarsening stops once the graph has between these many nodes.")
        scale_boxes.append((low, high))

        def make(i: int, bound: str):
            def on_value(value: int) -> None:
                def change(config: dict) -> None:
                    config["coarsening_presets"][i][bound] = int(value)

                doc.edit(f"Change {scales[i]} scale", change, merge_key=f"scale.{i}.{bound}")

            return on_value

        low.valueChanged.connect(make(index, "coarsen_inferior_limit"))
        high.valueChanged.connect(make(index, "coarsen_superior_limit"))

    def sync_scales() -> None:
        for (low, high), preset in zip(scale_boxes, doc.config.get("coarsening_presets", [])):
            for box, key in ((low, "coarsen_inferior_limit"), (high, "coarsen_superior_limit")):
                box.blockSignals(True)
                box.setValue(int(preset.get(key) or 0))
                box.blockSignals(False)

    syncers.append(sync_scales)
    page.section("Coarsening scales", scale_form)

    # --------------------------------------------------- shared parameters
    shared = FormGrid()
    shared_boxes = []
    for path, label, kind, minimum, maximum, decimals in SHARED_FIELDS:
        box = _number_box(kind, minimum, maximum, decimals)
        shared.add_row(label, box)
        shared_boxes.append((path, box, kind))

        def on_shared(value, p=path, k=kind, text=label) -> None:
            def change(config: dict) -> None:
                config.setdefault("common_defaults", {}).setdefault(p[0], {})[p[1]] = int(value) if k == "int" else float(value)

            doc.edit(f"Change {text.lower()}", change, merge_key="shared." + ".".join(p))

        box.valueChanged.connect(on_shared)
    strategy_spec = catalog.COARSENING_SPECS[0]
    matching = ComboBox()
    for value, text in strategy_spec.choices:
        matching.addItem(text, value)
    shared.add_row("Matching strategy", matching, tooltip=strategy_spec.help)

    def on_matching(index: int) -> None:
        value = matching.itemData(index)
        doc.edit("Change matching strategy", lambda c: c.setdefault("common_defaults", {}).setdefault("coarsening_parameters", {}).__setitem__("strategy", value))

    matching.currentIndexChanged.connect(on_matching)

    def sync_shared() -> None:
        defaults = doc.config.get("common_defaults", {})
        for path, box, kind in shared_boxes:
            value = (defaults.get(path[0]) or {}).get(path[1])
            box.blockSignals(True)
            box.setValue(int(value or 0) if kind == "int" else float(value or 0.0))
            box.blockSignals(False)
        matching.blockSignals(True)
        matching.setCurrentIndex(max(matching.findData((defaults.get("coarsening_parameters") or {}).get("strategy")), 0))
        matching.blockSignals(False)

    syncers.append(sync_shared)
    page.section("Shared parameters", shared)

    # ---------------------------------------------- per-method parameters
    method_syncers = []
    for alg_index, alg in enumerate(algorithms):
        strategy = alg.get("partitioning_strategy", "")
        params = alg.get("strategy_parameters") or {}
        if not params:
            continue
        form = FormGrid()
        fields = []
        for key, value in params.items():
            spec = _strategy_spec(strategy, key)
            label = spec.label if spec else PARAMETER_LABELS.get(key, (key.replace("_", " ").capitalize(), ""))[0]
            if isinstance(value, bool):
                if key == "simulated":
                    continue  # the method itself; changing it would make it another method
                editor = QCheckBox()
            elif isinstance(value, int):
                editor = _number_box("int", spec.minimum if spec and spec.minimum is not None else 0, spec.maximum if spec and spec.maximum else 10**9)
            elif isinstance(value, float):
                editor = _number_box("float", spec.minimum if spec and spec.minimum is not None else 0.0, spec.maximum if spec and spec.maximum else 1e9,
                                     spec.decimals if spec else 4)
            else:
                editor = QLineEdit()
            form.add_row(label, editor, tooltip=spec.help if spec else "")
            fields.append((key, editor))

            def make(i: int, k: str, widget):
                def commit(value: Any) -> None:
                    def change(config: dict) -> None:
                        config["algorithm_presets"][i].setdefault("strategy_parameters", {})[k] = value

                    doc.edit(f"Change {k.replace('_', ' ')} of {algorithms[i].get('key')}", change, merge_key=f"alg.{i}.{k}")

                if isinstance(widget, QCheckBox):
                    widget.toggled.connect(lambda v: commit(bool(v)))
                elif isinstance(widget, QLineEdit):
                    widget.editingFinished.connect(lambda: commit(widget.text().strip() or None))
                elif isinstance(widget, SpinBox):
                    widget.valueChanged.connect(lambda v: commit(int(v)))
                else:
                    widget.valueChanged.connect(lambda v: commit(float(v)))

            make(alg_index, key, editor)

        def sync_method(i=alg_index, fields=fields) -> None:
            current = doc.config["algorithm_presets"][i].get("strategy_parameters") or {}
            for key, widget in fields:
                value = current.get(key)
                widget.blockSignals(True)
                if isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                elif isinstance(widget, QLineEdit):
                    widget.setText("" if value is None else str(value))
                else:
                    widget.setValue(value or 0)
                widget.blockSignals(False)

        method_syncers.append(sync_method)
        page.section(f"{method_label(strategy, params.get('simulated'))} ({alg.get('key')})", form, expanded=False)
    syncers.extend(method_syncers)

    save = _button("Save", lambda: actions.save(), icon="save", primary=True)
    revert = _button("Revert", actions.revert)
    run = _button("Run batch…", actions.run, icon="batch")
    page.add(_buttons(save, revert, run, _button("Open folder", lambda: actions.open_path("batch"), icon="folder")))

    def sync_buttons() -> None:
        save.setEnabled(doc.is_dirty())
        revert.setEnabled(doc.is_dirty())

    syncers.append(sync_buttons)

    def sync_all() -> None:
        for fn in syncers:
            fn()

    bind(page, doc.changed, sync_all)
    bind(page, doc.dirtyChanged, lambda _d: sync_buttons())
    sync_all()
    return page
