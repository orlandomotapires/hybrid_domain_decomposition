from __future__ import annotations

import importlib.util
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel

from libs.multilevel_scheme.partitioning.qa import (
    get_qlm_qpu_api_summary,
    get_qpu_dense_clique_capacity,
)

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


class DWaveCheckRequest(BaseModel):
    qpu_solver_name: str | None = "Advantage2_system2.1"
    qpu_region: str | None = "eu-central-1"


class QLMInspectRequest(BaseModel):
    qlm_qpu_name: str | None = "qat.qpus:QSolidQPU10"


def _is_installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


@router.get("/status")
def get_environment_status() -> dict[str, Any]:
    packages = {
        "numpy": _is_installed("numpy"),
        "scipy": _is_installed("scipy"),
        "networkx": _is_installed("networkx"),
        "pymetis": _is_installed("pymetis"),
        "pennylane": _is_installed("pennylane"),
        "dwave_neal": _is_installed("neal"),
        "dwave_system": _is_installed("dwave.system"),
        "minorminer": _is_installed("minorminer"),
        "myqlm_qat": _is_installed("qat"),
    }
    return {
        "packages": packages,
        "backends": {
            "metis": {"ready": packages["pymetis"], "description": "Classical weighted multilevel k-way partitioning via PyMETIS"},
            "qa_emulated": {"ready": packages["dwave_neal"], "description": "Local simulated annealing QUBO solver via dwave-neal"},
            "qa_hardware": {
                "ready": packages["dwave_system"] and packages["minorminer"],
                "description": "Remote D-Wave Leap QPU hardware solver via dwave-system",
            },
            "qaoa_emulated": {"ready": packages["pennylane"], "description": "Local gate-based QAOA simulator via PennyLane"},
            "qaoa_hardware": {"ready": packages["myqlm_qat"], "description": "Remote QLM / myQLM gate-based QPU execution"},
        },
    }


@router.post("/dwave-check")
def check_dwave_qpu(req: DWaveCheckRequest) -> dict[str, Any]:
    try:
        solver_name, clique_capacity = get_qpu_dense_clique_capacity(
            req.qpu_solver_name,
            req.qpu_region,
        )
        return {
            "reachable": True,
            "solver_name": solver_name,
            "largest_clique_capacity": clique_capacity,
            "region": req.qpu_region,
            "error": None,
        }
    except Exception as exc:
        return {
            "reachable": False,
            "solver_name": req.qpu_solver_name,
            "largest_clique_capacity": None,
            "region": req.qpu_region,
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.post("/qlm-inspect")
def inspect_qlm_qpu(req: QLMInspectRequest) -> dict[str, Any]:
    summary = get_qlm_qpu_api_summary(qlm_qpu_name=req.qlm_qpu_name)
    reachable = "inspection_error" not in summary
    return {
        "reachable": reachable,
        "requested_qpu_name": req.qlm_qpu_name,
        "summary": summary,
    }

