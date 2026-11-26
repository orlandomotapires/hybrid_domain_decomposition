"""Batch studies: the configuration (matrices x algorithms x coarsening scales), its plan and past runs."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from libs.runtime import workspace
from libs.batch.cases import case_key, unique_matrix_keys
from libs.runtime.utils import write_json
from libs.multilevel_scheme.partitioning.capacity import backend_capacity, qpu_workload

from .errors import InvalidInput, NotFound

REQUIRED_KEYS = ("algorithm_presets", "coarsening_presets", "common_defaults", "matrices")
_BATCH_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


# ------------------------------------------------------------ configuration
def validate_configuration(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise InvalidInput("Batch configuration must be a JSON object")
    missing = sorted(set(REQUIRED_KEYS) - set(config))
    if missing:
        raise InvalidInput(f"Missing required batch configuration keys: {', '.join(missing)}")
    from libs.batch.run_batch import parse_batch_configuration

    try:
        parse_batch_configuration(config)
    except (KeyError, ValueError, TypeError) as exc:
        raise InvalidInput(f"Invalid batch configuration: {exc!r}") from exc


def load_configuration() -> dict[str, Any]:
    path = workspace.batch_config_path()
    if not path.exists():
        raise NotFound("batch_configuration.json not found")
    config = json.loads(path.read_text(encoding="utf-8"))
    cases = dry_run_cases(config)
    return {"configuration": config, "dry_run_cases": cases, "case_count": len(cases)}


def save_configuration(config: dict[str, Any]) -> dict[str, Any]:
    validate_configuration(config)
    workspace.batch_config_path().parent.mkdir(parents=True, exist_ok=True)
    write_json(workspace.batch_config_path(), config)
    cases = dry_run_cases(config)
    return {"configuration": config, "dry_run_cases": cases, "case_count": len(cases)}


def dry_run_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    """The cases a configuration expands to, in run order (the same expansion the batch runs).

    Tolerates a half-edited configuration, which the editor previews while the user types.
    """
    async_keys = set(config.get("async_remote_case_keys", []))
    cases = []
    for matrix in unique_matrix_keys(config):
        for alg in config.get("algorithm_presets", []):
            allowed = set(alg.get("allowed_sizes", []))
            for coarsen in config.get("coarsening_presets", []):
                size = coarsen.get("key")
                if size not in allowed:
                    continue
                cases.append(
                    {
                        "case_key": case_key(matrix, alg.get("key"), size),
                        "geometry": matrix,
                        "matrix": matrix,
                        "algorithm": alg.get("key"),
                        "partitioning_strategy": alg.get("partitioning_strategy"),
                        "coarsening_size": size,
                        "coarsen_inferior_limit": coarsen.get("coarsen_inferior_limit"),
                        "coarsen_superior_limit": coarsen.get("coarsen_superior_limit"),
                        "is_async": alg.get("key") in async_keys,
                        "strategy_parameters": alg.get("strategy_parameters", {}),
                    }
                )
    return cases


# ---------------------------------------------------------------- planning
def is_remote_hardware(strategy: str, params: dict[str, Any] | None) -> bool:
    return strategy != "metis_partitioning" and (params or {}).get("simulated") is False


def capacity_for(strategy: str, params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Largest coarse graph the backend accepts (one qubit per coarse node), or None when unbounded."""
    limit, what = backend_capacity({"partitioning_strategy": strategy, "strategies": {strategy: params or {}}})
    return None if limit is None else {"limit": limit, "what": what}


def qpu_load(strategy: str, params: dict[str, Any] | None, k_target: int) -> dict[str, Any] | None:
    """Remote workload of one case. Recursive bisection to k parts runs k - 1 bipartitions per start."""
    if not is_remote_hardware(strategy, params):
        return None
    return qpu_workload(strategy, params, k_target)
    return None


def _estimate(estimates: dict[str, Any] | None, geometry: str, algorithm: str, size: str) -> dict[str, Any] | None:
    if not estimates:
        return None
    exact = estimates.get("by_case", {}).get(f"{geometry}__{algorithm}__{size}")
    if exact:
        return {"seconds": exact["median_seconds"], "samples": exact["samples"], "basis": "matrix"}
    general = estimates.get("by_algorithm_scale", {}).get(f"{algorithm}__{size}")
    if general:
        return {"seconds": general["median_seconds"], "samples": general["samples"], "basis": "algorithm"}
    return None


