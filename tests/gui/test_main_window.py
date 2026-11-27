"""The desktop window on a real (temporary) workspace."""

import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from hdd.studio.main_window import MainWindow
from libs.runtime import workspace
from libs.runtime.utils import AVAILABLE_SAVE_OUTPUTS
from tests.test_workspace import make_workspace


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("HDD_DISABLE_HISTORY", "1")
    root = make_workspace(tmp_path / "ws")
    config_path = root / "simulations/sim_a/data/simulation_config.json"
    config = json.loads(config_path.read_text())
    config["save_output"] = sorted(AVAILABLE_SAVE_OUTPUTS)
    config_path.write_text(json.dumps(config))
    yield root
    monkeypatch.delenv(workspace.ENV_VAR, raising=False)


@pytest.fixture()
def window(qtbot, theme, settings, root):
    win = MainWindow(theme, settings, root)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: win.snapshot is not None, timeout=10000)
    yield win
    win.ctx.jobs.cancel_all()
    win.ctx.close()


def tree_labels(window) -> list[str]:
    return [i.data(Qt.ItemDataRole.DisplayRole) for i in window.project._walk()]


def test_window_layout_and_menus(window):
    names = {dock.objectName() for dock in window.docks}
    assert names == {"ProjectDock", "SettingsDock", "ConsoleDock", "JobsDock", "ProblemsDock", "HelpDock"}
    assert not window.help_dock.isVisible()
    assert window.dockWidgetArea(window.project_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.dockWidgetArea(window.console_dock) == Qt.DockWidgetArea.BottomDockWidgetArea
    menus = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert menus == ["File", "Edit", "Simulation", "Batch", "Tuning", "View", "Help"]
    assert window.windowTitle().startswith("ws")
    assert not window.isWindowModified()


def test_tree_shows_the_workspace(window):
    labels = tree_labels(window)
    for expected in ("Matrices", "grid", "Simulations", "sim_a", "Coarsening", "Results", "Batch", "Quantum hardware"):
        assert expected in labels


def test_selecting_nodes_loads_pages_and_plots(qtbot, window):
    assert window.select_node("coarsening")
    qtbot.waitUntil(lambda: window.settings_panel.title.text() == "Coarsening")
    assert window.select_node("matrix")
    qtbot.waitUntil(lambda: window.graphics.sparsity.data() is not None, timeout=10000)
    assert window.graphics.sparsity.data().n == 600


def test_run_a_simulation_from_the_window(qtbot, window, root):
    window.select_node("simulation")
    assert window.act_run.isEnabled()
    window.run_selected()
    job_id = window.console.job_id
    assert job_id is not None
    qtbot.waitUntil(lambda: window.ctx.jobs.get_job(job_id)["status"] != "running", timeout=120000)
    assert window.ctx.jobs.get_job(job_id)["status"] == "completed"
    qtbot.waitUntil(lambda: "Simulation Completed Successfully" in window.console_panel.view.visible_text(), timeout=5000)
    qtbot.waitUntil(lambda: any("METIS" in label for label in tree_labels(window)), timeout=10000)
    assert window.jobs.model.rowCount() == 1
    # The new run can be opened, with its plots.
    assert window.select_node("run")
    qtbot.waitUntil(lambda: window.graphics.sparsity.data() is not None, timeout=20000)
    assert window.graphics.tabs.count() == 2


def test_stop_cancels_the_followed_job(qtbot, window, monkeypatch):
    import sys

    sleeper = Path(window.ctx.root) / "sleep.py"
    sleeper.write_text("import time\nprint('[10:00:00 INFO] Coarsening Heavy Edge Matching', flush=True)\ntime.sleep(60)\n")
    monkeypatch.setattr(window.ctx.jobs, "_command", lambda kind, args: [sys.executable, "-u", str(sleeper)])
    window.select_node("simulation")
    window.run_selected()
    job_id = window.console.job_id
    qtbot.waitUntil(lambda: window.act_stop.isEnabled(), timeout=5000)
    window.stop_job()
    qtbot.waitUntil(lambda: window.ctx.jobs.get_job(job_id)["status"] == "cancelled", timeout=5000)
    qtbot.waitUntil(lambda: not window.act_stop.isEnabled(), timeout=5000)


def test_closing_with_a_running_job_asks_first(qtbot, window, monkeypatch):
    import sys

    sleeper = Path(window.ctx.root) / "sleep.py"
    sleeper.write_text("import time\ntime.sleep(60)\n")
    monkeypatch.setattr(window.ctx.jobs, "_command", lambda kind, args: [sys.executable, "-u", str(sleeper)])
    window.run_simulation("sim_a")
    monkeypatch.setattr(window, "_confirm_stop_jobs", lambda what: None)
    window.close()
    assert window.isVisible()
    monkeypatch.setattr(window, "_confirm_stop_jobs", lambda what: "stop")
    window.close()
    assert not window.isVisible()
    assert window.ctx.jobs.running_jobs() == []


def test_jobs_can_keep_running_after_the_window_closes(qtbot, theme, settings, root, monkeypatch):
    import sys

    from hdd.services.jobs import JobManager

    win = MainWindow(theme, settings, root)
    qtbot.waitUntil(lambda: win.snapshot is not None, timeout=10000)
    sleeper = Path(root) / "sleep.py"
    sleeper.write_text("import time\nprint('[10:00:00 INFO] working', flush=True)\ntime.sleep(60)\n")
    monkeypatch.setattr(win.ctx.jobs, "_command", lambda kind, args: [sys.executable, "-u", str(sleeper)])
    win.run_simulation("sim_a")
    job_id = win.console.job_id
    monkeypatch.setattr(win, "_confirm_stop_jobs", lambda what: "keep")
    win.close()
    reopened = JobManager(root)
    try:
        assert reopened.get_job(job_id)["status"] == "running"
    finally:
        reopened.cancel_all()


def test_generate_matrix_dialog_links_nonzeros_and_density(qtbot, theme):
    from PySide6.QtWidgets import QDialogButtonBox

    from hdd.studio.dialogs import GenerateMatrixDialog

    dialog = GenerateMatrixDialog()
    qtbot.addWidget(dialog)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    dialog.size.setValue(1000)
    dialog.nonzeros.setValue(10000)
    assert abs(dialog.density.value() - 1.0) < 1e-9
    dialog.density.setValue(2.0)
    assert dialog.nonzeros.value() == 20000
    dialog.size.setValue(2000)  # density was set last, so it is kept
    assert dialog.nonzeros.value() == 80000
    dialog.nonzeros.setValue(1500)  # fewer than the diagonal
    assert not ok.isEnabled()
    dialog.nonzeros.setValue(2001)
    assert ok.isEnabled()
    dialog.symmetry.setCurrentIndex(dialog.symmetry.findData("symmetric"))
    assert "2,000 will be stored" in dialog.summary.text()
    assert dialog.values() == {"kind": "random", "name": "random_matrix", "n": 2000, "nonzeros": 2001,
                               "symmetry": "symmetric", "seed": 42}
    dialog.kind.button(GenerateMatrixDialog.FEM).click()
    assert dialog.values()["kind"] == "fem" and dialog.values()["name"] == "demo_fem"
    assert dialog.size.isHidden() and not dialog.fem_dof.isHidden()


def test_generating_a_random_matrix_adds_it_to_the_library(qtbot, window, monkeypatch, root):
    from hdd.studio import dialogs

    monkeypatch.setattr(dialogs.GenerateMatrixDialog, "exec", lambda self: self.DialogCode.Accepted)
    monkeypatch.setattr(dialogs.GenerateMatrixDialog, "values", lambda self: {
        "kind": "random", "name": "rnd", "n": 300, "nonzeros": 3000, "symmetry": "unsymmetric", "seed": 5})
    window.generate_demo_matrix()
    qtbot.waitUntil(lambda: "rnd" in tree_labels(window), timeout=20000)
    assert (root / "matrices" / "rnd" / "matrix.mtx").is_file()


def test_batch_planning_runs_off_the_gui_thread(qtbot, window, monkeypatch):
    import threading

    from hdd.services import batch

    planned_on = []

    def plan(config, estimates=None):
        planned_on.append(threading.current_thread())
        return {"totals": {"estimated": False, "seconds": 0, "submissions": 0, "over_capacity": 0}}

    asked = []
    monkeypatch.setattr(batch, "load_configuration", lambda: {"configuration": {}, "case_count": 3})
    monkeypatch.setattr(batch, "duration_estimates", lambda: {})
    monkeypatch.setattr(batch, "plan", plan)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No)
    window.run_batch()
    qtbot.waitUntil(lambda: bool(asked), timeout=10000)
    assert planned_on[0] is not threading.main_thread()
    assert "3 cases will run." in asked[0]


