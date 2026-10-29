from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from libs.runtime.utils import write_json
from backend.services.job_manager import job_manager

router = APIRouter(prefix="/api/batch", tags=["batch"])

ROOT_DIR = Path(__file__).resolve().parents[2]
BATCH_DIR = ROOT_DIR / "batch"
BATCH_CONFIG_PATH = BATCH_DIR / "batch_configuration.json"
BATCH_RUNS_DIR = BATCH_DIR / "runs"


class StartBatchRequest(BaseModel):
    stop_on_error: bool = False


def _compute_dry_run_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    geometries = config.get("geometries", [])
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
                        "demonstrator_dir": geom.get("demonstrator_dir"),
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
    if not BATCH_CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="batch_configuration.json not found")
    config = json.loads(BATCH_CONFIG_PATH.read_text(encoding="utf-8"))
    cases = _compute_dry_run_cases(config)
    return {
        "configuration": config,
        "dry_run_cases": cases,
        "case_count": len(cases),
    }


@router.put("/config")
def update_batch_configuration(config_payload: dict[str, Any]) -> dict[str, Any]:
    required_keys = {"algorithm_presets", "coarsening_presets", "common_defaults", "geometries"}
    missing = required_keys - set(config_payload.keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required batch configuration keys: {', '.join(sorted(missing))}")

    write_json(BATCH_CONFIG_PATH, config_payload)
    cases = _compute_dry_run_cases(config_payload)
    return {
        "configuration": config_payload,
        "dry_run_cases": cases,
        "case_count": len(cases),
    }


@router.post("/run")
def start_batch_run(req: StartBatchRequest) -> dict[str, Any]:
    return job_manager.start_batch_study(stop_on_error=req.stop_on_error)


@router.get("/runs")
def list_batch_runs() -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    if BATCH_RUNS_DIR.exists():
        for bdir in sorted(BATCH_RUNS_DIR.iterdir(), key=lambda p: p.name, reverse=True):
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
    bdir = BATCH_RUNS_DIR / batch_id
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

