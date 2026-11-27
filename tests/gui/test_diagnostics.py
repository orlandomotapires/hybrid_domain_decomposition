"""Unexpected errors are logged with their traceback and reported to the user, never dropped."""

import logging
import sys
import threading

import pytest
from PySide6.QtCore import qInstallMessageHandler

from hdd.services.errors import InvalidInput
from hdd.studio import diagnostics
from hdd.studio.tasks import TaskRunner


def _boom():
    raise RuntimeError("boom")


def test_failed_task_without_handler_is_logged_with_traceback(qtbot, qapp, caplog):
    runner = TaskRunner()
    with caplog.at_level(logging.ERROR, logger="hdd"):
        runner.run(_boom, lambda result: None)
        qtbot.waitUntil(lambda: any("Background task failed" in r.getMessage() for r in caplog.records))
    message = next(r.getMessage() for r in caplog.records if "Background task failed" in r.getMessage())
    assert "Traceback" in message and "RuntimeError: boom" in message


def test_handled_task_errors_log_bugs_but_not_service_errors(qtbot, qapp, caplog):
    runner = TaskRunner()
    seen = []
    with caplog.at_level(logging.ERROR, logger="hdd"):
        runner.run(_boom, lambda result: None, seen.append)
        runner.run(lambda: (_ for _ in ()).throw(InvalidInput("bad value")), lambda result: None, seen.append)
        qtbot.waitUntil(lambda: len(seen) == 2)
    assert sorted(type(e).__name__ for e in seen) == ["InvalidInput", "RuntimeError"]
    logged = [r.getMessage() for r in caplog.records]
    assert any("RuntimeError: boom" in m for m in logged)
    assert not any("bad value" in m for m in logged)


@pytest.fixture()
def installed(tmp_path, monkeypatch, qapp):
    """Install the hooks for one test and put everything back afterwards."""
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setitem(diagnostics._state, "installed", False)
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    path = diagnostics.install(tmp_path)
    yield path
    qInstallMessageHandler(None)
    for handler in root.handlers[len(handlers):]:
        handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)
    diagnostics.set_reporter(None)


def test_thread_crash_reaches_the_log_file_and_the_user(qtbot, installed):
    shown, threads = [], []
    diagnostics.set_reporter(lambda text: (shown.append(text), threads.append(threading.current_thread())))
    worker = threading.Thread(target=_boom, name="follower")
    worker.start()
    worker.join()
    qtbot.waitUntil(lambda: bool(shown))
    assert "boom" in shown[0] and str(installed) in shown[0]
    assert threads[0] is threading.main_thread()  # widgets may only be touched from the GUI thread
    text = installed.read_text(encoding="utf-8")
    assert "Uncaught exception in thread follower" in text and "RuntimeError: boom" in text
