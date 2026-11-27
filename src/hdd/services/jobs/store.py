"""Job records on disk: ``<workspace>/.hdd/jobs/<job_id>.json`` plus the job's ``.log``.

A workspace may come from someone else, so records are untrusted input: a job id is a file
name and must not be able to point outside this directory.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = 1
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9_.-]*$")


def valid_job_id(job_id: Any) -> bool:
    return isinstance(job_id, str) and bool(_JOB_ID_RE.match(job_id)) and ".." not in job_id


class JobStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, job_id: str, suffix: str) -> Path:
        if not valid_job_id(job_id):
            raise ValueError(f"Invalid job id: {job_id!r}")
        return self.directory / f"{job_id}{suffix}"

    def record_path(self, job_id: str) -> Path:
        return self._path(job_id, ".json")

    def log_path(self, job_id: str) -> Path:
        return self._path(job_id, ".log")

    def save(self, record: dict[str, Any]) -> None:
        """Write atomically, so a crash never leaves a half-written record."""
        path = self.record_path(record["job_id"])
        self.directory.mkdir(parents=True, exist_ok=True)
        # A unique temporary file: the UI thread and a follower thread may save the same job at once.
        fd, tmp = tempfile.mkstemp(dir=self.directory, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"schema": SCHEMA, **record}, handle, indent=2)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def load_all(self) -> list[dict[str, Any]]:
        if not self.directory.is_dir():
            return []
        records = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict) or record.get("schema") != SCHEMA:
                continue
            # The id names the record's own file; anything else is a stray or a crafted record.
            if valid_job_id(record.get("job_id")) and path.stem == record["job_id"]:
                records.append(record)
        return records

    def delete(self, job_id: str) -> None:
        if not valid_job_id(job_id):
            return  # never stored (e.g. a run folder listed from disk)
        for path in (self.record_path(job_id), self.log_path(job_id)):
            path.unlink(missing_ok=True)
