"""Command lines for detached child interpreters (jobs, background batches).

Children run with the workspace as their working directory, and ``python -m``/``-c`` put that
directory first on ``sys.path``. A workspace is data that may come from someone else, so a
``json.py`` or ``libs/`` folder in it must never be imported. :func:`module_command` drops the
entry before importing anything (Python 3.10+); :data:`SAFE_PATH_ENV` covers any further
interpreter the child starts, such as a multiprocessing forkserver (Python 3.11+).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

SAFE_PATH_ENV = {"PYTHONSAFEPATH": "1"}

_BOOTSTRAP = (
    "import sys, os; "
    "sys.path[:] = [p for p in sys.path if p not in ('', '.', os.getcwd())]; "
    "import runpy; runpy.run_module({module!r}, run_name='__main__', alter_sys=True)"
)


def package_root() -> Path:
    """Folder that contains the ``libs`` package (``src/`` in a checkout, site-packages when installed)."""
    spec = importlib.util.find_spec("libs")
    return Path(next(iter(spec.submodule_search_locations))).parent


def module_command(module: str, args: list[str], python: str | None = None, *, unbuffered: bool = True) -> list[str]:
    """Run ``module`` like ``python -m module *args``, without the working directory on sys.path."""
    flags = ["-u"] if unbuffered else []
    return [python or sys.executable, *flags, "-c", _BOOTSTRAP.format(module=module), *args]


def child_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Current environment plus safe-path mode, with this package importable from anywhere."""
    env = dict(os.environ)
    env.update(SAFE_PATH_ENV)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(package_root()), env.get("PYTHONPATH")) if p)
    env.update(extra or {})
    return env
