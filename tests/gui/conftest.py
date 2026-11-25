"""GUI tests run headless and never touch the user's saved settings."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from hdd.studio.app import create_application
from hdd.studio.settings import Settings
from hdd.studio.theme import Theme
from libs.runtime import workspace


@pytest.fixture(autouse=True)
def restore_workspace():
    """Opening a window points the process at its workspace (``workspace.set_root``); undo that after each test."""
    before = os.environ.get(workspace.ENV_VAR)
    yield
    if before is None:
        os.environ.pop(workspace.ENV_VAR, None)
    else:
        os.environ[workspace.ENV_VAR] = before


@pytest.fixture(scope="session")
def qapp():
    return create_application([])


@pytest.fixture()
def theme(qapp):
    return Theme(qapp, "light")


@pytest.fixture()
def settings():
    return Settings.ephemeral()
