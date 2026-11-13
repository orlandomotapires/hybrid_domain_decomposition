"""Results in the desktop app: run comparison, batch analysis and plot export."""

import json

import pytest

from hdd.studio.main_window import MainWindow
from libs.runtime import workspace
from libs.runtime.runtime import run_simulation
from libs.runtime.utils import AVAILABLE_SAVE_OUTPUTS
from tests.test_workspace import make_workspace


@pytest.fixture(scope="module")
def populated(tmp_path_factory):
    """A workspace with two finished runs and a batch summary (built once: runs take seconds)."""
    root = make_workspace(tmp_path_factory.mktemp("results") / "ws")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("HDD_DISABLE_HISTORY", "1")
        mp.setenv(workspace.ENV_VAR, str(root))
        config_path = root / "simulations/sim_a/data/simulation_config.json"
        config = json.loads(config_path.read_text())
        config["save_output"] = sorted(AVAILABLE_SAVE_OUTPUTS)
        config_path.write_text(json.dumps(config))
        runs = [workspace.rel(run_simulation("simulations/sim_a")) for _ in range(2)]
    batch_dir = root / "batch" / "runs" / "batch_20260101_000000"
    batch_dir.mkdir(parents=True)
    rows = []
    for algorithm, permuted in (("metis", 0.04), ("qa_emulated", 0.05)):
        rows.append({"geometry": "grid", "case_key": f"grid__{algorithm}__big", "status": "completed", "algorithm": algorithm,
                     "coarsening_size": "big", "bandwidth_permuted": 100, "frac_0_1pct_original": 0.01, "frac_0_1pct_permuted": permuted / 4,
                     "frac_0_4pct_original": 0.01, "frac_0_4pct_permuted": permuted / 2, "frac_0_7pct_original": 0.02,
                     "frac_0_7pct_permuted": permuted, "frac_1_0pct_original": 0.02, "frac_1_0pct_permuted": permuted})
    (batch_dir / "batch_summary.json").write_text(json.dumps({"rows": rows}))
    (batch_dir / "batch_manifest.json").write_text(json.dumps({"cases": rows}))
    return root, runs


@pytest.fixture()
def window(qtbot, theme, settings, populated, monkeypatch):
    monkeypatch.setenv("HDD_DISABLE_HISTORY", "1")
    root, _runs = populated
    win = MainWindow(theme, settings, root)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: win.snapshot is not None, timeout=10000)
    yield win
    win.ctx.close()


def test_compare_two_runs(qtbot, window, populated):
    _root, runs = populated
    assert window.select_node("results")
    qtbot.waitUntil(lambda: hasattr(window.settings_panel.page(), "box") and window.settings_panel.title.text() == "Results", timeout=5000)
    window.compare_runs(runs)
    qtbot.waitUntil(lambda: window.graphics.current_view() == "curves" and len(window.graphics.curves.series()) == 3, timeout=10000)
    labels = [s.label for s in window.graphics.curves.series()]
    assert labels[-1] == "Original"
    qtbot.waitUntil(lambda: getattr(window.settings_panel.page(), "_comparison", None) is not None, timeout=5000)


def test_export_curves_and_figures(qtbot, window, populated, tmp_path):
    _root, runs = populated
    assert window.select_key(f"run:{runs[0]}") is None
    qtbot.waitUntil(lambda: window.graphics.sparsity.data() is not None, timeout=20000)
    figure = window.graphics.export("figure", str(tmp_path / "fig.png"))
    assert figure.read_bytes()[:4] == b"\x89PNG"
    png = window.graphics.export("png", str(tmp_path / "view.png"))
    assert png.stat().st_size > 1000
    svg = window.graphics.export("svg", str(tmp_path / "view.svg"))
    assert "<svg" in svg.read_text()[:500]
    window.graphics.tabs.setCurrentIndex(1)  # locality curve
    csv_file = window.graphics.export("csv", str(tmp_path / "curve.csv"))
    header, *lines = csv_file.read_text().splitlines()
    assert header.split(",")[1:] == ["Permuted", "Original"]
    assert len(lines) > 50


def test_batch_analysis_shows_methods_per_scale(qtbot, window):
    assert window.select_node("batch_run")
    qtbot.waitUntil(lambda: window.graphics.current_view() == "bands", timeout=10000)
    labels = [s.label for s in window.graphics.bands.series()]
    assert labels == ["METIS", "QA Emulated", "Original"]
    assert window.graphics.bands.series()[0].values[-1] == pytest.approx(4.0)
