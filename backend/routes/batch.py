from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from libs.runtime import workspace
from libs.runtime.utils import write_json
from backend.services.job_manager import job_manager

router = APIRouter(prefix="/api/batch", tags=["batch"])



class StartBatchRequest(BaseModel):
    stop_on_error: bool = False


def _compute_dry_run_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    geometries = config.get("matrices", [])
    coarsening_presets = config.get("coarsening_presets", [])
    algorithm_presets = config.get("algorithm_presets", [])
    async_keys = set(config.get("async_remote_case_keys", []))

    cases: list[dict[str, Any]] = []
    for geom in geometries:
        for alg in algorithm_presets:
            allowed_sizes = set(alg.get("allowed_sizes", []))
            for coarsen in coarsening_presets:
                c_key = coarsen.get("key")
                if c_key not in allowed_sizes:
                    continue
                case_key = f"{geom.get('key')}__{alg.get('key')}__{c_key}"
                cases.append(
                    {
                        "case_key": case_key,
                        "geometry": geom.get("key"),
                        "matrix": geom.get("key"),
                        "algorithm": alg.get("key"),
                        "partitioning_strategy": alg.get("partitioning_strategy"),
                        "coarsening_size": c_key,
                        "coarsen_inferior_limit": coarsen.get("coarsen_inferior_limit"),
                        "coarsen_superior_limit": coarsen.get("coarsen_superior_limit"),
                        "is_async": alg.get("key") in async_keys,
                        "strategy_parameters": alg.get("strategy_parameters", {}),
                    }
                )
    return cases


@router.get("/config")
def get_batch_configuration() -> dict[str, Any]:
    if not workspace.batch_config_path().exists():
        raise HTTPException(status_code=404, detail="batch_configuration.json not found")
    config = json.loads(workspace.batch_config_path().read_text(encoding="utf-8"))
    cases = _compute_dry_run_cases(config)
    return {
        "configuration": config,
        "dry_run_cases": cases,
        "case_count": len(cases),
    }


