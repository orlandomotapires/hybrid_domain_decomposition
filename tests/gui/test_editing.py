"""Editing a simulation: document model, forms, save/revert, presets and running with unsaved changes."""

import json

import pytest
from PySide6.QtWidgets import QMessageBox, QSpinBox

from hdd.services import catalog, simulations
from hdd.studio.documents import SimulationDocument
from hdd.studio.main_window import MainWindow
from libs.runtime import workspace
from tests.test_workspace import make_workspace

SPEC = {s.key: s for s in catalog.ALL_SPECS}
LOWER, UPPER = SPEC["coarsening_parameters.coarsen_inferior_limit"], SPEC["coarsening_parameters.coarsen_superior_limit"]
K = SPEC["partitioning_parameters.common.k_target"]
METHOD = SPEC["partitioning_parameters.partitioning_strategy"]
QAOA_SIM = SPEC["partitioning_parameters.strategies.quantum_approximation_optimizer.simulated"]
QAOA_QPU = SPEC["partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_qpu_name"]


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("HDD_DISABLE_HISTORY", "1")
    root = make_workspace(tmp_path / "ws")
    workspace.set_root(root)
    yield root
    monkeypatch.delenv(workspace.ENV_VAR, raising=False)


@pytest.fixture()
def doc(qapp, theme, root):
    document = SimulationDocument(simulations.get_simulation("sim_a"))
    yield document
    document.deleteLater()


def saved_params(root):
    return json.loads((root / "simulations/sim_a/data/simulation_parameters.json").read_text())


# ------------------------------------------------------------------ document
def test_edit_undo_redo_and_dirty_state(doc):
    assert not doc.is_dirty()
    doc.set_value(K, 6)
    assert doc.is_dirty() and doc.value(K) == 6
    doc.undo.undo()
    assert not doc.is_dirty() and doc.value(K) == 4
    doc.undo.redo()
    assert doc.value(K) == 6


def test_consecutive_edits_of_one_field_undo_together(doc):
    for value in (5, 6, 7):
        doc.set_value(K, value)
    doc.set_value(LOWER, 30)
    assert doc.undo.count() == 2
    doc.undo.undo()
    doc.undo.undo()
    assert doc.value(K) == 4


def test_validation_points_at_the_field(qtbot, doc):
    doc.set_value(UPPER, 10)  # below the lower limit (40)
    qtbot.waitUntil(lambda: bool(doc.errors()))
    issue = doc.errors()[0]
    assert issue.key == UPPER.key
    assert "Upper limit" in issue.message and "coarsening_parameters" not in issue.message


def test_backend_capacity_is_checked(qtbot, doc):
    doc.set_value(METHOD, "quantum_approximation_optimizer")
    qtbot.waitUntil(lambda: any(i.key == UPPER.key for i in doc.errors()))
    assert "18" in doc.issue_for(UPPER.key).message
    doc.set_value(UPPER, 18)
    doc.set_value(LOWER, 10)
    qtbot.waitUntil(lambda: not doc.errors())


def test_hardware_qaoa_needs_a_qpu_name(qtbot, doc):
    doc.set_value(METHOD, "quantum_approximation_optimizer")
    doc.set_value(UPPER, 10)
    doc.set_value(LOWER, 8)
    doc.set_value(QAOA_SIM, False)
    qtbot.waitUntil(lambda: doc.issue_for(QAOA_QPU.key) is not None or doc.issue_for(UPPER.key) is not None)
    doc.set_value(QAOA_QPU, "qat.qpus:QSolidQPU10")
    qtbot.waitUntil(lambda: not doc.errors())


def test_save_writes_the_active_preset_and_keeps_other_strategies(doc, root):
    before = saved_params(root)
    doc.set_value(K, 3)
    doc.save()
    after = saved_params(root)
    assert after["partitioning_parameters"]["common"]["k_target"] == 3
    assert not doc.is_dirty()
    assert set(before["partitioning_parameters"]["strategies"]) <= set(after["partitioning_parameters"]["strategies"])


def test_revert_restores_the_saved_values(doc):
    doc.set_value(K, 9)
    doc.revert()
    assert doc.value(K) == 4 and not doc.is_dirty()


