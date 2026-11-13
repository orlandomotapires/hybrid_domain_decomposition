"""Job records on disk: ``<workspace>/.hdd/jobs/<job_id>.json`` plus the job's ``.log``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SCHEMA = 1


class JobStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def record_path(self, job_id: str) -> Path:
        return self.directory / f"{job_id}.json"

    def log_path(self, job_id: str) -> Path:
        return self.directory / f"{job_id}.log"

    def save(self, record: dict[str, Any]) -> None:
        """Write atomically, so a crash never leaves a half-written record."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.record_path(record["job_id"])
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"schema": SCHEMA, **record}, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def load_all(self) -> list[dict[str, Any]]:
        if not self.directory.is_dir():
            return []
        records = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if record.get("schema") == SCHEMA and record.get("job_id"):
                records.append(record)
        return records

    def delete(self, job_id: str) -> None:
        for path in (self.record_path(job_id), self.log_path(job_id)):
            path.unlink(missing_ok=True)
