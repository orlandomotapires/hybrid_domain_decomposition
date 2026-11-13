"""Moved to ``hdd.services.jobs``. Kept so existing imports keep working.

``job_manager`` is created on first use for the current workspace.
"""

from __future__ import annotations

import threading
from typing import Any

from hdd.services.jobs.manager import JobManager, SimulationJob  # noqa: F401
from hdd.services.jobs.parsing import PIPELINE_STAGES, _parse_log_line  # noqa: F401


class _LazyJobManager:
    _instance: JobManager | None = None
    _lock = threading.Lock()

    def _get(self) -> JobManager:
        with self._lock:
            if self._instance is None:
                type(self)._instance = JobManager()
            return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)


job_manager = _LazyJobManager()