def test_import_matrix_and_switch_workspace(qtbot, window, tmp_path, monkeypatch):
    from hdd.services import matrices

    source = next((window.ctx.root / "matrices" / "grid").glob("*.mtx"))
    matrices.import_matrix("copy", source)
    window.reload()
    qtbot.waitUntil(lambda: "copy" in tree_labels(window), timeout=5000)

    other = workspace.init(tmp_path / "other")
    assert window.open_workspace(other)
    qtbot.waitUntil(lambda: "sim_a" not in tree_labels(window), timeout=5000)
    assert window.ctx.root == other.resolve()
    assert os.environ[workspace.ENV_VAR] == str(other.resolve())
    assert str(other.resolve()) in window._settings.recent_workspaces()


def test_layout_survives_a_restart(qtbot, theme, settings, root):
    first = MainWindow(theme, settings, root)
    qtbot.addWidget(first)
    first.show()
    first.jobs_dock.setFloating(True)
    first.problems_dock.close()
    first.close()
    second = MainWindow(theme, settings, root)
    qtbot.addWidget(second)
    second.show()
    assert second.jobs_dock.isFloating()
    assert not second.problems_dock.isVisible()
    second.reset_layout()
    qtbot.wait(20)
    assert not second.jobs_dock.isFloating()
    second.ctx.close()


def test_theme_choice_is_remembered(window, theme, settings):
    window.set_theme("dark")
    assert theme.tokens.is_dark
    assert settings.theme_mode() == "dark"


def test_toolbar_toggles_light_and_dark(window, theme, settings):
    window.set_theme("light")
    window.act_toggle_theme.trigger()
    assert theme.tokens.is_dark and settings.theme_mode() == "dark"
    assert "light" in window.act_toggle_theme.toolTip()
    window.act_toggle_theme.trigger()
    assert not theme.tokens.is_dark and settings.theme_mode() == "light"
    assert window.act_toggle_theme in window.toolbar.actions()
