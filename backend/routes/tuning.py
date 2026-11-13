"""Parameter selection API. Thin adapter over ``hdd.services.tuning``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.job_manager import job_manager
from hdd.services import tuning

router = APIRouter(prefix="/api/tuning", tags=["tuning"])


class AutoSelectRequest(BaseModel):
    simulation: str
    parameters: dict[str, Any] | None = None  # unsaved editor state; defaults to the saved file
    apply: bool = False


class StudyRequest(BaseModel):
    simulation: str
    parameters: dict[str, Any] | None = None
    objectives: list[str]
    aggregation: str = "pareto"
    weights: dict[str, float] | None = None
    band_percent: float | None = None
    sampler: str = "auto"
    n_trials: int = 30
    repeats: int = 1
    timeout_sec: float | None = None
    patience: int | None = None
    population_size: int | None = None
    seed: int | None = None
    search_space: dict[str, Any] | None = None
    warm_start: dict[str, bool] | None = None
    start: bool = True  # False = create only (for suggest-next / human-in-the-loop)


class ApplyRequest(BaseModel):
    trial_number: int | None = None  # default: best / knee trial


class SuggestRequest(BaseModel):
    apply: bool = True


class ReportRequest(BaseModel):
    trial_number: int
    run_id: str | None = None  # default: newest run of the simulation after the suggestion


@router.get("/meta")
def tuning_meta() -> dict[str, Any]:
    return tuning.meta()


@router.get("/features/{matrix_id}")
def matrix_features(matrix_id: str, dof_per_node: int = 1) -> dict[str, Any]:
    return tuning.matrix_features(matrix_id, dof_per_node)


@router.get("/defaults/{simulation}")
def study_defaults(simulation: str) -> dict[str, Any]:
    return tuning.study_defaults(simulation)


@router.get("/history")
def history(matrix_id: str | None = None, limit: int = 200) -> dict[str, Any]:
    return tuning.history(matrix_id, limit)


@router.post("/auto-select")
def auto_select(req: AutoSelectRequest) -> dict[str, Any]:
    return tuning.auto_select(req.simulation, req.parameters, req.apply)


@router.get("/studies")
def list_studies(simulation: str | None = None) -> list[dict[str, Any]]:
    return tuning.list_studies(simulation, job_manager)


@router.post("/studies")
def create_study(req: StudyRequest) -> dict[str, Any]:
    return tuning.create_study(req.simulation, req.model_dump(), start=req.start, jobs=job_manager)


@router.get("/studies/{simulation}/{study_id}")
def get_study(simulation: str, study_id: str) -> dict[str, Any]:
    return tuning.get_study(simulation, study_id, job_manager)


@router.post("/studies/{simulation}/{study_id}/resume")
def resume_study(simulation: str, study_id: str, n_trials: int | None = None) -> dict[str, Any]:
    return tuning.resume_study(simulation, study_id, job_manager, n_trials)


@router.post("/studies/{simulation}/{study_id}/stop")
def stop_study(simulation: str, study_id: str) -> dict[str, Any]:
    return tuning.stop_study(simulation, study_id)


@router.post("/studies/{simulation}/{study_id}/apply")
def apply_study(simulation: str, study_id: str, req: ApplyRequest) -> dict[str, Any]:
    return tuning.apply_study(simulation, study_id, req.trial_number)


@router.post("/studies/{simulation}/{study_id}/suggest")
def suggest(simulation: str, study_id: str, req: SuggestRequest) -> dict[str, Any]:
    return tuning.suggest_next(simulation, study_id, req.apply, job_manager)


@router.post("/studies/{simulation}/{study_id}/report")
def report(simulation: str, study_id: str, req: ReportRequest) -> dict[str, Any]:
    return tuning.report_run(simulation, study_id, req.trial_number, req.run_id)


@router.delete("/studies/{simulation}/{study_id}")
def delete_study(simulation: str, study_id: str) -> dict[str, Any]:
    return tuning.delete_study(simulation, study_id, job_manager)
