"""How a job is launched: the command line and environment of the child process."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ENTRY_MODULE = "libs.runtime.job_entry"


def package_root() -> Path:
    """Folder that contains the ``libs`` package (``src/`` in a checkout, site-packages when installed)."""
    spec = importlib.util.find_spec("libs")
    return Path(next(iter(spec.submodule_search_locations))).parent


def job_command(kind: str, args: list[str], python: str | None = None) -> list[str]:
    """``[python, -u, -m, libs.runtime.job_entry, kind, *args]``."""
    return [python or sys.executable, "-u", "-m", ENTRY_MODULE, kind, *args]


def job_environment(workspace_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["HDD_WORKSPACE"] = str(workspace_root)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(package_root()), env.get("PYTHONPATH")) if p)
    return env
