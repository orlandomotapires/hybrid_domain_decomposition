"""Settings pages, one per project-tree node kind.

A page is built in two steps: ``load_<kind>`` runs on a worker thread and returns
plain data; ``build_<kind>`` turns that data into widgets on the GUI thread.
Parameter pages are read-only in this version.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from hdd.services import batch, hardware, matrices, results, simulations, tuning
from hdd.services.catalog import method_label
from hdd.services.matrix_files import inspect_matrix

from .theme import Theme
from .tree import Node
from .widgets import InlineMessage, PropertyTable, Section
from .widgets.tables import DataTable, fmt

READ_ONLY_NOTE = "Read-only in this version of the desktop app. Edit the batch configuration in the web Studio for now."

PARAMETER_LABELS = {
    "dof_per_node": ("Rows per graph node (dof)", ""),
    "seed": ("Random seed", ""),
    "coarsen_inferior_limit": ("Lower limit", "nodes"),
    "coarsen_superior_limit": ("Upper limit", "nodes"),
    "coarsen_ratio": ("Reduction ratio", ""),
    "max_levels": ("Maximum levels", ""),
    "max_node_weight": ("Maximum node weight", ""),
    "strategy": ("Matching strategy", ""),
    "weight": ("Edge weight attribute", ""),
    "k_target": ("Number of parts (k)", ""),
    "balance_tolerance": ("Balance tolerance", ""),
    "refine_objective": ("Objective", ""),
    "refine_balance_lambda": ("Balance weight (λ)", ""),
    "refine_max_passes_per_level": ("Passes per level", ""),
    "refine_max_moves_per_pass": ("Moves per pass", ""),
    "validate_node_weights": ("Validate node weights", ""),
    "num_reads": ("Reads per bisection", ""),
    "num_starts": ("Restarts", ""),
    "simulated": ("Emulated", ""),
    "qpu_solver_name": ("QPU solver", ""),
    "qpu_region": ("QPU region", ""),
    "circuit_depth": ("Circuit depth (p)", ""),
    "num_steps": ("Optimizer steps", ""),
    "num_shots": ("Shots", ""),
    "qlm_qpu_name": ("QLM QPU", ""),
    "qubo_balance_lambda": ("QUBO balance weight", ""),
    "balance_violation_lambda": ("Balance violation weight", ""),
    "adam_learning_rate": ("Learning rate", ""),
}

OUTPUT_LABELS = {
    "matrix_permuted": "Permuted matrix (.mtx)",
    "run_metrics": "Run metrics (.json, .txt)",
    "run_simulation_parameters": "Parameters used (.json)",
    "permutation": "Permutation (.txt)",
    "coarsened_graph": "Coarsened graph (.mtx)",
}


@dataclass
class PageActions:
    """What a page can ask the window to do."""

    run_simulation: Callable[[str], None]
    open_path: Callable[[str], None]
    export_run: Callable[[str], None]
    select_key: Callable[[str], None]
    compare_runs: Callable[[list[str]], None] = lambda dirs: None
    show_batch: Callable[[str, str, str], None] = lambda batch, matrix, scale: None


def _param_rows(block: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows = []
    for key, value in block.items():
        if isinstance(value, dict):
            continue
        label, unit = PARAMETER_LABELS.get(key, (key.replace("_", " ").capitalize(), ""))
        rows.append((label, fmt(value, 3) if isinstance(value, float) else fmt(value), unit))
    return rows


def _buttons(*buttons: QPushButton) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(8)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return row


def _button(text: str, callback: Callable[[], None], *, icon: str | None = None, primary: bool = False) -> QPushButton:
    button = QPushButton(text)
    if primary:
        button.setProperty("role", "primary")
    if icon:
        Theme.instance().bind_icon(button, icon, "on_accent" if primary else "default")
    button.clicked.connect(callback)
    return button


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

    def section(self, title: str, *widgets: QWidget, expanded: bool = True) -> Section:
        section = Section(title, expanded=expanded)
        for widget in widgets:
            section.add(widget)
        self.add(section)
        return section

    def note(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "muted")
        label.setWordWrap(True)
        self.add(label)
        return label

    def finish(self) -> "Page":
        self.box.addStretch(1)
        return self


# ------------------------------------------------------------------ loaders
def _simulation(node: Node) -> dict[str, Any]:
    return simulations.get_simulation(node.simulation_id)


LOADERS: dict[str, Callable[[Node], Any]] = {
    "matrices": lambda node: matrices.list_matrices()["matrices"],
    "matrix": lambda node: inspect_matrix(node.data["matrix"]),
    "simulations": lambda node: simulations.list_simulations()["demonstrators"],
    "simulation": _simulation,
    "input": _simulation,
    "coarsening": _simulation,
    "partitioning": _simulation,
    "refinement": _simulation,
    "outputs": _simulation,
    "presets": _simulation,
    "preset": lambda node: simulations.load_preset(node.simulation_id, node.data["preset"]),
    "tuning": lambda node: tuning.list_studies(node.simulation_id, None),
    "study": lambda node: tuning.get_study(node.simulation_id, node.data["study"]),
    "results": lambda node: results.list_runs(node.simulation_id)["runs"],
    "run": lambda node: results.get_run_detail(node.data["result_dir"]),
    "batch": lambda node: batch.list_batch_runs()["batch_runs"],
    "batch_config": lambda node: {**batch.load_configuration(), "plan": batch.plan(batch.load_configuration()["configuration"], batch.duration_estimates())},
    "batch_runs": lambda node: batch.list_batch_runs()["batch_runs"],
    "batch_run": lambda node: {**batch.get_batch_run(node.data["batch"]), "analysis": results.batch_analysis(node.data["batch"])},
    "hardware": lambda node: hardware.environment_status(),
}


def load(node: Node) -> Any:
    loader = LOADERS.get(node.kind)
    return loader(node) if loader else None


# ----------------------------------------------------------------- builders
def build(node: Node, data: Any, actions: PageActions) -> QWidget:
    builder = BUILDERS.get(node.kind, _build_empty)
    return builder(node, data, actions).finish()


def build_error(message: str) -> QWidget:
    page = Page()
    page.add(InlineMessage("error", message))
    return page.finish()


def _build_empty(node: Node, data: Any, actions: PageActions) -> Page:
    page = Page()
    page.note("Nothing to configure here.")
    return page


def _build_matrices(node: Node, data: list[dict], actions: PageActions) -> Page:
    page = Page()
    table = DataTable(["Matrix", "Rows", "Nonzeros", "Used by"], numeric={1, 2})
    table.set_rows(
        [[m["id"], (m.get("info") or {}).get("rows"), (m.get("info") or {}).get("nnz"), ", ".join(m.get("used_by") or []) or "—"] for m in data],
        [f"matrix:{m['id']}" for m in data],
    )
    table.on_activate(actions.select_key)
    page.section("Library", table)
    if not data:
        page.note("The library is empty. Import a Matrix Market (.mtx) file to start.")
    return page


def _matrix_rows(info: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows, nnz = info.get("rows"), info.get("nnz")
    density = (100.0 * nnz / (rows * rows)) if rows and nnz else None
    return [
        ("File", info.get("filename") or "—", ""),
        ("Format", f"Matrix Market, {info.get('format_type', '—')}", ""),
        ("Dimension (n)", fmt(rows), ""),
        ("Nonzeros", fmt(nnz), ""),
        ("Density", fmt(density, 3) if density is not None else "—", "%"),
        ("Symmetry", str(info.get("symmetry", "—")).capitalize(), ""),
        ("Field", str(info.get("field_type", "—")).capitalize(), ""),
        ("Size on disk", fmt((info.get("size_bytes") or 0) / 1e6, 1), "MB"),
    ]


def _build_matrix(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    if not data.get("ready", True):
        page.add(InlineMessage("error", data.get("error") or "The matrix file is missing."))
    page.section("Matrix", PropertyTable(_matrix_rows(data.get("info") or {})))
    used = ", ".join(data.get("used_by") or []) or "No simulation uses this matrix."
    label = QLabel(used)
    label.setWordWrap(True)
    page.section("Used by", label)
    return page


def _build_simulations(node: Node, data: list[dict], actions: PageActions) -> Page:
    page = Page()
    table = DataTable(["Simulation", "Matrix", "Method", "k", "Runs"], numeric={3, 4})
    rows, keys = [], []
    for sim in data:
        if sim.get("error"):
            rows.append([sim["id"], "—", "Invalid configuration", None, None])
        else:
            pp = sim["simulation_parameters"]["partitioning_parameters"]
            strategy = pp["partitioning_strategy"]
            simulated = (pp.get("strategies") or {}).get(strategy, {}).get("simulated")
            rows.append([sim["id"], sim["simulation_config"]["input_matrix"], method_label(strategy, simulated), pp["common"]["k_target"], sim["runs_count"]])
        keys.append(f"simulation:{sim['id']}")
    table.set_rows(rows, keys)
    table.on_activate(actions.select_key)
    page.section("Simulations", table)
    return page


def _estimate_text(estimates: dict[str, Any]) -> str | None:
    if "expected_qpu_submissions" in estimates:
        where = "emulator" if estimates.get("simulated") else "D-Wave QPU"
        return f"{estimates['expected_qpu_submissions']:,} annealing problems and {estimates['expected_qpu_reads']:,} reads on the {where}."
    if "expected_qlm_jobs" in estimates:
        where = "emulator" if estimates.get("simulated") else "QLM QPU"
        return f"{estimates['expected_qlm_jobs']:,} circuit jobs and {estimates['total_circuit_shots']:,} shots on the {where}."
    return None


def _build_simulation(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    pp = data["simulation_parameters"]["partitioning_parameters"]
    strategy = pp["partitioning_strategy"]
    simulated = (pp.get("strategies") or {}).get(strategy, {}).get("simulated")
    matrix = data.get("matrix") or {}
    if not matrix.get("ready", True):
        page.add(InlineMessage("error", f"Input matrix {data['simulation_config']['input_matrix']!r} is not in the library."))
    page.section("Summary", PropertyTable([
        ("Input matrix", data["simulation_config"]["input_matrix"], ""),
        ("Active preset", data["active_parameters_file"], ""),
        ("Method", method_label(strategy, simulated), ""),
        ("Number of parts (k)", fmt(pp["common"]["k_target"]), ""),
        ("Runs", fmt(data["runs_count"]), ""),
    ]))
    estimate = _estimate_text(data.get("estimates") or {})
    if estimate:
        page.add(InlineMessage("info", f"Estimate: {estimate}"))
    for warning in (data.get("estimates") or {}).get("warnings", []):
        page.add(InlineMessage("warning", warning))
    page.add(_buttons(
        _button("Run", lambda: actions.run_simulation(data["id"]), icon="run", primary=True),
        _button("Open folder", lambda: actions.open_path(data["demonstrator_dir"]), icon="folder"),
    ))
    return page


def _build_input(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    matrix = data.get("matrix") or {}
    if not matrix.get("ready", True):
        page.add(InlineMessage("error", matrix.get("error") or "The matrix is not in the library."))
    page.section("Matrix", PropertyTable([("Library matrix", str(matrix.get("id")), "")] + _matrix_rows(matrix.get("info") or {})))
    page.section("Graph", PropertyTable(_param_rows(data["simulation_parameters"]["general_parameters"])))
    page.note(READ_ONLY_NOTE)
    return page


def _stage_page(block_name: str, title: str) -> Callable[[Node, dict, PageActions], Page]:
    def builder(node: Node, data: dict, actions: PageActions) -> Page:
        page = Page()
        page.section(title, PropertyTable(_param_rows(data["simulation_parameters"][block_name])))
        page.note(READ_ONLY_NOTE)
        return page

    return builder


def _build_partitioning(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    pp = data["simulation_parameters"]["partitioning_parameters"]
    strategy = pp["partitioning_strategy"]
    block = (pp.get("strategies") or {}).get(strategy, {})
    page.section("Method", PropertyTable([("Method", method_label(strategy, block.get("simulated")), "")] + _param_rows(pp["common"])))
    if block:
        page.section(method_label(strategy, block.get("simulated")), PropertyTable(_param_rows(block)))
    estimate = _estimate_text(data.get("estimates") or {})
    if estimate:
        page.add(InlineMessage("info", f"Estimate: {estimate}"))
    page.note(READ_ONLY_NOTE)
    return page


def _build_outputs(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    saved = set(data["simulation_config"].get("save_output") or [])
    rows = [(OUTPUT_LABELS.get(key, key), "Saved" if key in saved else "Not saved", "") for key in data.get("available_save_outputs", [])]
    page.section("Files written by each run", PropertyTable(rows))
    if not {"matrix_permuted", "permutation", "coarsened_graph"} <= saved:
        page.add(InlineMessage("info", "Plots of a run need the permuted matrix, the permutation and the coarsened graph."))
    page.note(READ_ONLY_NOTE)
    return page


def _build_presets(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    table = DataTable(["Preset", "State"])
    files = data.get("preset_files", [])
    table.set_rows([[f, "Active" if f == data["active_parameters_file"] else ""] for f in files], [f"preset:{data['id']}/{f}" for f in files])
    table.on_activate(actions.select_key)
    page.section("Parameter presets", table)
    return page


def _build_preset(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    text = QPlainTextEdit(json.dumps(data["parameters"], indent=2))
    text.setReadOnly(True)
    text.setFont(Theme.instance().mono_font())
    text.setMinimumHeight(420)
    page.section(data["filename"], text)
    return page


def _build_tuning(node: Node, data: list[dict], actions: PageActions) -> Page:
    page = Page()
    table = DataTable(["Study", "Objectives", "Sampler", "Trials"], numeric={3})
    table.set_rows(
        [[s["id"], ", ".join(s.get("objectives") or []), s.get("sampler") or "—", f"{(s.get('summary') or {}).get('trials_done', 0)} / {s.get('n_trials') or '—'}"] for s in data],
        [f"study:{node.simulation_id}/{s['id']}" for s in data],
    )
    table.on_activate(actions.select_key)
    page.section("Studies", table)
    if not data:
        page.note("No tuning studies yet.")
    return page


def _build_study(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    summary = data.get("summary") or {}
    config = data.get("config") or {}
    if data.get("running_job_id"):
        page.add(InlineMessage("info", "This study is running."))
    page.section("Study", PropertyTable([
        ("Objectives", ", ".join(config.get("objectives") or []), ""),
        ("Aggregation", str(config.get("aggregation", "—")), ""),
        ("Sampler", str(config.get("sampler", "—")), ""),
        ("Trials completed", fmt(summary.get("trials_done")), ""),
        ("Trial budget", fmt(config.get("n_trials")), ""),
        ("Free parameters", ", ".join(data.get("free_parameters") or []) or "—", ""),
        ("State", str(summary.get("state", "—")), ""),
    ]))
    trials = data.get("trials") or []
    objectives = config.get("objectives") or []
    table = DataTable(["Trial", "Status"] + objectives, numeric=set(range(2, 2 + len(objectives))) | {0})
    table.set_rows([[t.get("number"), t.get("status", "—")] + [fmt((t.get("values") or {}).get(o), 4) for o in objectives] for t in trials])
    page.section("Trials", table)
    return page


def _kpi_rows(kpi: dict[str, Any]) -> list[tuple[str, str, str]]:
    def pct(value):
        return fmt(100 * value, 1) if value is not None else "—"

    return [
        ("Dimension (n)", fmt(kpi.get("n")), ""),
        ("Nonzeros", fmt(kpi.get("nnz_original")), ""),
        ("Bandwidth, original", fmt(kpi.get("bandwidth_original")), ""),
        ("Bandwidth, permuted", fmt(kpi.get("bandwidth_permuted")), ""),
        ("Bandwidth reduction", fmt(kpi.get("bandwidth_reduction_pct"), 1), "%"),
        ("Average bandwidth, original", fmt(kpi.get("avg_bandwidth_original"), 1), ""),
        ("Average bandwidth, permuted", fmt(kpi.get("avg_bandwidth_permuted"), 1), ""),
        ("Nonzeros within 1 % of the diagonal, original", pct(kpi.get("frac_1_0pct_original")), "%"),
        ("Nonzeros within 1 % of the diagonal, permuted", pct(kpi.get("frac_1_0pct_permuted")), "%"),
    ]


MAX_COMPARED_RUNS = 5


def _build_results(node: Node, data: list[dict], actions: PageActions) -> Page:
    page = Page()
    table = DataTable(["Run", "Method", "k", "Bandwidth reduction (%)"], numeric={2, 3}, multi_select=True)
    table.set_rows(
        [[r["run_id"], method_label(r.get("partitioning_strategy"), r.get("simulated"), short=True) if r.get("partitioning_strategy") != "unknown" else "—",
          r.get("k_target"), fmt((r.get("kpi_summary") or {}).get("bandwidth_reduction_pct"), 1)] for r in data],
        [r["result_dir"] for r in data],
    )
    table.on_activate(lambda result_dir: actions.select_key(f"run:{result_dir}"))
    page.section("Runs", table)
    if not data:
        page.note("No runs yet. Select the simulation and press Run.")
        return page
    compare = _button("Compare selected", lambda: actions.compare_runs(table.selected_data()[:MAX_COMPARED_RUNS]), icon="compare")
    hint = QLabel(f"Select up to {MAX_COMPARED_RUNS} runs (Ctrl+click) to overlay their locality curves.")
    hint.setProperty("role", "muted")
    hint.setWordWrap(True)

    def update() -> None:
        count = len(table.selected_data())
        compare.setEnabled(count >= 1)
        compare.setText(f"Compare {min(count, MAX_COMPARED_RUNS)} selected" if count > 1 else "Compare selected")

    table.itemSelectionChanged.connect(update)
    update()
    page.add(hint)
    page.add(_buttons(compare))
    return page


def build_comparison_table(details: list[dict], labels: list[str]) -> DataTable:
    """KPIs of several runs side by side."""
    rows = []
    metrics = [
        ("Bandwidth, permuted", "bandwidth_permuted", 0),
        ("Bandwidth reduction (%)", "bandwidth_reduction_pct", 1),
        ("Average bandwidth, permuted", "avg_bandwidth_permuted", 1),
        ("Within 1 % of the diagonal (%)", "frac_1_0pct_permuted", 1),
    ]
    for label, key, decimals in metrics:
        row = [label]
        for d in details:
            value = (d.get("kpi_summary") or {}).get(key)
            if key.startswith("frac_") and value is not None:
                value *= 100
            row.append(fmt(value, decimals))
        rows.append(row)
    return DataTable(["Metric"] + labels, rows, numeric=set(range(1, len(labels) + 1)), stretch=0)


def _build_run(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    kpi = data.get("kpi_summary")
    check = (kpi or {}).get("permutation_check") or {}
    if kpi is None:
        page.add(InlineMessage("warning", "This run has no metrics. It may have failed, or run metrics were not saved."))
    elif check and not all(bool(v) for v in check.values() if isinstance(v, bool)):
        page.add(InlineMessage("error", "The permutation check failed for this run."))
    params = data.get("run_parameters") or {}
    pp = params.get("partitioning_parameters") or {}
    strategy = pp.get("partitioning_strategy")
    page.section("Run", PropertyTable([
        ("Method", method_label(strategy, (pp.get("strategies") or {}).get(strategy, {}).get("simulated")) if strategy else "Not recorded", ""),
        ("Number of parts (k)", fmt((pp.get("common") or {}).get("k_target")), ""),
        ("Folder", data["result_dir"], ""),
    ]))
    if kpi:
        page.section("Matrix structure", PropertyTable(_kpi_rows(kpi)))
    page.add(_buttons(
        _button("Open folder", lambda: actions.open_path(data["result_dir"]), icon="folder"),
        _button("Export bundle…", lambda: actions.export_run(data["result_dir"]), icon="export"),
    ))
    return page


def _build_batch(node: Node, data: list[dict], actions: PageActions) -> Page:
    return _build_batch_runs(node, data, actions)


def _build_batch_config(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    totals = data["plan"]["totals"]
    rows = [("Cases", fmt(data["case_count"]), ""), ("Asynchronous cases", fmt(totals["async_count"]), "")]
    if totals["estimated"]:
        rows.append(("Estimated duration", fmt(totals["seconds"] / 60, 1), "min"))
    if totals["submissions"]:
        rows.append(("QPU submissions", fmt(totals["submissions"]), ""))
    page.section("Plan", PropertyTable(rows))
    if totals["over_capacity"]:
        page.add(InlineMessage("warning", f"{totals['over_capacity']} cases ask for a coarse graph larger than their backend accepts."))
    table = DataTable(["Case", "Method", "Scale", "Est. (s)"], numeric={3})
    table.set_rows([[c["case_key"], method_label(c["partitioning_strategy"], (c.get("strategy_parameters") or {}).get("simulated"), short=True),
                     c["coarsening_size"], fmt((c.get("estimate") or {}).get("seconds"), 0)] for c in data["plan"]["cases"]])
    page.section("Cases", table)
    page.note(READ_ONLY_NOTE)
    return page


def _build_batch_runs(node: Node, data: list[dict], actions: PageActions) -> Page:
    page = Page()
    table = DataTable(["Batch", "Cases", "Completed", "Failed"], numeric={1, 2, 3})
    table.set_rows([[b["id"], b["total_cases"], b["completed_cases"], b["failed_cases"]] for b in data], [f"batch_run:{b['id']}" for b in data])
    table.on_activate(actions.select_key)
    page.section("Batch runs", table)
    return page


def _build_batch_run(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    manifest = data.get("manifest") or {}
    rows = data.get("summary_rows") or manifest.get("cases") or []
    failed = [r for r in rows if r.get("status") == "failed"]
    if failed:
        page.add(InlineMessage("error", f"{len(failed)} of {len(rows)} cases failed."))
    page.section("Batch", PropertyTable([
        ("Started", str(manifest.get("batch_started_at") or "—"), ""),
        ("Finished", str(manifest.get("batch_finished_at") or "—"), ""),
        ("Cases", fmt(len(rows)), ""),
        ("Completed", fmt(sum(1 for r in rows if r.get("status") == "completed")), ""),
    ]))

    analysis = data.get("analysis") or {}
    matrices = analysis.get("available_demonstrators") or []
    if matrices:
        matrix_box, scale_box = QComboBox(), QComboBox()
        matrix_box.addItems(matrices)
        scales = [s for s in ("small", "medium", "big") if any(r.get("coarsening_size") == s for r in rows)] or ["big"]
        scale_box.addItems(scales)
        from .widgets import FormGrid

        form = FormGrid()
        form.add_row("Matrix", matrix_box)
        form.add_row("Coarsening scale", scale_box)
        summary = DataTable(["Method", "Scale", "Bandwidth, permuted", "Within 1 % (%)"], numeric={2, 3}, stretch=0)

        def refresh() -> None:
            matrix = matrix_box.currentText()
            completed = [r for r in rows if r.get("status") == "completed" and r.get("geometry") == matrix]
            summary.set_rows([
                [method_label(r.get("algorithm"), short=True), r.get("coarsening_size", "—"), r.get("bandwidth_permuted"),
                 fmt(100 * r["frac_1_0pct_permuted"], 1) if r.get("frac_1_0pct_permuted") is not None else "—"]
                for r in completed
            ])
            actions.show_batch(data["id"], matrix, scale_box.currentText())

        matrix_box.currentIndexChanged.connect(lambda _i: refresh())
        scale_box.currentIndexChanged.connect(lambda _i: refresh())
        page.section("Analysis", form, summary)
        refresh()

    table = DataTable(["Case", "Status"], max_visible_rows=10)
    table.set_rows([[r.get("case_key", "—"), r.get("status", "—")] for r in rows])
    page.section("Cases", table, expanded=not matrices)
    page.add(_buttons(_button("Open folder", lambda: actions.open_path(f"batch/runs/{data['id']}"), icon="folder")))
    return page


def _build_hardware(node: Node, data: dict, actions: PageActions) -> Page:
    page = Page()
    labels = {"ready": "Ready", "configured": "Configured", "needs_credentials": "Needs credentials", "missing_sdk": "SDK missing"}
    table = DataTable(["Backend", "Status"])
    table.set_rows([[b["label"], labels.get(b["status"], b["status"])] for b in data["backends"].values()])
    page.section("Partitioning backends", table)
    packages = DataTable(["Package", "Version", "Used for"], stretch=2)
    packages.set_rows([[p["name"], p["version"] or "not installed", p["purpose"]] for p in data["package_versions"]])
    page.section("Packages", packages, expanded=False)
    page.note("Probing a remote QPU arrives in a later version.")
    return page


BUILDERS: dict[str, Callable[[Node, Any, PageActions], Page]] = {
    "matrices": _build_matrices,
    "matrix": _build_matrix,
    "simulations": _build_simulations,
    "simulation": _build_simulation,
    "input": _build_input,
    "coarsening": _stage_page("coarsening_parameters", "Coarsening"),
    "partitioning": _build_partitioning,
    "refinement": _stage_page("uncoarsening_parameters", "Refinement"),
    "outputs": _build_outputs,
    "presets": _build_presets,
    "preset": _build_preset,
    "tuning": _build_tuning,
    "study": _build_study,
    "results": _build_results,
    "run": _build_run,
    "batch": _build_batch,
    "batch_config": _build_batch_config,
    "batch_runs": _build_batch_runs,
    "batch_run": _build_batch_run,
    "hardware": _build_hardware,
}
