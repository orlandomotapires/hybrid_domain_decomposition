"""GUI tests run headless and never touch the user's saved settings."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from hdd.studio.app import create_application
from hdd.studio.settings import Settings
from hdd.studio.theme import Theme

# The workspace environment is restored after every test by tests/conftest.py.


@pytest.fixture(scope="session")
def qapp():
    return create_application([])


@pytest.fixture()
def theme(qapp):
    return Theme(qapp, "light")


@pytest.fixture()
def settings():
    return Settings.ephemeral()


_exit_status = 0


def pytest_sessionfinish(session, exitstatus):
    global _exit_status
    _exit_status = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    """Skip the interpreter's own shutdown after a GUI test session on Python < 3.12.

    There, PySide6 crashes while Python tears down the session's Qt objects (free(): invalid
    size, or a segfault) after every test passed and the report was printed, which fails CI.
    This runs after all of pytest's own work (reports, coverage data), so ending the process
    here, with pytest's exit status, loses nothing.
    """
    if sys.version_info < (3, 12):
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_exit_status)
