"""How a job is launched: the command line and environment of the child process."""

from __future__ import annotations

from pathlib import Path

from libs.runtime.launch import child_environment, module_command, package_root

ENTRY_MODULE = "libs.runtime.job_entry"

__all__ = ["ENTRY_MODULE", "job_command", "job_environment", "package_root"]


def job_command(kind: str, args: list[str], python: str | None = None) -> list[str]:
    """Command line of ``libs.runtime.job_entry kind *args`` (never imports from the workspace)."""
    return module_command(ENTRY_MODULE, [kind, *args], python)


def job_environment(workspace_root: Path) -> dict[str, str]:
    return child_environment({
        "PYTHONUNBUFFERED": "1",
        "HDD_EVENTS": "1",  # libs.runtime.events: report progress as structured events
        "HDD_WORKSPACE": str(workspace_root),
    })
