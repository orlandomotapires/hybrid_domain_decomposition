"""Run blocking work (file reads, service calls) off the GUI thread.

Callbacks always run on the GUI thread. A ``key`` makes a newer request supersede an
older one with the same key: the stale result is dropped, so a slow load for a node
the user already left never overwrites the page they are looking at. An ``owner``
widget that has been destroyed by the time the result arrives also drops it.
"""

from __future__ import annotations

import itertools
import traceback
from typing import Any, Callable

import shiboken6
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Signals(QObject):
    done = Signal(int, object, object)  # token, result, error


class _Task(QRunnable):
    def __init__(self, token: int, fn: Callable[[], Any], signals: _Signals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._token, self._fn, self._signals = token, fn, signals

    def run(self) -> None:
        try:
            result, error = self._fn(), None
        except Exception as exc:  # delivered to on_error on the GUI thread
            exc.__traceback_text__ = traceback.format_exc()
            result, error = None, exc
        self._signals.done.emit(self._token, result, error)


class TaskRunner(QObject):
    def __init__(self, parent: QObject | None = None, max_threads: int = 4) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max_threads)
        self._signals = _Signals(self)
        self._signals.done.connect(self._finish)
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
        self._pool.start(_Task(token, fn, self._signals))
        return token

    @Slot(int, object, object)
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
        elif on_error is not None:
            on_error(error)

    def wait(self, msecs: int = 30000) -> bool:
        return self._pool.waitForDone(msecs)
