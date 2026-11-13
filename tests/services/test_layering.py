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
        self.assert_no_imports(SRC / "libs", {"hdd", "backend", "PySide6", "fastapi", "pydantic"})

    def test_services_do_not_know_any_ui_or_http(self) -> None:
        self.assert_no_imports(SRC / "hdd" / "services", {"backend", "PySide6", "fastapi", "pydantic", "pyqtgraph"})

    def test_desktop_does_not_reach_around_the_services(self) -> None:
        self.assert_no_imports(SRC / "hdd" / "studio", {"backend", "fastapi"})

    def test_importing_the_services_does_not_load_the_quantum_stack(self) -> None:
        code = (
            "import sys, hdd.services.simulations, hdd.services.matrices; "
            "print(sorted(m for m in ('pennylane', 'dwave', 'neal', 'optuna') if m in sys.modules))"
        )
        out = subprocess.run([sys.executable, "-c", code], env={"PYTHONPATH": str(SRC), "PATH": ""}, capture_output=True, text=True, check=True)
        self.assertEqual("[]", out.stdout.strip())


if __name__ == "__main__":
    unittest.main()
