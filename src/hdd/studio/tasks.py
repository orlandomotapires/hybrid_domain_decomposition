"""Run blocking work (file reads, service calls) off the GUI thread.

Callbacks always run on the GUI thread. A ``key`` makes a newer request supersede an
older one with the same key: the stale result is dropped, so a slow load for a node
the user already left never overwrites the page they are looking at. An ``owner``
widget that has been destroyed by the time the result arrives also drops it.

Worker threads never touch Qt objects: they put their result in a queue, and a timer on
the GUI thread delivers it. Emitting a Qt signal from a worker thread can deadlock with the
GUI thread (the emitter holds Qt's connection lock while it waits for Python's GIL, and the
GUI thread holds the GIL while it waits for that lock, for example during garbage collection).
"""

from __future__ import annotations

import itertools
import queue
import traceback
from typing import Any, Callable

import shiboken6
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer

from hdd.services.errors import ServiceError

from . import diagnostics

POLL_MS = 10


class _Task(QRunnable):
    def __init__(self, token: int, fn: Callable[[], Any], done: queue.SimpleQueue) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._token, self._fn, self._done = token, fn, done

    def run(self) -> None:
        try:
            result, error = self._fn(), None
        except Exception as exc:  # delivered to on_error on the GUI thread
            exc.__traceback_text__ = traceback.format_exc()
            result, error = None, exc
        self._done.put((self._token, result, error))


class TaskRunner(QObject):
    def __init__(self, parent: QObject | None = None, max_threads: int = 4) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._done: queue.SimpleQueue[tuple[int, Any, Any]] = queue.SimpleQueue()
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self.drain)
        self._tokens = itertools.count(1)
        self._pending: dict[int, tuple[Callable, Callable | None, str | None, QObject | None]] = {}
        self._latest: dict[str, int] = {}

    def run(
        self,
        fn: Callable[[], Any],
        on_result: Callable[[Any], None],
        on_error: Callable[[Exception], None] | None = None,
        key: str | None = None,
        owner: QObject | None = None,
    ) -> int:
        token = next(self._tokens)
        self._pending[token] = (on_result, on_error, key, owner)
        if key is not None:
            self._latest[key] = token
        self._pool.start(_Task(token, fn, self._done))
        if not self._timer.isActive():
            self._timer.start()
        return token

    def drain(self) -> None:
        """Deliver every finished task's result (GUI thread)."""
        while True:
            try:
                token, result, error = self._done.get_nowait()
            except queue.Empty:
                break
            self._finish(token, result, error)
        if not self._pending:
            self._timer.stop()

    def cancel_pending(self) -> None:
        """Drop the callbacks of every task not yet delivered (the tasks themselves still finish)."""
        self._pending.clear()
        self._latest.clear()

    def _finish(self, token: int, result: Any, error: Any) -> None:
        on_result, on_error, key, owner = self._pending.pop(token, (None, None, None, None))
        if on_result is None:
            return
        if owner is not None and not shiboken6.isValid(owner):
            return  # the widget that asked is gone
        if key is not None and self._latest.get(key) != token:
            return  # superseded by a newer request
        if error is None:
            on_result(result)
            return
        trace = getattr(error, "__traceback_text__", None)
        if on_error is None:
            diagnostics.report_exception(error, "Background task failed", trace)
            return
        if not isinstance(error, ServiceError):
            # Service errors are expected and carry a message for the user; anything else is a
            # bug or an environment problem whose traceback must survive the error dialog.
            diagnostics.LOGGER.error("Background task failed: %s\n%s", error, (trace or "").rstrip())
        on_error(error)

    def wait(self, msecs: int = 30000) -> bool:
        """Wait for the running tasks to finish (their results are delivered by the next ``drain``)."""
        return self._pool.waitForDone(msecs)
