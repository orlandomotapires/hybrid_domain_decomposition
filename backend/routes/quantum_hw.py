"""Partitioning backends API. Thin adapter over ``hdd.services.hardware``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from hdd.services import hardware

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


class DWaveCheckRequest(BaseModel):
    qpu_solver_name: str | None = hardware.DEFAULT_DWAVE_SOLVER
    qpu_region: str | None = hardware.DEFAULT_DWAVE_REGION


class QLMInspectRequest(BaseModel):
    qlm_qpu_name: str | None = hardware.DEFAULT_QLM_QPU


@router.get("/status")
def get_environment_status() -> dict[str, Any]:
    return hardware.environment_status()


@router.post("/dwave-check")
def check_dwave_qpu(req: DWaveCheckRequest) -> dict[str, Any]:
    return hardware.probe_dwave(req.qpu_solver_name, req.qpu_region)


@router.post("/qlm-inspect")
def inspect_qlm_qpu(req: QLMInspectRequest) -> dict[str, Any]:
    return hardware.probe_qlm(req.qlm_qpu_name)