@router.put("/config")
def update_batch_configuration(config_payload: dict[str, Any]) -> dict[str, Any]:
    required_keys = {"algorithm_presets", "coarsening_presets", "common_defaults", "matrices"}
    missing = required_keys - set(config_payload.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required batch configuration keys: {', '.join(sorted(missing))}")

    write_json(workspace.batch_config_path(), config_payload)
    cases = _compute_dry_run_cases(config_payload)
    return {
        "configuration": config_payload,
        "dry_run_cases": cases,
        "case_count": len(cases),
    }


@router.post("/run")
def start_batch_run(req: StartBatchRequest) -> dict[str, Any]:
    return job_manager.start_batch_study(stop_on_error=req.stop_on_error)


_LOG_CASE_RE = re.compile(r"^\[(\d+)/(\d+)\] (Running|Launched async) (\S+)")
_LOG_TS_RE = re.compile(r"^\[(\d{1,2} \w{3} \d{4} \d{2}:\d{2}:\d{2}) UTC ")


def _parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _durations_from_log(log_path: Path) -> dict[str, float]:
    """Per-case seconds from batch.log: first to last timestamp between `[NN/MM] Running <case>` markers.

    Used only for cases without manifest timestamps (e.g. summary rows merged from an older batch).
    Async launches are skipped because their work happens in a separate process/log. Status is not
    inferred here (an async case's FAILED line can be printed inside another case's block); callers
    only use entries for cases already known to be completed.
    """
    durations: dict[str, float] = {}
    if not log_path.exists():
        return durations
    current: str | None = None
    first: datetime | None = None
    last: datetime | None = None

    def flush() -> None:
        if current and first and last and last >= first:
            durations[current] = (last - first).total_seconds()

    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        marker = _LOG_CASE_RE.match(line)
        if marker:
            flush()
            current = marker.group(4) if marker.group(3) == "Running" else None
            first = last = None
            continue
        if current is None:
            continue
        ts = _LOG_TS_RE.match(line)
        if ts:
            try:
                stamp = datetime.strptime(ts.group(1), "%d %b %Y %H:%M:%S")
            except ValueError:
                continue
            first = first or stamp
            last = stamp
    flush()
    return durations


def collect_case_durations(runs_dir: Path | None = None) -> list[dict[str, Any]]:
    """Durations (seconds) of every *completed* case across past batches.

    Prefers manifest `started_at`/`finished_at`; falls back to batch.log timestamps.
    """
    samples: list[dict[str, Any]] = []
    runs_dir = runs_dir or workspace.batch_runs_dir()
    if not runs_dir.exists():
        return samples
    for bdir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        manifest: dict[str, Any] = {}
        summary_rows: list[dict[str, Any]] = []
        try:
            manifest = json.loads((bdir / "batch_manifest.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        try:
            summary_rows = json.loads((bdir / "batch_summary.json").read_text(encoding="utf-8")).get("rows", [])
        except Exception:
            pass

        cases: dict[str, dict[str, Any]] = {}
        for row in summary_rows:
            if row.get("case_key"):
                cases[row["case_key"]] = dict(row)
        for case in manifest.get("cases", []):
            if case.get("case_key"):
                cases[case["case_key"]] = {**cases.get(case["case_key"], {}), **case}

        log_durations: dict[str, float] | None = None
        for key, case in cases.items():
            if case.get("status") != "completed":
                continue
            start, end = _parse_iso(case.get("started_at")), _parse_iso(case.get("finished_at"))
            seconds: float | None = None
            source = "manifest"
            if start and end and end >= start:
                seconds = (end - start).total_seconds()
            else:
                if log_durations is None:
                    log_durations = _durations_from_log(bdir / "batch.log")
                seconds = log_durations.get(key)
                source = "log"
            if seconds is None:
                continue
            parts = key.split("__")
            samples.append(
                {
                    "batch_id": bdir.name,
                    "case_key": key,
                    "geometry": case.get("geometry") or (parts[0] if len(parts) == 3 else None),
                    "algorithm": case.get("algorithm") or (parts[1] if len(parts) == 3 else None),
                    "coarsening_size": case.get("coarsening_size") or (parts[2] if len(parts) == 3 else None),
                    "seconds": round(seconds, 1),
                    "is_async": bool(case.get("async_log_file")),
                    "source": source,
                }
            )
    return samples


def compute_duration_estimates(runs_dir: Path | None = None) -> dict[str, Any]:
    """Median duration per (algorithm, scale) and per (matrix, algorithm, scale) from past batches."""
    samples = collect_case_durations(runs_dir)
    by_alg_scale: dict[str, list[float]] = {}
    by_case: dict[str, list[float]] = {}
    for s in samples:
        if not s["algorithm"] or not s["coarsening_size"]:
            continue
        by_alg_scale.setdefault(f"{s['algorithm']}__{s['coarsening_size']}", []).append(s["seconds"])
        if s["geometry"]:
            by_case.setdefault(f"{s['geometry']}__{s['algorithm']}__{s['coarsening_size']}", []).append(s["seconds"])

    def summarize(groups: dict[str, list[float]]) -> dict[str, dict[str, Any]]:
        return {
            key: {"median_seconds": round(median(vals), 1), "samples": len(vals)}
            for key, vals in sorted(groups.items())
        }

    return {
        "by_case": summarize(by_case),
        "by_algorithm_scale": summarize(by_alg_scale),
        "sample_count": len(samples),
        "batch_count": len({s["batch_id"] for s in samples}),
    }


@router.get("/estimates")
def get_batch_estimates() -> dict[str, Any]:
    """Median per-case durations from past batch runs, used to estimate a new batch before launch."""
    return compute_duration_estimates()


@router.get("/runs")
def list_batch_runs() -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    if workspace.batch_runs_dir().exists():
        for bdir in sorted(workspace.batch_runs_dir().iterdir(), key=lambda p: p.name, reverse=True):
            if not bdir.is_dir():
                continue
            manifest_path = bdir / "batch_manifest.json"
            summary_path = bdir / "batch_summary.json"
            manifest = {}
            summary_rows = []
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if summary_path.exists():
                try:
                    summary_rows = json.loads(summary_path.read_text(encoding="utf-8")).get("rows", [])
                except Exception:
                    pass

            cases = manifest.get("cases", summary_rows)
            completed = sum(1 for c in cases if c.get("status") == "completed")
            failed = sum(1 for c in cases if c.get("status") == "failed")
            running = sum(1 for c in cases if c.get("status") in ("running", "running_async"))
            geometries = sorted({c.get("geometry") for c in cases if c.get("geometry")})

            runs.append(
                {
                    "id": bdir.name,
                    "batch_directory": f"batch/runs/{bdir.name}",
                    "started_at": manifest.get("batch_started_at"),
                    "finished_at": manifest.get("batch_finished_at"),
                    "total_cases": len(cases),
                    "completed_cases": completed,
                    "failed_cases": failed,
                    "running_cases": running,
                    "geometries": geometries,
                    "has_summary": summary_path.exists(),
                }
            )
    return {"batch_runs": runs}


@router.get("/runs/{batch_id}")
def get_batch_run_detail(batch_id: str) -> dict[str, Any]:
    bdir = workspace.batch_runs_dir() / batch_id
    if not bdir.exists() or not bdir.is_dir():
        raise HTTPException(status_code=404, detail=f"Batch run {batch_id!r} not found")

    manifest_path = bdir / "batch_manifest.json"
    summary_path = bdir / "batch_summary.json"
    config_path = bdir / "batch_configuration.json"
    log_path = bdir / "batch.log"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"rows": []}
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    log_text = log_path.read_text(encoding="utf-8", errors="ignore")[-40000:] if log_path.exists() else ""

    return {
        "id": batch_id,
        "manifest": manifest,
        "summary_rows": summary.get("rows", []),
        "configuration": config,
        "batch_log": log_text,
    }

