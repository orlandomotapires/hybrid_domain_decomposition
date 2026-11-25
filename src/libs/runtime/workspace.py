"""Workspace: the folder that holds a project's data.

A workspace contains ``matrices/``, ``simulations/``, ``batch/`` and ``tuning/``.
Every module that reads or writes project data asks this module where it lives;
nothing else may derive a data path from the location of the source code.

Resolution order of :func:`root`:

1. the ``HDD_WORKSPACE`` environment variable;
2. the nearest ancestor of the current directory that contains ``.hdd/workspace.json``;
3. the source checkout this code runs from (so the repository itself keeps working
   as a workspace with no setup);
4. otherwise :class:`WorkspaceNotFound`.

The first successful resolution is written back to ``HDD_WORKSPACE`` so the rest of
the process and every child process (simulation, batch and tuning jobs) agree on it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ENV_VAR = "HDD_WORKSPACE"
STATE_DIR_NAME = ".hdd"
MARKER_FILE = "workspace.json"
MARKER_SCHEMA = 1


class WorkspaceNotFound(RuntimeError):
    """No workspace could be resolved."""


def _source_checkout() -> Path | None:
    """The repository root when running from a source checkout, else ``None``."""
    candidate = Path(__file__).resolve().parents[3]
    return candidate if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir() else None


def _marked_ancestor(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / STATE_DIR_NAME / MARKER_FILE).is_file():
            return directory
    return None


def root() -> Path:
    """Absolute path of the current workspace."""
    configured = os.environ.get(ENV_VAR)
    if configured:
        return Path(configured).expanduser().resolve()
    found = _marked_ancestor(Path.cwd().resolve()) or _source_checkout()
    if found is None:
        raise WorkspaceNotFound(
            f"No workspace found. Set {ENV_VAR} to a project folder, or run from inside one "
            f"(a folder containing {STATE_DIR_NAME}/{MARKER_FILE})."
        )
    os.environ[ENV_VAR] = str(found)
    return found


def set_root(path: str | Path) -> Path:
    """Make ``path`` the workspace for this process and its children."""
    resolved = Path(path).expanduser().resolve()
    os.environ[ENV_VAR] = str(resolved)
    return resolved


def init(path: str | Path) -> Path:
    """Create the folder layout and marker of a new workspace at ``path`` (idempotent)."""
    resolved = Path(path).expanduser().resolve()
    for name in ("matrices", "simulations", "batch", "tuning", STATE_DIR_NAME):
        (resolved / name).mkdir(parents=True, exist_ok=True)
    marker = resolved / STATE_DIR_NAME / MARKER_FILE
    if not marker.exists():
        marker.write_text(json.dumps({"schema": MARKER_SCHEMA}, indent=2) + "\n", encoding="utf-8")
    return resolved


def matrices_dir() -> Path:
    return root() / "matrices"


def simulations_dir() -> Path:
    return root() / "simulations"


def batch_dir() -> Path:
    return root() / "batch"


def batch_config_path() -> Path:
    return batch_dir() / "batch_configuration.json"


def batch_runs_dir() -> Path:
    return batch_dir() / "runs"


def tuning_dir() -> Path:
    return root() / "tuning"


def history_path() -> Path:
    """Global run history. ``HDD_HISTORY_PATH`` overrides the default location."""
    override = os.environ.get("HDD_HISTORY_PATH")
    return Path(override) if override else tuning_dir() / "history.jsonl"


def state_dir() -> Path:
    """Application state kept inside the workspace (job records, UI state)."""
    return root() / STATE_DIR_NAME


def rel(path: str | Path) -> str:
    """``path`` relative to the workspace, or unchanged (as text) when it lies outside."""
    try:
        return str(Path(path).resolve().relative_to(root()))
    except ValueError:
        return str(path)


def resolve_inside(relative: str | Path) -> Path:
    """Absolute path of ``relative`` inside the workspace. Raises ``ValueError`` if it escapes."""
    base = root()
    resolved = (base / relative).resolve()
    resolved.relative_to(base)
    return resolved
