"""Bounded retries for calls to remote quantum services.

A hardware run makes many remote calls (``num_starts * (k - 1)`` D-Wave problems, or QLM jobs
per optimizer step); one dropped connection should not throw away the work already paid for.
Only transient errors are retried, a few times, and every retry is logged.
"""

from __future__ import annotations

import time
from typing import Callable, Sequence, TypeVar

from libs.runtime.log import log

T = TypeVar("T")

# Seconds to wait before the second and third attempt.
QPU_RETRY_DELAYS: tuple[float, ...] = (5.0, 30.0)


def call_with_retries(
    fn: Callable[[], T],
    *,
    retry_on: tuple[type[BaseException], ...],
    what: str,
    delays: Sequence[float] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn``; on one of ``retry_on`` wait and try again, ``len(delays) + 1`` attempts in all."""
    waits = list(QPU_RETRY_DELAYS if delays is None else delays)
    attempts = len(waits) + 1
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as exc:
            if attempt == attempts:
                raise
            delay = waits[attempt - 1]
            log("WARNING", f"{what} failed ({type(exc).__name__}: {exc}); "
                           f"retrying in {delay:.0f}s (attempt {attempt + 1} of {attempts})")
            sleep(delay)
    raise AssertionError("unreachable")
