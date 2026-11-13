"""Editable pages of a simulation and its stages, bound to a SimulationDocument."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPlainTextEdit, QPushButton

from hdd.services import catalog
from hdd.services.catalog import method_label
from hdd.services.matrix_files import inspect_matrix

from .documents import SimulationDocument, bind
from .editors import CoarseningPreview, EstimateNote, IssueList, MatrixPicker, OutputsEditor, ParameterForm, StrategyForm
from .pages import Page, _buttons, _matrix_rows
from .theme import Theme
from .tree import Node
from .widgets import InlineMessage, PropertyTable
from .widgets.tables import DataTable, fmt


@dataclass
class SimulationActions:
    """What a simulation page can ask the window to do."""

    document: Callable[[dict], SimulationDocument]
    run: Callable[[str], None]
    save: Callable[[str], None]
    revert: Callable[[str], None]
    save_as_preset: Callable[[str], None]
    compare: Callable[[str, str | None], None]
    auto_select: Callable[[str], None]
    load_preset: Callable[[str, str], None]
    activate_preset: Callable[[str, str], None]
    delete_preset: Callable[[str, str], None]
    open_path: Callable[[str], None]
    run_task: Callable
    show_coarsening: Callable[[dict | None], None]
    show_matrix: Callable[[str], None]
    matrix_ids: Callable[[], list[str]]


class EditorPage(Page):
    """A page whose forms can take keyboard focus on a given parameter."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[ParameterForm] = []

    def form(self, doc: SimulationDocument, specs) -> ParameterForm:
        form = ParameterForm(doc, specs)
        self.forms.append(form)
        return form

    def focus(self, key: str) -> bool:
        return any(form.focus(key) for form in self.forms)


def _button(text: str, slot, *, icon: str | None = None, primary: bool = False, tint: str = "default") -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setProperty("role", "primary")
    if icon:
        Theme.instance().bind_icon(button, icon, "on_accent" if primary else tint)
    button.clicked.connect(lambda: slot())
    return button


def _keys(*prefixes: str) -> set[str]:
    return {s.key for s in catalog.ALL_SPECS if s.key.startswith(prefixes)}


def build_simulation(node: Node, data: dict, a: SimulationActions) -> Page:
    doc = a.document(data)
    sid = doc.simulation_id
    page = EditorPage()

    summary = PropertyTable()

    def refresh_summary() -> None:
        pp = doc.params["partitioning_parameters"]
        strategy = pp["partitioning_strategy"]
        summary.set_rows([
            ("Input matrix", str(doc.config.get("input_matrix")), ""),
            ("Active preset", doc.active_preset, ""),
            ("Method", method_label(strategy, (pp.get("strategies") or {}).get(strategy, {}).get("simulated")), ""),
            ("Number of parts (k)", fmt(pp["common"]["k_target"]), ""),
            ("Runs", fmt(data.get("runs_count")), ""),
        ])

    bind(page, doc.changed, lambda _k: refresh_summary())
    refresh_summary()
    page.section("Summary", summary)
    page.section("Checks", IssueList(doc, ok_text="Parameters are valid."), EstimateNote(doc))

    save = _button("Save", lambda: a.save(sid), icon="save")
    revert = _button("Revert", lambda: a.revert(sid), icon="undo")

    def refresh_buttons(dirty: bool | None = None) -> None:
        dirty = doc.is_dirty() if dirty is None else dirty
        save.setEnabled(dirty)
        revert.setEnabled(dirty)

    bind(page, doc.dirtyChanged, refresh_buttons)
    refresh_buttons()
    page.add(_buttons(_button("Run", lambda: a.run(sid), icon="run", primary=True), save, revert))
    page.add(_buttons(
        _button("Save as preset…", lambda: a.save_as_preset(sid), icon="presets"),
        _button("Compare…", lambda: a.compare(sid, None), icon="compare"),
        _button("Auto-select parameters", lambda: a.auto_select(sid), icon="tuning"),
    ))
    page.add(_buttons(_button("Open folder", lambda: a.open_path(data["demonstrator_dir"]), icon="folder")))
    return page


def build_input(node: Node, data: dict, a: SimulationActions) -> Page:
    doc = a.document(data)
    page = EditorPage()
    picker = MatrixPicker(doc, a.matrix_ids())
    info = PropertyTable()

    def refresh_info() -> None:
        matrix_id = doc.config.get("input_matrix")
        try:
            details = inspect_matrix(str(matrix_id))
            info.set_rows(_matrix_rows(details.get("info") or {}))
            a.show_matrix(matrix_id)
        except (FileNotFoundError, ValueError) as exc:
            info.set_rows([("Status", f"Not available: {exc}", "")])

    bind(page, doc.changed, lambda key: refresh_info() if key in ("", "config.input_matrix") else None)
    page.section("Matrix", picker, info)
    refresh_info()
    page.section("Graph", page.form(doc, catalog.GENERAL_SPECS))
    page.add(IssueList(doc, {"config.input_matrix"} | _keys("general_parameters")))
    return page


