"""Batch API. Thin adapter over ``hdd.services.batch``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.job_manager import job_manager
from hdd.services import batch

router = APIRouter(prefix="/api/batch", tags=["batch"])

# Kept for callers of the old module.
collect_case_durations = batch.collect_case_durations
compute_duration_estimates = batch.duration_estimates


class StartBatchRequest(BaseModel):
    stop_on_error: bool = False


@router.get("/config")
def get_batch_configuration() -> dict[str, Any]:
    return batch.load_configuration()


@router.put("/config")
def update_batch_configuration(config_payload: dict[str, Any]) -> dict[str, Any]:
    return batch.save_configuration(config_payload)


@router.post("/run")
def start_batch_run(req: StartBatchRequest) -> dict[str, Any]:
    return job_manager.start_batch_study(stop_on_error=req.stop_on_error)


@router.get("/estimates")
def get_batch_estimates() -> dict[str, Any]:
    """Median per-case durations from past batch runs, used to estimate a new batch before launch."""
    return batch.duration_estimates()


@router.get("/runs")
def list_batch_runs() -> dict[str, Any]:
    return batch.list_batch_runs()


@router.get("/runs/{batch_id}")
def get_batch_run_detail(batch_id: str) -> dict[str, Any]:
    return batch.get_batch_run(batch_id)
