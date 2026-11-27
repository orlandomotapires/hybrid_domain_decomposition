"""Everything the window needs for one open workspace: services, jobs and background tasks."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from hdd.services import simulations, workspace
from hdd.services.jobs import JobManager

from .tasks import TaskRunner

# When several events arrive for a job before the GUI drains them, keep the most significant.
_EVENT_RANK = {"changed": 0, "added": 1, "finished": 2, "removed": 3}


class JobsBridge(QObject):
    """Turns job-manager events (from reader threads) into a Qt signal on the GUI thread.

    The listener only records which jobs changed; a timer on the GUI thread emits
    ``jobChanged`` for each of them, so bursts of log lines become one update.
    """

    jobChanged = Signal(str, str)  # event, job_id

    def __init__(self, manager: JobManager, parent: QObject | None = None, interval_ms: int = 100) -> None:
        super().__init__(parent)
        self._pending: dict[str, str] = {}
        self._lock = threading.Lock()
        self._unsubscribe = manager.subscribe(self._on_event)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.drain)
        self._timer.start()

    def _on_event(self, event: str, job_id: str) -> None:  # any thread
        with self._lock:
            current = self._pending.get(job_id)
            if current is None or _EVENT_RANK[event] >= _EVENT_RANK[current]:
                self._pending[job_id] = event

    def drain(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        for job_id, event in pending.items():
            self.jobChanged.emit(event, job_id)

    def close(self) -> None:
        self._timer.stop()
        self._unsubscribe()


class AppContext(QObject):
    def __init__(self, root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.root = workspace.open_workspace(root)
        self.jobs = JobManager(self.root)
        self.bridge = JobsBridge(self.jobs, self)
        self.tasks = TaskRunner(self)

    def run_simulation(self, simulation_id: str) -> dict[str, Any]:
        """Start a run of the simulation's saved parameters."""
        simulations.get_simulation(simulation_id)  # raises NotFound with a clear message
        return self.jobs.start_single_simulation(f"simulations/{simulations.sanitize_simulation_id(simulation_id)}")

    def close(self) -> None:
        """Release the workspace. Running jobs keep running and are picked up when it opens again."""
        self.bridge.close()
        self.jobs.close()
        self.tasks.cancel_pending()  # results that arrive after this are for a closed workspace
        self.tasks.wait(5000)