def test_load_parameters_is_one_undo_step(doc):
    other = json.loads(json.dumps(doc.params))
    other["partitioning_parameters"]["common"]["k_target"] = 2
    other["coarsening_parameters"]["coarsen_inferior_limit"] = 20
    doc.load_parameters(other, "Load preset")
    assert doc.value(K) == 2 and doc.value(LOWER) == 20
    doc.undo.undo()
    assert doc.value(K) == 4 and doc.value(LOWER) == 40


def test_external_changes_reload_only_a_clean_document(doc, root):
    params = saved_params(root)
    params["partitioning_parameters"]["common"]["k_target"] = 5
    simulations.save_parameters("sim_a", params)
    assert doc.reload_from(simulations.get_simulation("sim_a"))
    assert doc.value(K) == 5
    doc.set_value(K, 7)
    params["partitioning_parameters"]["common"]["k_target"] = 2
    simulations.save_parameters("sim_a", params)
    assert not doc.reload_from(simulations.get_simulation("sim_a"))
    assert doc.value(K) == 7


def test_diff_ignores_unused_strategy_blocks(doc):
    other = json.loads(json.dumps(doc.params))
    other["partitioning_parameters"]["strategies"]["quantum_annealing"] = {"num_reads": 99}
    other["coarsening_parameters"]["max_levels"] = 3
    assert [key for key, _a, _b in catalog.diff(doc.params, other)] == ["coarsening_parameters.max_levels"]


# -------------------------------------------------------------------- window
@pytest.fixture()
def window(qtbot, theme, settings, root):
    # Not handed to qtbot: it would close the window before this fixture discards the edits,
    # and the unsaved-changes prompt would block the test run.
    win = MainWindow(theme, settings, root)
    win.show()
    qtbot.waitUntil(lambda: win.snapshot is not None, timeout=10000)
    yield win
    win.ctx.jobs.cancel_all()
    for doc in win.docs.values():
        doc.revert()
    win.close()
    win.deleteLater()


def open_stage(qtbot, window, kind):
    assert window.select_node(kind)
    qtbot.waitUntil(lambda: hasattr(window.settings_panel.page(), "forms") and "sim_a" in window.docs, timeout=10000)
    return window.docs["sim_a"], window.settings_panel.page()


def test_form_edits_reach_the_document_and_back(qtbot, window):
    doc, page = open_stage(qtbot, window, "coarsening")
    box = page.forms[0].editors[LOWER.key].input
    assert isinstance(box, QSpinBox) and box.value() == 40
    box.setValue(30)
    assert doc.value(LOWER) == 30
    assert window.isWindowModified() and window.settings_panel.dirty.isVisible()
    window.act_undo.trigger()
    assert box.value() == 40 and doc.value(LOWER) == 40


def test_errors_show_inline_and_in_problems_and_block_saving(qtbot, window, monkeypatch, root):
    doc, page = open_stage(qtbot, window, "coarsening")
    page.forms[0].editors[UPPER.key].input.setValue(10)
    qtbot.waitUntil(lambda: bool(doc.errors()))
    grid = page.forms[0].grid
    row = page.forms[0]._rows[UPPER.key]
    assert grid._rows[row][1].isVisibleTo(page) and "Upper limit" in grid._rows[row][1].text()
    qtbot.waitUntil(lambda: window.problems.rowCount() >= 1)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))
    assert not window.save_simulation("sim_a")
    assert warned and saved_params(root)["coarsening_parameters"]["coarsen_superior_limit"] == 120


def test_problem_row_navigates_to_the_field(qtbot, window):
    doc, _page = open_stage(qtbot, window, "simulation")
    doc.set_value(UPPER, 10)
    qtbot.waitUntil(lambda: any(t and t[2] == UPPER.key for t in window._problem_targets))
    row = next(i for i, t in enumerate(window._problem_targets) if t and t[2] == UPPER.key)
    window._go_to_problem(row)
    qtbot.waitUntil(lambda: window.settings_panel.title.text() == "Coarsening", timeout=5000)


