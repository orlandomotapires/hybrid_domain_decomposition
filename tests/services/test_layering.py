"""Layering rules of the migration: who may import whom."""

import ast
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


class LayeringTest(unittest.TestCase):
    def assert_no_imports(self, package: Path, forbidden: set[str]) -> None:
        offenders = {
            str(path.relative_to(REPO_ROOT)): sorted(imported_roots(path) & forbidden)
            for path in package.rglob("*.py")
            if imported_roots(path) & forbidden
        }
        self.assertEqual({}, offenders)

    def test_core_does_not_know_the_application_or_any_ui(self) -> None:
        self.assert_no_imports(SRC / "libs", {"hdd", "PySide6", "shiboken6", "pyqtgraph"})

    def test_services_use_only_the_core_and_plain_libraries(self) -> None:
        # An allow-list, so a new dependency of the services layer shows up here.
        # dwave: hardware.py reads the Leap config for its credential check (imported lazily; the
        # test below makes sure importing the services does not load it).
        allowed = set(sys.stdlib_module_names) | {"hdd", "libs", "numpy", "scipy", "networkx", "dwave"}
        offenders = {
            str(path.relative_to(REPO_ROOT)): sorted(imported_roots(path) - allowed)
            for path in (SRC / "hdd" / "services").rglob("*.py")
            if imported_roots(path) - allowed
        }
        self.assertEqual({}, offenders)

    def test_desktop_does_not_reach_around_the_services(self) -> None:
        self.assert_no_imports(SRC / "hdd" / "studio", {"libs"})

    def test_importing_the_services_does_not_load_the_quantum_stack(self) -> None:
        code = (
            "import sys, hdd.services.simulations, hdd.services.matrices, hdd.services.results, hdd.services.batch, "
            "hdd.services.tuning, hdd.services.hardware; "
            "print(sorted(m for m in ('pennylane', 'dwave', 'neal', 'optuna') if m in sys.modules))"
        )
        out = subprocess.run([sys.executable, "-c", code], env={"PYTHONPATH": str(SRC), "PATH": ""}, capture_output=True, text=True, check=True)
        self.assertEqual("[]", out.stdout.strip())


class DesktopImportCostTest(unittest.TestCase):
    def test_opening_the_desktop_app_does_not_load_heavy_or_web_stacks(self) -> None:
        code = (
            "import sys, hdd.studio.main_window; "
            "print(sorted(m for m in ('pennylane', 'dwave', 'neal', 'optuna', 'matplotlib.pyplot', 'fastapi') if m in sys.modules))"
        )
        env = {"PYTHONPATH": str(SRC), "PATH": "", "QT_QPA_PLATFORM": "offscreen"}
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        self.assertEqual("[]", out.stdout.strip())

    def test_loading_a_project_and_the_hardware_probe_module_stay_light(self) -> None:
        # What the window does at runtime: read the whole project tree (studies included) and
        # import the D-Wave access module a probe uses.
        code = (
            "import sys, json, tempfile, pathlib, scipy.io, scipy.sparse as sp; "
            "from libs.runtime import workspace; "
            "root = workspace.init(pathlib.Path(tempfile.mkdtemp())); workspace.set_root(root); "
            "lib = root / 'matrices' / 'm'; lib.mkdir(); scipy.io.mmwrite(str(lib / 'm.mtx'), sp.identity(4).tocsr()); "
            "(lib / 'matrix.json').write_text(json.dumps({'name': 'm', 'file': 'm.mtx'})); "
            "from hdd.studio.project import load_snapshot; load_snapshot(); "
            "import libs.multilevel_scheme.partitioning.qa.dwave_access; "
            "print(sorted(m for m in ('pennylane', 'neal', 'optuna', 'matplotlib.pyplot') if m in sys.modules))"
        )
        env = {"PYTHONPATH": str(SRC), "PATH": "", "QT_QPA_PLATFORM": "offscreen"}
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual("[]", out.stdout.strip(), out.stderr)


if __name__ == "__main__":
    unittest.main()