def build_coarsening(node: Node, data: dict, a: SimulationActions) -> Page:
    doc = a.document(data)
    page = EditorPage()
    page.section("Coarsening", page.form(doc, catalog.COARSENING_SPECS))
    page.section("Preview per level", CoarseningPreview(doc, a.run_task, a.show_coarsening))
    return page


def build_partitioning(node: Node, data: dict, a: SimulationActions) -> Page:
    doc = a.document(data)
    page = EditorPage()
    page.section("Method", page.form(doc, catalog.PARTITIONING_SPECS))
    strategy_form = StrategyForm(doc)
    if strategy_form.form is not None:
        page.forms.append(strategy_form.form)
    section = page.section("Method parameters", strategy_form)

    def update_section(_key: str = "") -> None:
        section.setVisible(bool(catalog.STRATEGY_SPECS.get(doc.strategy())))
        if strategy_form.form is not None and strategy_form.form not in page.forms:
            page.forms.append(strategy_form.form)

    bind(page, doc.changed, update_section)
    update_section()
    page.add(EstimateNote(doc))
    page.add(IssueList(doc, _keys("partitioning_parameters") | {"coarsening_parameters.coarsen_superior_limit"}))
    return page


def build_refinement(node: Node, data: dict, a: SimulationActions) -> Page:
    doc = a.document(data)
    page = EditorPage()
    page.section("Refinement per level", page.form(doc, catalog.REFINEMENT_SPECS))
    return page


def build_outputs(node: Node, data: dict, a: SimulationActions) -> Page:
    doc = a.document(data)
    page = EditorPage()
    page.section("Files written by each run", OutputsEditor(doc, data.get("available_save_outputs", [])))
    note = InlineMessage("info", "Plots of a run need the permuted matrix, the permutation and the coarsened graph.")
    page.add(note)
    return page


def build_presets(node: Node, data: dict, a: SimulationActions) -> Page:
    doc = a.document(data)
    sid = doc.simulation_id
    page = EditorPage()
    files = data.get("preset_files", [])
    table = DataTable(["Preset", "State"], max_visible_rows=12)
    table.set_rows([[f, "Active" if f == data["active_parameters_file"] else ""] for f in files], files)
    page.section("Parameter presets", table)

    def selected() -> str | None:
        row = table.currentRow()
        return table.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 else None

    load = _button("Load into editor", lambda: selected() and a.load_preset(sid, selected()), icon="import")
    activate = _button("Make active", lambda: selected() and a.activate_preset(sid, selected()), icon="ok")
    compare = _button("Compare with current", lambda: selected() and a.compare(sid, selected()), icon="compare")
    delete = _button("Delete", lambda: selected() and a.delete_preset(sid, selected()), icon="delete")

    def update() -> None:
        name = selected()
        for button in (load, compare):
            button.setEnabled(bool(name))
        activate.setEnabled(bool(name) and name != data["active_parameters_file"])
        delete.setEnabled(bool(name) and name not in ("simulation_parameters.json", data["active_parameters_file"]))

    table.itemSelectionChanged.connect(update)
    update()
    page.add(_buttons(load, activate, compare, delete))
    page.add(_buttons(_button("Save current parameters as preset…", lambda: a.save_as_preset(sid), icon="save")))
    return page


def build_preset(node: Node, data: dict, a: SimulationActions) -> Page:
    sid, name = node.simulation_id, data["filename"]
    page = EditorPage()
    text = QPlainTextEdit(json.dumps(data["parameters"], indent=2))
    text.setReadOnly(True)
    text.setFont(Theme.instance().mono_font())
    text.setMinimumHeight(380)
    page.add(_buttons(
        _button("Load into editor", lambda: a.load_preset(sid, name), icon="import"),
        _button("Make active", lambda: a.activate_preset(sid, name), icon="ok"),
        _button("Compare with current", lambda: a.compare(sid, name), icon="compare"),
    ))
    page.section(name, text)
    return page


BUILDERS: dict[str, Callable[[Node, Any, SimulationActions], Page]] = {
    "simulation": build_simulation,
    "input": build_input,
    "coarsening": build_coarsening,
    "partitioning": build_partitioning,
    "refinement": build_refinement,
    "outputs": build_outputs,
    "presets": build_presets,
    "preset": build_preset,
}

#: Tree node kind that holds each parameter block, for "go to the problem".
NODE_FOR_BLOCK = {
    "general_parameters": "input",
    "config": "input",
    "coarsening_parameters": "coarsening",
    "partitioning_parameters": "partitioning",
    "uncoarsening_parameters": "refinement",
}


def node_kind_for_key(key: str | None) -> str:
    if not key:
        return "simulation"
    return NODE_FOR_BLOCK.get(key.split(".")[0], "simulation")
