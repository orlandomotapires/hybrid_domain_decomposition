"""Parameter selection subsystem: auto-select (Mode A), Optuna studies (Mode B), suggest-next."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from libs.runtime import workspace
from backend.routes.matrices import _sanitize_dem_name, update_simulation_parameters
from backend.services.job_manager import job_manager
from libs.runtime.utils import resolve_parameters_file_path, validate_and_normalize_simulation_config
from libs.tuning import tuner
from libs.tuning.history import load_history
from libs.tuning.objectives import OBJECTIVES
from libs.tuning.search_space import default_search_space, describe_parameters

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


# --------------------------------------------------------------------------- helpers

def _sim_dir(simulation: str) -> Path:
    sim_dir = workspace.simulations_dir() / _sanitize_dem_name(simulation)
    if not sim_dir.exists():
        raise HTTPException(status_code=404, detail=f"Simulation {simulation!r} not found")
    return sim_dir


def _sim_inputs(simulation: str) -> tuple[str, dict[str, Any]]:
    data_dir = _sim_dir(simulation) / "data"
    cfg = validate_and_normalize_simulation_config(json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8")))
    params = json.loads(resolve_parameters_file_path(data_dir, cfg["parameters_file_path"]).read_text(encoding="utf-8"))
    return cfg["input_matrix"], params


def _study_dir(simulation: str, study_id: str) -> Path:
    if not study_id.startswith("study_") or "/" in study_id or ".." in study_id:
        raise HTTPException(status_code=400, detail="Invalid study id")
    d = _sim_dir(simulation) / "tuning" / study_id
    if not (d / tuner.STUDY_CONFIG).exists():
        raise HTTPException(status_code=404, detail=f"Study {study_id!r} not found")
    return d


def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _running_job_for(study_dir: Path) -> dict[str, Any] | None:
    rel = str(study_dir.resolve().relative_to(workspace.root()))
    for job in job_manager.list_jobs():
        if job.get("job_type") == "tuning" and job.get("study_dir") == rel and job.get("status") == "running":
            return job
    return None


def _study_brief(simulation: str, study_dir: Path) -> dict[str, Any]:
    config = _read(study_dir / tuner.STUDY_CONFIG, {}) or {}
    summary = _read(study_dir / tuner.SUMMARY, {}) or {}
    job = _running_job_for(study_dir)
    return {
        "id": study_dir.name,
        "simulation": simulation,
        "matrix_id": config.get("matrix_id"),
        "objectives": config.get("objectives"),
        "aggregation": config.get("aggregation"),
        "sampler": config.get("sampler"),
        "n_trials": config.get("n_trials"),
        "free_parameters": [k for k, v in (config.get("search_space") or {}).items() if v.get("free")],
        "summary": summary,
        "running_job_id": job["job_id"] if job else None,
    }


def _apply_parameters(simulation: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return update_simulation_parameters(_sanitize_dem_name(simulation), parameters)


# --------------------------------------------------------------------------- metadata / features

@router.get("/meta")
def tuning_meta() -> dict[str, Any]:
    return {
        "objectives": [{"key": k, **v} for k, v in OBJECTIVES.items()],
        "samplers": [
            {"key": "auto", "label": "Auto", "description": "TPE for one objective / weighted, NSGA-II for Pareto"},
            {"key": "tpe", "label": "Bayesian (TPE)", "description": "Sample-efficient; best for expensive runs (QA/QAOA)"},
            {"key": "nsga2", "label": "Genetic (NSGA-II)", "description": "Population based; natural for Pareto fronts"},
            {"key": "cmaes", "label": "CMA-ES", "description": "Evolution strategy for continuous parameters (single objective)"},
            {"key": "qmc", "label": "Quasi-random (Sobol)", "description": "Space-filling exploration baseline"},
            {"key": "random", "label": "Random", "description": "Baseline"},
        ],
        "parameters": describe_parameters(),
    }


@router.get("/features/{matrix_id}")
def matrix_features(matrix_id: str, dof_per_node: int = 1) -> dict[str, Any]:
    from libs.tuning.features import compute_matrix_features

    try:
        return compute_matrix_features(matrix_id, dof_per_node)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/defaults/{simulation}")
def study_defaults(simulation: str) -> dict[str, Any]:
    """Base parameters, matrix features and a search space adapted to the matrix."""
    from libs.runtime.utils import validate_and_normalize_simulation_parameters
    from libs.tuning.features import compute_matrix_features

    matrix_id, params = _sim_inputs(simulation)
    try:
        normalized = validate_and_normalize_simulation_parameters(params)
        features = compute_matrix_features(matrix_id, int(normalized["general_parameters"]["dof_per_node"]))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "simulation": simulation,
        "matrix_id": matrix_id,
        "parameters": params,
        "features": features,
        "search_space": default_search_space(normalized, features),
    }


@router.get("/history")
def history(matrix_id: str | None = None, limit: int = 200) -> dict[str, Any]:
    rows = load_history(matrix_id)
    return {"count": len(rows), "rows": rows[-limit:]}


# --------------------------------------------------------------------------- Mode A

@router.post("/auto-select")
def auto_select(req: AutoSelectRequest) -> dict[str, Any]:
    from libs.tuning.auto_select import auto_select_parameters

    matrix_id, saved = _sim_inputs(req.simulation)
    try:
        result = auto_select_parameters(matrix_id, req.parameters or saved)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.apply and result["feasible"]:
        _apply_parameters(req.simulation, result["parameters"])
        result["applied"] = True
    return result


# --------------------------------------------------------------------------- Mode B

@router.get("/studies")
def list_studies(simulation: str | None = None) -> list[dict[str, Any]]:
    sims = [_sim_dir(simulation)] if simulation else sorted(d for d in workspace.simulations_dir().iterdir() if d.is_dir())
    out = []
    for sim in sims:
        tdir = sim / "tuning"
        if not tdir.exists():
            continue
        for d in sorted(tdir.glob("study_*"), reverse=True):
            if (d / tuner.STUDY_CONFIG).exists():
                out.append(_study_brief(sim.name, d))
    return out


@router.post("/studies")
def create_study(req: StudyRequest) -> dict[str, Any]:
    matrix_id, saved = _sim_inputs(req.simulation)
    raw = req.model_dump(exclude={"start", "parameters"}, exclude_none=True)
    raw.update({"matrix_id": matrix_id, "base_parameters": req.parameters or saved})
    try:
        config = tuner.normalize_study_config(raw)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    study_dir = tuner.create_study_dir(config, parent=_sim_dir(req.simulation) / "tuning")
    job = None
    if req.start:
        job = job_manager.start_tuning_study(
            study_dir=study_dir,
            title=f"Tuning {req.simulation} ({', '.join(config['objectives'])})",
            demonstrator_id=req.simulation,
        )
    return {"study": _study_brief(req.simulation, study_dir), "job": job}


@router.get("/studies/{simulation}/{study_id}")
def get_study(simulation: str, study_id: str) -> dict[str, Any]:
    d = _study_dir(simulation, study_id)
    return {
        **_study_brief(simulation, d),
        "config": _read(d / tuner.STUDY_CONFIG, {}),
        "trials": tuner.load_trials(d),
        "pending": _read(d / tuner.PENDING, {}) or {},
        "best_parameters": _read(d / tuner.BEST),
    }


@router.post("/studies/{simulation}/{study_id}/resume")
def resume_study(simulation: str, study_id: str, n_trials: int | None = None) -> dict[str, Any]:
    d = _study_dir(simulation, study_id)
    if _running_job_for(d):
        raise HTTPException(status_code=409, detail="Study is already running")
    if n_trials is not None:
        config = _read(d / tuner.STUDY_CONFIG)
        config["n_trials"] = max(int(n_trials), len(tuner.load_trials(d)) + 1)
        (d / tuner.STUDY_CONFIG).write_text(json.dumps(config, indent=2), encoding="utf-8")
    (d / tuner.STOP_FILE).unlink(missing_ok=True)
    job = job_manager.start_tuning_study(study_dir=d, title=f"Tuning {simulation} ({study_id})", demonstrator_id=simulation)
    return {"study": _study_brief(simulation, d), "job": job}


@router.post("/studies/{simulation}/{study_id}/stop")
def stop_study(simulation: str, study_id: str) -> dict[str, Any]:
    d = _study_dir(simulation, study_id)
    (d / tuner.STOP_FILE).write_text(datetime.now().isoformat(), encoding="utf-8")
    return {"stopping": True}


@router.post("/studies/{simulation}/{study_id}/apply")
def apply_study(simulation: str, study_id: str, req: ApplyRequest) -> dict[str, Any]:
    d = _study_dir(simulation, study_id)
    if req.trial_number is None:
        params = _read(d / tuner.BEST)
        if not params:
            raise HTTPException(status_code=400, detail="Study has no successful trial yet")
    else:
        row = next((t for t in tuner.load_trials(d) if t.get("number") == req.trial_number), None)
        if row is None or row.get("status") != "ok":
            raise HTTPException(status_code=400, detail=f"Trial {req.trial_number} has no successful run")
        params = row["parameters"]
    return _apply_parameters(simulation, params)


@router.post("/studies/{simulation}/{study_id}/suggest")
def suggest(simulation: str, study_id: str, req: SuggestRequest) -> dict[str, Any]:
    d = _study_dir(simulation, study_id)
    if _running_job_for(d):
        raise HTTPException(status_code=409, detail="Stop the running study before asking for manual suggestions")
    try:
        result = tuner.suggest_next(d)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.apply:
        _apply_parameters(simulation, result["parameters"])
        result["applied"] = True
    return result


@router.post("/studies/{simulation}/{study_id}/report")
def report(simulation: str, study_id: str, req: ReportRequest) -> dict[str, Any]:
    d = _study_dir(simulation, study_id)
    results_dir = _sim_dir(simulation) / "results"
    if req.run_id:
        run_dir = results_dir / Path(req.run_id).name
    else:
        pending = (_read(d / tuner.PENDING, {}) or {}).get(str(req.trial_number))
        if pending is None:
            raise HTTPException(status_code=400, detail=f"Trial {req.trial_number} is not pending")
        created = datetime.fromisoformat(pending["created_at"]).timestamp()
        runs = [r for r in results_dir.glob("run_*") if r.is_dir() and r.stat().st_mtime >= created
                and (r / "decomposition_metrics.json").exists()]
        if not runs:
            raise HTTPException(status_code=400, detail="No finished run of this simulation since the suggestion; run it first")
        run_dir = max(runs, key=lambda r: r.stat().st_mtime)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run {req.run_id!r} not found")
    try:
        summary = tuner.report_run(d, req.trial_number, run_dir)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not score run: {exc}") from exc
    return {"summary": summary, "run_id": run_dir.name}


@router.delete("/studies/{simulation}/{study_id}")
def delete_study(simulation: str, study_id: str) -> dict[str, Any]:
    d = _study_dir(simulation, study_id)
    if _running_job_for(d):
        raise HTTPException(status_code=409, detail="Stop the study before deleting it")
    shutil.rmtree(d)
    return {"deleted": study_id}
