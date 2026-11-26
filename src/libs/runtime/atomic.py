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


def atomic_write_json(path: str | Path, data: Any, **dumps_kwargs: Any) -> None:
    """Serialise first (so a bad value raises before anything is touched), then write atomically."""
    dumps_kwargs.setdefault("indent", 2)
    atomic_write_text(path, json.dumps(data, **dumps_kwargs))
