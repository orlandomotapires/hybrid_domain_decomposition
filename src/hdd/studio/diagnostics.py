"""Logging and last-resort error reporting for the Studio process.

Everything goes to a rotating log file in the user's state folder (and to stderr). Uncaught
exceptions, whether in a Qt slot, a background thread or a task without an error handler, are
logged with their traceback and announced to the user through the reporter the main window
registers, so a failure is never silent even when the app was started from a launcher.
"""

from __future__ import annotations

import logging
import logging.handlers
import queue
import sys
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QStandardPaths, QtMsgType, QTimer, qInstallMessageHandler

LOGGER = logging.getLogger("hdd")
_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"

_state: dict[str, object] = {"installed": False, "log_file": None}


class _Relay(QObject):
    """Carries messages from any thread to the GUI thread, where the relay lives.

    Other threads only append to a queue; a timer on the GUI thread hands them on. (A Qt signal
    emitted from another thread can deadlock with the GUI thread: see ``tasks.py``.)
    """

    def __init__(self, interval_ms: int = 100) -> None:
        super().__init__()
        self._messages: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.drain)
        self._timer.start()

    def post(self, text: str) -> None:  # any thread
        self._messages.put(text)

    def drain(self) -> None:
        while True:
            try:
                text = self._messages.get_nowait()
            except queue.Empty:
                return
            _deliver(text)


_relay: _Relay | None = None
_reporter: Callable[[str], None] | None = None


def log_file() -> Path | None:
    return _state["log_file"]  # type: ignore[return-value]


def default_log_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    return Path(base or Path.home() / ".local" / "state" / "hdd-studio") / "logs"


def install(log_dir: Path | None = None) -> Path | None:
    """Set up logging and the exception hooks once per process. Returns the log file, if any."""
    global _relay
    if _state["installed"]:
        return log_file()
    _state["installed"] = True

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    path: Path | None = None
    try:
        directory = log_dir or default_log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "studio.log"
        handlers.append(logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"))
    except OSError as exc:  # a read-only home must not stop the app
        print(f"HDD Studio: cannot write a log file ({exc})", file=sys.stderr)
        path = None
    _state["log_file"] = path

    formatter = logging.Formatter(_FORMAT)
    root = logging.getLogger()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.WARNING)
    LOGGER.setLevel(logging.INFO)

    _relay = _Relay()
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    qInstallMessageHandler(_qt_message)
    LOGGER.info("HDD Studio started (Python %s); log file: %s", sys.version.split()[0], path)
    return path


def set_reporter(reporter: Callable[[str], None] | None) -> None:
    """Show error summaries to the user, e.g. in the main window's status bar (GUI thread)."""
    global _reporter
    _reporter = reporter


def report_exception(exc: BaseException, context: str, traceback_text: str | None = None) -> None:
    """Log an unexpected exception with its traceback and tell the user."""
    if traceback_text:
        LOGGER.error("%s: %s\n%s", context, exc, traceback_text.rstrip())
    else:
        LOGGER.error("%s: %s", context, exc, exc_info=(type(exc), exc, exc.__traceback__))
    summary = f"Unexpected error: {exc}" if str(exc) else f"Unexpected error: {type(exc).__name__}"
    if log_file() is not None:
        summary += f" (details in {log_file()})"
    if _relay is not None:
        _relay.post(summary)  # shown from the GUI thread


def _deliver(text: str) -> None:
    if _reporter is not None:
        try:
            _reporter(text)
        except Exception:  # the reporter's window may be closing
            LOGGER.exception("error reporter failed")


def _excepthook(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    exc.__traceback__ = tb
    report_exception(exc, "Uncaught exception")


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit or args.exc_value is None:
        return
    args.exc_value.__traceback__ = args.exc_traceback
    name = args.thread.name if args.thread is not None else "unknown"
    report_exception(args.exc_value, f"Uncaught exception in thread {name}")


_QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def _qt_message(mode, context, message: str) -> None:
    logging.getLogger("hdd.qt").log(_QT_LEVELS.get(mode, logging.WARNING), message)
