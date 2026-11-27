"""Isolation shared by every test: no state leaks from one test into the next."""

import os

import pytest

from libs.runtime.log import close_log_file

_ENV_KEYS = ("HDD_WORKSPACE", "HDD_HISTORY_PATH", "HDD_DISABLE_HISTORY", "HDD_BATCH_DIR")


@pytest.fixture(autouse=True)
def isolated_process_state(tmp_path_factory):
    """Restore the workspace-related environment and close the pipeline's log file after each test.

    ``workspace.root()`` pins ``HDD_WORKSPACE`` and ``run_simulation`` opens a module-global log
    file; without this a later test could log into an earlier test's run folder. Runs never
    append to the repository's own tuning history.
    """
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    os.environ.setdefault("HDD_HISTORY_PATH", str(tmp_path_factory.mktemp("history") / "history.jsonl"))
    yield
    close_log_file()
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
