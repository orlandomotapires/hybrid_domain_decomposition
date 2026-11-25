"""Structured progress events for the job runner.

A job reports its progress as lines on stdout::

    @@hdd-event {"event": "stage", "stage": "coarsening", "index": 1, "of": 5}

The Studio's job manager reads these instead of guessing from the wording of log
messages. Events are emitted only inside a Studio job (``HDD_EVENTS=1``, set by
the job runner), so command-line runs print nothing extra.

Events
------
``stage``        a pipeline stage starts: ``stage``, ``index``, ``of``
``progress``     work done inside the current stage: ``fraction`` (0–1)
``result``       a run wrote its results: ``result_dir``
``batch``        a batch starts: ``total``
``batch_case``   a batch case starts: ``index``, ``total``, ``case``
``batch_done``   a batch case ends: ``case``, ``status`` (``completed`` | ``failed``)
``tuning``       a tuning study starts: ``total``
``trial``        a tuning trial ends: ``done``, ``total``, ``status``
``exit``         the job ends: ``code`` (0 is success)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

PREFIX = "@@hdd-event "
ENV_VAR = "HDD_EVENTS"

STAGES = ("initialization", "coarsening", "partitioning", "uncoarsening", "permutation")


def enabled() -> bool:
    return os.environ.get(ENV_VAR) == "1"


def emit(event: str, **data: Any) -> None:
    """Write one event line to stdout (only inside a Studio job)."""
    if not enabled():
        return
    payload = json.dumps({"event": event, **data}, default=str, separators=(",", ":"))
    sys.stdout.write(f"{PREFIX}{payload}\n")
    sys.stdout.flush()


def stage(name: str) -> None:
    emit("stage", stage=name, index=STAGES.index(name), of=len(STAGES))


def progress(fraction: float) -> None:
    emit("progress", fraction=round(max(0.0, min(1.0, float(fraction))), 4))


def parse(line: str) -> dict[str, Any] | None:
    """The event in ``line``, or ``None`` when it is an ordinary log line."""
    if not line.startswith(PREFIX):
        return None
    try:
        event = json.loads(line[len(PREFIX):])
    except ValueError:
        return None
    return event if isinstance(event, dict) and "event" in event else None
