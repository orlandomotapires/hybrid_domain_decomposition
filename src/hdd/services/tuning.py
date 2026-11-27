"""Parameter selection: rule-based auto-selection, Optuna studies and human-in-the-loop suggestions.

Studies live in ``simulations/<id>/tuning/study_*``. Functions that start or inspect running
studies take ``jobs``, the job manager of the calling application.
Optuna and the tuning internals are imported on first use, not at import time.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from libs.runtime import workspace
from libs.runtime.atomic import atomic_write_json
from libs.runtime.utils import resolve_parameters_file_path, validate_and_normalize_simulation_config

from . import simulations
from .errors import Conflict, InvalidInput, NotFound

SAMPLERS = [
    {"key": "auto", "label": "Auto", "description": "TPE for one objective / weighted, NSGA-II for Pareto"},
    {"key": "tpe", "label": "Bayesian (TPE)", "description": "Sample-efficient; best for expensive runs (QA/QAOA)"},
    {"key": "nsga2", "label": "Genetic (NSGA-II)", "description": "Population based; natural for Pareto fronts"},
    {"key": "cmaes", "label": "CMA-ES", "description": "Evolution strategy for continuous parameters (single objective)"},
    {"key": "qmc", "label": "Quasi-random (Sobol)", "description": "Space-filling exploration baseline"},
    {"key": "random", "label": "Random", "description": "Baseline"},
]


class Jobs(Protocol):
    def list_jobs(self, limit: int | None = 40) -> list[dict[str, Any]]: ...

    def start_tuning_study(self, *, study_dir: Path, title: str, demonstrator_id: str | None = None) -> dict[str, Any]: ...


def _tuner():
    from libs.tuning import tuner

    return tuner


# ------------------------------------------------------------------ helpers
def simulation_dir(simulation: str) -> Path:
    path = workspace.simulations_dir() / simulations.sanitize_simulation_id(simulation)
    if not path.exists():
        raise NotFound(f"Simulation {simulation!r} not found")
    return path


def simulation_inputs(simulation: str) -> tuple[str, dict[str, Any]]:
    """Matrix id and saved (active) parameters of a simulation."""
    data_dir = simulation_dir(simulation) / "data"
    cfg = validate_and_normalize_simulation_config(json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8")))
    params = json.loads(resolve_parameters_file_path(data_dir, cfg["parameters_file_path"]).read_text(encoding="utf-8"))
    return cfg["input_matrix"], params


def study_dir(simulation: str, study_id: str) -> Path:
    if not study_id.startswith("study_") or "/" in study_id or ".." in study_id:
        raise InvalidInput("Invalid study id")
    path = simulation_dir(simulation) / "tuning" / study_id
    if not (path / _tuner().STUDY_CONFIG).exists():
        raise NotFound(f"Study {study_id!r} not found")
    _tuner().migrate_legacy_study(path)
    return path


def _read(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def running_job_for(jobs: Jobs | None, path: Path) -> dict[str, Any] | None:
    if jobs is None:
        return None
    rel = workspace.rel(path)
    # Scan every job: a long study can be older than the newest 40 and must still count as running.
    for job in jobs.list_jobs(limit=None):
        if job.get("job_type") == "tuning" and job.get("study_dir") == rel and job.get("status") == "running":
            return job
    return None


def study_brief(simulation: str, path: Path, jobs: Jobs | None = None) -> dict[str, Any]:
    tuner = _tuner()
    config = _read(path / tuner.STUDY_CONFIG, {}) or {}
    job = running_job_for(jobs, path)
    return {
        "id": path.name,
        "simulation": simulation,
        "matrix_id": config.get("matrix_id"),
        "objectives": config.get("objectives"),
        "aggregation": config.get("aggregation"),
        "sampler": config.get("sampler"),
        "n_trials": config.get("n_trials"),
        "free_parameters": [k for k, v in (config.get("search_space") or {}).items() if v.get("free")],
        "summary": _read(path / tuner.SUMMARY, {}) or {},
        "running_job_id": job["job_id"] if job else None,
    }


def apply_parameters(simulation: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return simulations.save_parameters(simulations.sanitize_simulation_id(simulation), parameters)


# --------------------------------------------------------- metadata / features
def meta() -> dict[str, Any]:
    from libs.tuning.objectives import OBJECTIVES
    from libs.tuning.search_space import describe_parameters

    return {"objectives": [{"key": k, **v} for k, v in OBJECTIVES.items()], "samplers": SAMPLERS, "parameters": describe_parameters()}


def matrix_features(matrix_id: str, dof_per_node: int = 1) -> dict[str, Any]:
    from libs.tuning.features import compute_matrix_features

    try:
        return compute_matrix_features(matrix_id, dof_per_node)
    except FileNotFoundError as exc:
        raise NotFound(str(exc)) from exc
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc


def study_defaults(simulation: str) -> dict[str, Any]:
    """Base parameters, matrix features and a search space adapted to the matrix."""
    from libs.runtime.utils import validate_and_normalize_simulation_parameters
    from libs.tuning.features import compute_matrix_features
    from libs.tuning.search_space import default_search_space

    matrix_id, params = simulation_inputs(simulation)
    try:
        normalized = validate_and_normalize_simulation_parameters(params)
        features = compute_matrix_features(matrix_id, int(normalized["general_parameters"]["dof_per_node"]))
    except (ValueError, FileNotFoundError) as exc:
        raise InvalidInput(str(exc)) from exc
    return {
        "simulation": simulation,
        "matrix_id": matrix_id,
        "parameters": params,
        "features": features,
        "search_space": default_search_space(normalized, features),
    }


def history(matrix_id: str | None = None, limit: int = 200) -> dict[str, Any]:
    from libs.tuning.history import load_history

    rows = load_history(matrix_id)
    return {"count": len(rows), "rows": rows[-limit:]}


# ------------------------------------------------------- Mode A: auto-select
def auto_select(simulation: str, parameters: dict[str, Any] | None = None, apply: bool = False) -> dict[str, Any]:
    from libs.tuning.auto_select import auto_select_parameters

    matrix_id, saved = simulation_inputs(simulation)
    try:
        result = auto_select_parameters(matrix_id, parameters or saved)
    except (ValueError, FileNotFoundError) as exc:
        raise InvalidInput(str(exc)) from exc
    if apply and result["feasible"]:
        apply_parameters(simulation, result["parameters"])
        result["applied"] = True
    return result


# ----------------------------------------------------------- Mode B: studies
def list_studies(simulation: str | None = None, jobs: Jobs | None = None) -> list[dict[str, Any]]:
    tuner = _tuner()
    root = workspace.simulations_dir()
    sims = [simulation_dir(simulation)] if simulation else (sorted(d for d in root.iterdir() if d.is_dir()) if root.exists() else [])
    out = []
    for sim in sims:
        for path in sorted((sim / "tuning").glob("study_*"), reverse=True):
            if (path / tuner.STUDY_CONFIG).exists():
                out.append(study_brief(sim.name, path, jobs))
    return out


def create_study(simulation: str, request: dict[str, Any], *, start: bool = True, jobs: Jobs | None = None) -> dict[str, Any]:
    """Create a study from ``request`` (objectives, sampler, search space...) and optionally start it."""
    tuner = _tuner()
    matrix_id, saved = simulation_inputs(simulation)
    raw = {k: v for k, v in request.items() if v is not None and k not in ("simulation", "parameters", "start")}
    raw.update({"simulation": simulation, "matrix_id": matrix_id, "base_parameters": request.get("parameters") or saved})
    try:
        config = tuner.normalize_study_config(raw)
    except (ValueError, FileNotFoundError) as exc:
        raise InvalidInput(str(exc)) from exc
    path = tuner.create_study_dir(config, parent=simulation_dir(simulation) / "tuning")
    job = None
    if start:
        if jobs is None:
            raise InvalidInput("Starting a study needs a job manager")
        job = jobs.start_tuning_study(
            study_dir=path, title=f"Tuning {simulation} ({', '.join(config['objectives'])})", demonstrator_id=simulation
        )
    return {"study": study_brief(simulation, path, jobs), "job": job}


def get_study(simulation: str, study_id: str, jobs: Jobs | None = None) -> dict[str, Any]:
    tuner = _tuner()
    path = study_dir(simulation, study_id)
    return {
        **study_brief(simulation, path, jobs),
        "config": _read(path / tuner.STUDY_CONFIG, {}),
        "trials": tuner.load_trials(path),
        "pending": _read(path / tuner.PENDING, {}) or {},
        "best_parameters": _read(path / tuner.BEST),
    }


def resume_study(simulation: str, study_id: str, jobs: Jobs, n_trials: int | None = None) -> dict[str, Any]:
    tuner = _tuner()
    path = study_dir(simulation, study_id)
    if running_job_for(jobs, path):
        raise Conflict("Study is already running")
    if n_trials is not None:
        config = _read(path / tuner.STUDY_CONFIG)
        config["n_trials"] = max(int(n_trials), len(tuner.load_trials(path)) + 1)
        atomic_write_json(path / tuner.STUDY_CONFIG, config)
    (path / tuner.STOP_FILE).unlink(missing_ok=True)
    job = jobs.start_tuning_study(study_dir=path, title=f"Tuning {simulation} ({study_id})", demonstrator_id=simulation)
    return {"study": study_brief(simulation, path, jobs), "job": job}


def stop_study(simulation: str, study_id: str) -> dict[str, Any]:
    """Ask a running study to stop after its current trial."""
    path = study_dir(simulation, study_id)
    (path / _tuner().STOP_FILE).write_text(datetime.now().isoformat(), encoding="utf-8")
    return {"stopping": True}


def apply_study(simulation: str, study_id: str, trial_number: int | None = None) -> dict[str, Any]:
    """Write the best (or a chosen) trial's parameters into the simulation."""
    tuner = _tuner()
    path = study_dir(simulation, study_id)
    if trial_number is None:
        params = _read(path / tuner.BEST)
        if not params:
            raise InvalidInput("Study has no successful trial yet")
    else:
        row = next((t for t in tuner.load_trials(path) if t.get("number") == trial_number), None)
        if row is None or row.get("status") != "ok":
            raise InvalidInput(f"Trial {trial_number} has no successful run")
        params = row["parameters"]
    return apply_parameters(simulation, params)


