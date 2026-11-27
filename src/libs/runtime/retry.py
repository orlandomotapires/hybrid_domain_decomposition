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

# HTTP statuses worth another try: rate limiting and server-side failures. A 4xx such as 400,
# 401 or 403 means the request itself is wrong and would fail the same way again.
RETRY_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


def http_status(exc: BaseException) -> int | None:
    """Status code carried by an HTTP error (requests or similar), if any."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status", None)
    return status if isinstance(status, int) else None


def is_transient_network_error(exc: BaseException) -> bool:
    """A connection problem or timeout, or an HTTP error with a retryable status."""
    status = http_status(exc)
    if status is not None:
        return status in RETRY_HTTP_STATUSES
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    # requests' and urllib3's connection errors and timeouts (matched by name: both packages are
    # optional here, and their HTTPError base class also covers non-transient errors).
    names = {cls.__name__ for cls in type(exc).__mro__}
    return bool(names & {"ConnectionError", "Timeout", "TimeoutError", "ProtocolError", "NewConnectionError",
                         "MaxRetryError", "ReadTimeoutError", "ConnectTimeoutError", "ChunkedEncodingError"})


def call_with_retries(
    fn: Callable[[], T],
    *,
    retry_on: tuple[type[BaseException], ...],
    what: str,
    retry_if: Callable[[BaseException], bool] | None = None,
    delays: Sequence[float] | None = None,
    deadline: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> T:
    """Call ``fn``; on one of ``retry_on`` (for which ``retry_if`` holds) wait and try again.

    ``len(delays) + 1`` attempts in all. With ``deadline`` (a ``clock()`` value) no wait goes past it.
    """
    waits = list(QPU_RETRY_DELAYS if delays is None else delays)
    attempts = len(waits) + 1
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as exc:
            if attempt == attempts or (retry_if is not None and not retry_if(exc)):
                raise
            delay = waits[attempt - 1]
            if deadline is not None and clock() + delay >= deadline:
                raise
            log("WARNING", f"{what} failed ({type(exc).__name__}: {exc}); "
                           f"retrying in {delay:.0f}s (attempt {attempt + 1} of {attempts})")
            sleep(delay)
    raise AssertionError("unreachable")
