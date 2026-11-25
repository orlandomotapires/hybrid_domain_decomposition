"""Batch configuration editing, tuning studies, hardware probes and contextual help in the desktop app."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QPushButton, QTableWidget

from hdd.services import hardware, tuning, wiki
from hdd.studio.dialogs import NewStudyDialog
from hdd.studio.main_window import MainWindow
from libs.runtime import workspace
from tests.test_workspace import make_workspace

BATCH = {
    "matrices": [{"key": "grid"}],
    "coarsening_presets": [
        {"key": "medium", "coarsen_inferior_limit": 20, "coarsen_superior_limit": 40},
        {"key": "small", "coarsen_inferior_limit": 4, "coarsen_superior_limit": 10},
    ],
    "algorithm_presets": [
        {"key": "metis", "partitioning_strategy": "metis_partitioning", "allowed_sizes": ["medium", "small"], "strategy_parameters": {}},
        {"key": "qa_emulated", "partitioning_strategy": "quantum_annealing", "allowed_sizes": ["small"],
         "strategy_parameters": {"simulated": True, "num_reads": 5, "num_starts": 2}},
    ],
    "common_defaults": {"general_parameters": {"seed": 42}, "partitioning_common": {"k_target": 4, "balance_tolerance": 2},
                        "coarsening_parameters": {"coarsen_ratio": 0.9, "max_levels": 20, "strategy": "modified"}},
    "async_remote_case_keys": [],
}


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("HDD_DISABLE_HISTORY", "1")
    root = make_workspace(tmp_path / "ws")
    (root / "batch").mkdir(exist_ok=True)
    (root / "batch" / "batch_configuration.json").write_text(json.dumps(BATCH))
    workspace.set_root(root)
    return root


@pytest.fixture()
def window(qtbot, theme, settings, root):
    win = MainWindow(theme, settings, root)
    win.show()
    qtbot.waitUntil(lambda: win.snapshot is not None, timeout=10000)
    yield win
    win.ctx.jobs.cancel_all()
    for doc in win.docs.values():
        doc.revert()
    if win.batch_doc is not None:
        win.batch_doc.revert()
    win.close()
    win.deleteLater()


def table_with_header(page, text: str) -> QTableWidget:
    return next(t for t in page.findChildren(QTableWidget) if t.horizontalHeaderItem(0) and t.horizontalHeaderItem(0).text() == text)


def button(page, text: str) -> QPushButton:
    return next(b for b in page.findChildren(QPushButton) if b.text() == text)


def open_batch_config(qtbot, window):
    window.select_key("batch_config")
    qtbot.waitUntil(lambda: window.batch_doc is not None and len(window.settings_panel.page().findChildren(QTableWidget)) >= 3, timeout=10000)
    return window.settings_panel.page()


# ------------------------------------------------------------------ batch
def test_batch_configuration_edit_undo_and_save(qtbot, window, root):
    page = open_batch_config(qtbot, window)
    doc = window.batch_doc
    assert len(doc.plan()["cases"]) == 3
    grid = table_with_header(page, "Method")
    small_qa = grid.item(1, 1)  # qa_emulated × medium scale: not in the plan yet
    assert small_qa.checkState() == Qt.CheckState.Unchecked
    small_qa.setCheckState(Qt.CheckState.Checked)
    assert len(doc.plan()["cases"]) == 4
    assert window.isWindowModified() and window.act_save.isEnabled()

    window.act_undo.trigger()
    assert len(doc.plan()["cases"]) == 3
    assert table_with_header(page, "Method").item(1, 1).checkState() == Qt.CheckState.Unchecked
    window.act_redo.trigger()

    window.act_save.trigger()
    saved = json.loads((root / "batch" / "batch_configuration.json").read_text())
    assert next(a for a in saved["algorithm_presets"] if a["key"] == "qa_emulated")["allowed_sizes"] == ["medium", "small"]
    assert not doc.is_dirty() and not window.isWindowModified()


def test_batch_configuration_refuses_an_empty_plan(qtbot, window, root, monkeypatch):
    page = open_batch_config(qtbot, window)
    matrices = table_with_header(page, "Matrix")
    matrices.item(0, 0).setCheckState(Qt.CheckState.Unchecked)
    assert "Choose at least one matrix." in window.batch_doc.problems()
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))
    assert window.save_batch() is False
    assert warned
    assert json.loads((root / "batch" / "batch_configuration.json").read_text())["matrices"] == [{"key": "grid"}]


# ----------------------------------------------------------------- tuning
def test_create_open_and_delete_a_study(qtbot, window, root, monkeypatch):
    dialog = NewStudyDialog(tuning.meta(), tuning.study_defaults("sim_a"), window)
    request = dialog.request()
    assert request["objectives"] == ["edge_cut", "imbalance"]
    result = window.create_study("sim_a", request, start=False)
    study_id = result["study"]["id"]
    qtbot.waitUntil(lambda: window.project.current_node() is not None and window.project.current_node().kind == "study", timeout=10000)
    qtbot.waitUntil(lambda: window.settings_panel.title.text() == study_id
                    and any(b.text() == "Apply best parameters" for b in window.settings_panel.page().findChildren(QPushButton)), timeout=10000)
    assert not button(window.settings_panel.page(), "Apply best parameters").isEnabled()
    from hdd.studio.widgets import PropertyTable

    values = {t.item(r, 0).text(): t.item(r, 1).text() for t in window.settings_panel.page().findChildren(PropertyTable) for r in range(t.rowCount())}
    assert values["Objectives"] == "Edge cut, Imbalance"

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.study_action("sim_a", study_id, "delete")
    assert not (root / "simulations" / "sim_a" / "tuning" / study_id).exists()


def test_new_study_dialog_rejects_bad_ranges(qtbot, window):
    dialog = NewStudyDialog(tuning.meta(), tuning.study_defaults("sim_a"), window)
    for box in dialog.objectives.values():
        box.setChecked(False)
    with pytest.raises(ValueError, match="objective"):
        dialog.request()


# --------------------------------------------------------------- hardware
def test_hardware_probe_runs_in_the_background(qtbot, window, monkeypatch):
    monkeypatch.setattr(hardware, "probe_dwave", lambda solver, region: {"largest_clique_capacity": 177, "reachable": True, "solver_name": solver})
    window.select_key("hardware")
    qtbot.waitUntil(lambda: window.settings_panel.title.text() == "Quantum hardware"
                    and any(b.text() == "Probe" for b in window.settings_panel.page().findChildren(QPushButton)), timeout=10000)
    page = window.settings_panel.page()
    next(b for b in page.findChildren(QPushButton) if b.text() == "Probe").click()
    qtbot.waitUntil(lambda: "177 variables" in " ".join(label.text() for label in page.findChildren(type(window.status_job))), timeout=10000)


# ------------------------------------------------------------------- help
def test_f1_documents_the_focused_parameter(qtbot, window):
    window.select_key("coarsening:sim_a")
    qtbot.waitUntil(lambda: hasattr(window.settings_panel.page(), "forms") and "sim_a" in window.docs, timeout=10000)
    page = window.settings_panel.page()
    key = "coarsening_parameters.coarsen_inferior_limit"
    assert page.focus(key)
    window.act_help.trigger()
    assert window.help_dock.isVisible()
    assert window.help.current_topic()["id"] == wiki.topic_for_parameter(key)["id"]


def test_f1_without_a_parameter_documents_the_selected_item(qtbot, window):
    window.select_key("hardware")
    qtbot.waitUntil(lambda: window.settings_panel.title.text() == "Quantum hardware", timeout=10000)
    window.setFocus()
    window.act_help.trigger()
    assert window.help.current_topic()["id"] == "hardware-backends"
