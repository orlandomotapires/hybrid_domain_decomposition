"""The workspace (project folder) as the app sees it: which one is open, and making new ones.

A thin facade over :mod:`libs.runtime.workspace`, so the desktop layer never imports ``libs``.
"""

from __future__ import annotations

from pathlib import Path

from libs.runtime import workspace as _workspace

STATE_DIR_NAME = _workspace.STATE_DIR_NAME


def root() -> Path:
    """The open workspace (or the default one when none was chosen)."""
    return _workspace.root()


def open_workspace(path: str | Path) -> Path:
    """Make ``path`` the workspace of this process; returns its resolved path."""
    return _workspace.set_root(path)


def create_workspace(path: str | Path) -> Path:
    """Create the workspace folders in ``path`` (existing content is kept)."""
    return _workspace.init(path)


def is_workspace(path: str | Path) -> bool:
    return (Path(path) / STATE_DIR_NAME).exists()


def has_batch_config() -> bool:
    return _workspace.batch_config_path().exists()
