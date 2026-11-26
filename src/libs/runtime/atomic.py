"""Write files so that a reader never sees half of them.

The text goes to a unique temporary file in the same folder, which then replaces the target in
one step. A crash, a full disk or an error while serialising leaves the old file intact, and two
writers of the same file never write into each other's temporary file.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows: appends are still single writes, just not locked
    fcntl = None


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_line(path: str | Path, line: str) -> None:
    """Append one line to a shared log file (JSON Lines) without interleaving with other writers.

    The whole line goes out in a single write under an exclusive lock, and a previous writer that
    died mid-line is repaired first, so its fragment does not swallow this line.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.fstat(fd).st_size
        if size:
            os.lseek(fd, size - 1, os.SEEK_SET)
            if os.read(fd, 1) != b"\n":
                data = b"\n" + data
        os.write(fd, data)  # O_APPEND: goes to the end whatever the read position
    finally:
        os.close(fd)  # also releases the lock


def atomic_write_json(path: str | Path, data: Any, **dumps_kwargs: Any) -> None:
    """Serialise first (so a bad value raises before anything is touched), then write atomically."""
    dumps_kwargs.setdefault("indent", 2)
    atomic_write_text(path, json.dumps(data, **dumps_kwargs))