def plan(config: dict[str, Any], estimates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cases with capacity checks, QPU load and duration estimates, plus totals for the whole batch."""
    k_target = int((config.get("common_defaults") or {}).get("partitioning_common", {}).get("k_target", 2))
    presets = {alg.get("key"): alg for alg in config.get("algorithm_presets", [])}
    cases = []
    for case in dry_run_cases(config):
        alg = presets[case["algorithm"]]
        strategy, params = alg.get("partitioning_strategy"), alg.get("strategy_parameters")
        max_nodes = case["coarsen_superior_limit"] if case["coarsen_superior_limit"] is not None else case["coarsen_inferior_limit"]
        capacity = capacity_for(strategy, params)
        cases.append(
            {
                **case,
                "remote": is_remote_hardware(strategy, params),
                "max_coarse_nodes": max_nodes,
                "over_capacity": capacity if capacity and max_nodes is not None and max_nodes > capacity["limit"] else None,
                "qpu": qpu_load(strategy, params, k_target),
                "estimate": _estimate(estimates, case["geometry"], case["algorithm"], case["coarsening_size"]),
            }
        )
    return {"cases": cases, "totals": totals(cases)}


def totals(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Blocking duration (async cases run in the background) and remote workload of a set of cases."""
    t = {"seconds": 0.0, "estimated": 0, "missing": 0, "async_count": 0, "submissions": 0, "reads": 0, "shots": 0, "over_capacity": 0}
    for case in cases:
        t["async_count"] += bool(case.get("is_async"))
        t["over_capacity"] += bool(case.get("over_capacity"))
        estimate = case.get("estimate")
        if estimate:
            t["estimated"] += 1
            if not case.get("is_async"):
                t["seconds"] += float(estimate["seconds"])
        else:
            t["missing"] += 1
        qpu = case.get("qpu")
        if qpu:
            t["submissions"] += qpu["submissions"]
            t["reads" if qpu["unit"] == "reads" else "shots"] += qpu["samples"]
    return t


# --------------------------------------------------------------- estimates
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
    """Per-case seconds from batch.log, for cases without manifest timestamps (older batches).

    Async launches are skipped: their work happens in a separate process and log.
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


def duration_estimates(runs_dir: Path | None = None) -> dict[str, Any]:
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
        return {key: {"median_seconds": round(median(vals), 1), "samples": len(vals)} for key, vals in sorted(groups.items())}

    return {
        "by_case": summarize(by_case),
        "by_algorithm_scale": summarize(by_alg_scale),
        "sample_count": len(samples),
        "batch_count": len({s["batch_id"] for s in samples}),
    }


# --------------------------------------------------------------------- runs
def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def list_batch_runs() -> dict[str, Any]:
    runs = []
    root = workspace.batch_runs_dir()
    for bdir in sorted((d for d in root.iterdir() if d.is_dir()), key=lambda p: p.name, reverse=True) if root.exists() else []:
        manifest = _read(bdir / "batch_manifest.json", {})
        summary_rows = _read(bdir / "batch_summary.json", {}).get("rows", [])
        cases = manifest.get("cases", summary_rows)
        runs.append(
            {
                "id": bdir.name,
                "batch_directory": f"batch/runs/{bdir.name}",
                "started_at": manifest.get("batch_started_at"),
                "finished_at": manifest.get("batch_finished_at"),
                "total_cases": len(cases),
                "completed_cases": sum(1 for c in cases if c.get("status") == "completed"),
                "failed_cases": sum(1 for c in cases if c.get("status") == "failed"),
                "running_cases": sum(1 for c in cases if c.get("status") in ("running", "running_async")),
                "geometries": sorted({c.get("geometry") for c in cases if c.get("geometry")}),
                "has_summary": (bdir / "batch_summary.json").exists(),
            }
        )
    return {"batch_runs": runs}


def get_batch_run(batch_id: str) -> dict[str, Any]:
    if not _BATCH_ID_RE.match(batch_id or "") or batch_id in (".", ".."):
        raise InvalidInput(f"Invalid batch id: {batch_id!r}")
    bdir = workspace.batch_runs_dir() / batch_id
    if not bdir.is_dir():
        raise NotFound(f"Batch run {batch_id!r} not found")
    log_path = bdir / "batch.log"
    return {
        "id": batch_id,
        "manifest": _read(bdir / "batch_manifest.json", {}),
        "summary_rows": _read(bdir / "batch_summary.json", {"rows": []}).get("rows", []),
        "configuration": _read(bdir / "batch_configuration.json", {}),
        "batch_log": log_path.read_text(encoding="utf-8", errors="ignore")[-40000:] if log_path.exists() else "",
    }