def suggest_next(simulation: str, study_id: str, apply: bool = True, jobs: Jobs | None = None) -> dict[str, Any]:
    path = study_dir(simulation, study_id)
    if running_job_for(jobs, path):
        raise Conflict("Stop the running study before asking for manual suggestions")
    try:
        result = _tuner().suggest_next(path)
    except (RuntimeError, ValueError) as exc:
        raise InvalidInput(str(exc)) from exc
    if apply:
        apply_parameters(simulation, result["parameters"])
        result["applied"] = True
    return result


def report_run(simulation: str, study_id: str, trial_number: int, run_id: str | None = None) -> dict[str, Any]:
    """Score a finished run of the simulation as the result of a pending (suggested) trial."""
    tuner = _tuner()
    path = study_dir(simulation, study_id)
    results_dir = simulation_dir(simulation) / "results"
    if run_id:
        run_dir = results_dir / Path(run_id).name
    else:
        pending = (_read(path / tuner.PENDING, {}) or {}).get(str(trial_number))
        if pending is None:
            raise InvalidInput(f"Trial {trial_number} is not pending")
        created = datetime.fromisoformat(pending["created_at"]).timestamp()
        runs = [
            r for r in results_dir.glob("run_*")
            if r.is_dir() and r.stat().st_mtime >= created and (r / "decomposition_metrics.json").exists()
        ]
        if not runs:
            raise InvalidInput("No finished run of this simulation since the suggestion; run it first")
        run_dir = max(runs, key=lambda r: r.stat().st_mtime)
    if not run_dir.exists():
        raise NotFound(f"Run {run_id!r} not found")
    try:
        summary = tuner.report_run(path, trial_number, run_dir)
    except (ValueError, KeyError) as exc:
        raise InvalidInput(f"Could not score run: {exc}") from exc
    return {"summary": summary, "run_id": run_dir.name}


def delete_study(simulation: str, study_id: str, jobs: Jobs | None = None) -> dict[str, Any]:
    path = study_dir(simulation, study_id)
    if running_job_for(jobs, path):
        raise Conflict("Stop the study before deleting it")
    shutil.rmtree(path)
    return {"deleted": study_id}
