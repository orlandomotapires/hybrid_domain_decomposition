"""GUI tests run headless and never touch the user's saved settings."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from hdd.studio.app import create_application
from hdd.studio.settings import Settings
from hdd.studio.theme import Theme


@pytest.fixture(scope="session")
def qapp():
    return create_application([])


@pytest.fixture()
def theme(qapp):
    return Theme(qapp, "light")


@pytest.fixture()
def settings():
    return Settings.ephemeral()
