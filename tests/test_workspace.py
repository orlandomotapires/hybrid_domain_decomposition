"""The workspace resolver, and proof that a run stays inside the workspace it was given."""

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import scipy.io

from libs.runtime import workspace
from libs.runtime.runtime import run_simulation
from tests.test_tuning import _grid_laplacian, _params

REPO_ROOT = Path(__file__).resolve().parents[1]


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in (workspace.ENV_VAR, "HDD_HISTORY_PATH")}
    env.update(extra)
    return env


def make_workspace(root: Path) -> Path:
    """A workspace with one small matrix and one METIS simulation."""
    workspace.init(root)
    library = root / "matrices" / "grid"
    library.mkdir(parents=True)
    scipy.io.mmwrite(str(library / "grid.mtx"), _grid_laplacian())
    (library / "matrix.json").write_text(json.dumps({"name": "grid", "file": "grid.mtx"}))
    data = root / "simulations" / "sim_a" / "data"
    data.mkdir(parents=True)
    (data / "simulation_config.json").write_text(
        json.dumps({"input_matrix": "grid", "parameters_file_path": "simulation_parameters.json", "save_output": ["run_metrics", "permutation"]})
    )
    (data / "simulation_parameters.json").write_text(json.dumps(_params()))
    return root


class ResolutionTest(unittest.TestCase):
    def test_environment_variable_wins(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {workspace.ENV_VAR: tmp}):
            self.assertEqual(Path(tmp).resolve(), workspace.root())
            self.assertEqual(Path(tmp).resolve() / "matrices", workspace.matrices_dir())
            self.assertEqual(Path(tmp).resolve() / "batch" / "runs", workspace.batch_runs_dir())

    def test_marker_in_an_ancestor_of_the_current_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = workspace.init(tmp)
            nested = root / "simulations" / "deep"
            nested.mkdir(parents=True)
            code = "from libs.runtime import workspace; print(workspace.root())"
            out = subprocess.run([sys.executable, "-c", code], cwd=nested, env=_clean_env(PYTHONPATH=str(REPO_ROOT / "src")),
                                 capture_output=True, text=True, check=True)
            self.assertEqual(str(root), out.stdout.strip())

    def test_source_checkout_is_the_fallback_and_gets_pinned(self) -> None:
        with TemporaryDirectory() as elsewhere, patch.dict(os.environ, _clean_env(), clear=True):
            previous = Path.cwd()
            os.chdir(elsewhere)
            try:
                self.assertEqual(REPO_ROOT, workspace.root())
                self.assertEqual(str(REPO_ROOT), os.environ[workspace.ENV_VAR])
            finally:
                os.chdir(previous)

    def test_set_root_is_inherited_by_child_processes(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, _clean_env(), clear=True):
            workspace.set_root(tmp)
            code = "from libs.runtime import workspace; print(workspace.root())"
            out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
                                 capture_output=True, text=True, check=True)
            self.assertEqual(str(Path(tmp).resolve()), out.stdout.strip())

    def test_history_override_and_relative_paths(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, _clean_env(**{workspace.ENV_VAR: tmp}), clear=True):
            root = Path(tmp).resolve()
            self.assertEqual(root / "tuning" / "history.jsonl", workspace.history_path())
            self.assertEqual("simulations/x", workspace.rel(root / "simulations" / "x"))
            self.assertEqual("/etc/hosts", workspace.rel("/etc/hosts"))
            self.assertEqual(root / "matrices" / "m", workspace.resolve_inside("matrices/m"))
            with self.assertRaises(ValueError):
                workspace.resolve_inside("../outside")
            with patch.dict(os.environ, {"HDD_HISTORY_PATH": "/tmp/h.jsonl"}):
                self.assertEqual(Path("/tmp/h.jsonl"), workspace.history_path())

    def test_init_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = workspace.init(tmp)
            marker = root / ".hdd" / "workspace.json"
            marker.write_text('{"schema": 1, "note": "kept"}')
            workspace.init(tmp)
            self.assertIn("kept", marker.read_text())
            for name in ("matrices", "simulations", "batch", "tuning"):
                self.assertTrue((root / name).is_dir())


class RunStaysInsideWorkspaceTest(unittest.TestCase):
    def test_simulation_reads_and_writes_only_the_given_workspace(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, _clean_env(), clear=True):
            root = make_workspace(Path(tmp).resolve())
            workspace.set_root(root)
            result_dir = run_simulation("simulations/sim_a")
            self.assertEqual(root / "simulations" / "sim_a" / "results", result_dir.parent)
            inputs = json.loads((result_dir / "run_inputs.json").read_text())
            self.assertEqual("matrices/grid/grid.mtx", inputs["matrix_path"])
            history = [json.loads(line) for line in (root / "tuning" / "history.jsonl").read_text().splitlines()]
            self.assertEqual(1, len(history))
            self.assertTrue(history[0]["run_dir"].startswith("simulations/sim_a/results/run_"))

    def test_command_line_run_honours_the_workspace(self) -> None:
        with TemporaryDirectory() as tmp:
            root = make_workspace(Path(tmp).resolve())
            env = _clean_env(**{workspace.ENV_VAR: str(root), "PYTHONPATH": str(REPO_ROOT / "src")})
            subprocess.run([sys.executable, "-m", "main", "simulations/sim_a"], cwd=REPO_ROOT / "src", env=env,
                           capture_output=True, text=True, check=True)
            runs = list((root / "simulations" / "sim_a" / "results").glob("run_*"))
            self.assertEqual(1, len(runs))
            self.assertTrue((runs[0] / "permutation.txt").is_file())


class NoSourceAnchoredDataPathsTest(unittest.TestCase):
    """Only the workspace module may derive a path from where the code lives."""

    def test_core_library_has_no_file_anchors(self) -> None:
        offenders = []
        for path in (REPO_ROOT / "src" / "libs").rglob("*.py"):
            if path.name == "workspace.py":
                continue
            if re.search(r"__file__|parents\[", path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