def test_save_from_the_window(qtbot, window, root):
    doc, page = open_stage(qtbot, window, "coarsening")
    page.forms[0].editors[LOWER.key].input.setValue(25)
    window.act_save.trigger()
    assert saved_params(root)["coarsening_parameters"]["coarsen_inferior_limit"] == 25
    assert not window.isWindowModified()


def test_coarsening_preview_follows_edits(qtbot, window):
    doc, page = open_stage(qtbot, window, "coarsening")
    qtbot.waitUntil(lambda: window.graphics.current_view() == "trajectory", timeout=10000)
    first = window.graphics.trajectory.series()[0].values.copy()
    page.forms[0].editors[LOWER.key].input.setValue(10)
    page.forms[0].editors[UPPER.key].input.setValue(20)
    qtbot.waitUntil(lambda: len(window.graphics.trajectory.series()[0].values) != len(first), timeout=10000)


def test_presets_save_load_activate_delete(qtbot, window, monkeypatch, root):
    doc, _page = open_stage(qtbot, window, "simulation")
    doc.set_value(K, 2)
    monkeypatch.setattr("hdd.studio.main_window.QInputDialog.getText", lambda *a, **k: ("k2", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.save_as_preset("sim_a")
    assert (root / "simulations/sim_a/data/k2.json").is_file()
    doc.revert()
    window.load_preset("sim_a", "k2.json")
    assert doc.value(K) == 2 and doc.is_dirty()
    doc.revert()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.activate_preset("sim_a", "k2.json")
    assert doc.active_preset == "k2.json" and doc.value(K) == 2
    window.activate_preset("sim_a", "simulation_parameters.json")
    window.delete_preset("sim_a", "k2.json")
    assert not (root / "simulations/sim_a/data/k2.json").exists()


def test_compare_dialog_lists_differences(qtbot, window, monkeypatch):
    from hdd.studio import dialogs

    doc, _page = open_stage(qtbot, window, "simulation")
    doc.set_value(K, 7)
    seen = {}

    def fake_exec(self):
        seen["rows"] = self.differences()
        return 0

    monkeypatch.setattr(dialogs.CompareDialog, "exec", fake_exec)
    window.compare("sim_a", None)
    assert [row[0] for row in seen["rows"]] == ["partitioning_parameters.common.k_target"]


def test_run_with_unsaved_changes_can_save_first(qtbot, window, monkeypatch, root):
    doc, _page = open_stage(qtbot, window, "simulation")
    doc.set_value(K, 2)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: self.setProperty("clicked", True) or self.buttons()[0].click() or 0)
    started = []
    monkeypatch.setattr(window, "_started", lambda job: started.append(job))
    window.run_simulation("sim_a")
    assert started and saved_params(root)["partitioning_parameters"]["common"]["k_target"] == 2
    qtbot.waitUntil(lambda: window.ctx.jobs.get_job(started[0]["job_id"])["status"] != "running", timeout=120000)


def test_new_rename_and_delete_simulation(qtbot, window, monkeypatch, root):
    from hdd.studio import dialogs

    monkeypatch.setattr(dialogs.NewSimulationDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(dialogs.NewSimulationDialog, "values", lambda self: {"name": "fresh", "matrix": "grid", "clone_from": None})
    window.new_simulation()
    qtbot.waitUntil(lambda: (root / "simulations/fresh").is_dir(), timeout=20000)
    window.ctx.tasks.wait()
    qtbot.waitUntil(lambda: window.project.find_key("simulation:fresh").isValid(), timeout=10000)
    monkeypatch.setattr("hdd.studio.main_window.QInputDialog.getText", lambda *a, **k: ("renamed", True))
    window.rename_simulation("fresh")
    qtbot.waitUntil(lambda: (root / "simulations/renamed").is_dir())
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.delete_simulation("renamed")
    assert not (root / "simulations/renamed").exists()


def test_quitting_with_unsaved_changes_asks(qtbot, window, monkeypatch):
    doc, _page = open_stage(qtbot, window, "simulation")
    doc.set_value(K, 5)
    monkeypatch.setattr(window, "_confirm_unsaved", lambda what: False)
    window.close()
    assert window.isVisible()
    monkeypatch.undo()
