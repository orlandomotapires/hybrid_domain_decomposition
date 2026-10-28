from __future__ import annotations

import asyncio
from typing import Any
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from libs.runtime.utils import validate_and_normalize_simulation_parameters
from api.services.job_manager import PIPELINE_STAGES, job_manager

router = APIRouter(prefix="/api/execution", tags=["execution"])


class StartSimulationRequest(BaseModel):
    demonstrator_dir: str
    parameters_file_override: str | None = None
    parameters_override: dict[str, Any] | None = None


@router.get("/stages")
def get_pipeline_stages() -> dict[str, Any]:
    return {"stages": PIPELINE_STAGES}


@router.get("/jobs")
def list_jobs() -> dict[str, Any]:
    return {"jobs": job_manager.list_jobs()}


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str, log_offset: int = 0) -> dict[str, Any]:
    job = job_manager.get_job(job_id, log_offset=log_offset)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job


@router.post("/run")
def run_single_simulation(req: StartSimulationRequest) -> dict[str, Any]:
    normalized_override = None
    if req.parameters_override is not None:
        try:
            normalized_override = validate_and_normalize_simulation_parameters(req.parameters_override)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid parameters: {exc}") from exc

    job = job_manager.start_single_simulation(
        req.demonstrator_dir,
        parameters_override=normalized_override,
        parameters_file_override=req.parameters_file_override,
    )
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_running_job(job_id: str) -> dict[str, Any]:
    job = job_manager.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return job


@router.delete("/jobs/{job_id}")
def delete_job_record(job_id: str, delete_files: bool = False) -> dict[str, Any]:
    ok = job_manager.delete_job(job_id, delete_files=delete_files)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Cannot delete job {job_id!r}")
    return {"deleted": job_id}


@router.websocket("/ws/{job_id}")
async def stream_job_logs(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    offset = 0
    try:
        while True:
            snapshot = job_manager.get_job(job_id, log_offset=offset)
            if snapshot is None:
                await websocket.send_json({"error": f"Job {job_id} not found"})
                break

            new_logs = snapshot.get("logs", [])
            if new_logs or offset == 0:
                await websocket.send_json(snapshot)
                offset = int(snapshot.get("log_count", offset))

            if snapshot.get("status") in ("completed", "failed", "cancelled"):
                await websocket.send_json(snapshot)
                break

            await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        return

