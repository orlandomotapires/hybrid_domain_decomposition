"""Mode B: iterative tuning with Optuna (ask/tell), plus the human-in-the-loop "suggest next".

A study lives in a folder (``simulations/<sim>/tuning/study_<ts>/``)::

    study_config.json     what the user asked for (objectives, sampler, search space, budget)
    study.db              Optuna storage (SQLite), so studies can be resumed
    trials.jsonl          one line per trial: parameters, objective values, status, run folders
    summary.json          progress, best trial / Pareto front, reference values
    best_parameters.json  full parameter set of the best (or Pareto "knee") trial
    trials/trial_000/...  normal run folders produced by ``run_simulation``
    STOP                  created by the Studio to stop after the current trial

Progress is printed as ``[tuning] trial i/N ...`` lines and reported to the Studio as ``trial`` events.
"""

from __future__ import annotations

import copy
import json
import math
import statistics
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from libs.multilevel_scheme.partitioning.utils.metrics import legacy_tolerance_percent
from libs.runtime import events, workspace
from libs.runtime.matrix_library import resolve_matrix
from libs.runtime.utils import load_mtx, validate_and_normalize_simulation_parameters
from libs.tuning import history as history_mod
from libs.tuning.feasibility import check_feasibility
from libs.tuning.features import build_pipeline_graph, compute_matrix_features
from libs.tuning.objectives import (
    DEFAULT_BAND_PERCENT,
    objective_values,
    read_run_metrics,
    validate_objectives,
    weighted_score,
)
from libs.tuning.search_space import (
    distributions_for,
    fixed_keys_match,
    normalize_search_space,
    parameters_to_trial_values,
    suggest_parameters,
    trial_values_in_range,
)

SAMPLERS = ["auto", "tpe", "nsga2", "random", "qmc", "cmaes"]
PENALTY = 1e6
MAX_CONSECUTIVE_ERRORS = 5

STUDY_CONFIG = "study_config.json"
SUMMARY = "summary.json"
TRIALS = "trials.jsonl"
BEST = "best_parameters.json"
STOP_FILE = "STOP"
PENDING = "pending_suggestions.json"
# Unit of balance_tolerance in this study's files. Studies without it predate the percent-only rule.
TOLERANCE_UNIT = "percent"


# --------------------------------------------------------------------------- configuration

def normalize_study_config(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Study config must be an object")
    matrix_id = raw.get("matrix_id")
    if not isinstance(matrix_id, str) or not matrix_id:
        raise ValueError("matrix_id is required")
    raw_base = copy.deepcopy(raw.get("base_parameters") or {})
    base = validate_and_normalize_simulation_parameters(copy.deepcopy(raw_base))
    # The validator keeps only the active strategy block; keep the others so a free
    # partitioning_strategy starts from the user's settings for every backend.
    raw_strategies = (raw_base.get("partitioning_parameters") or {}).get("strategies") or {}
    base["partitioning_parameters"]["strategies"] = {**raw_strategies, **base["partitioning_parameters"]["strategies"]}
    objectives = validate_objectives(raw.get("objectives") or ["edge_cut"])
    aggregation = str(raw.get("aggregation") or "pareto")
    if aggregation not in ("pareto", "weighted"):
        raise ValueError("aggregation must be 'pareto' or 'weighted'")
    if len(objectives) == 1:
        aggregation = "weighted"
    weights = {o: float((raw.get("weights") or {}).get(o, 1.0)) for o in objectives}
    if any(w < 0 for w in weights.values()):
        raise ValueError("Objective weights must be >= 0")
    sampler = str(raw.get("sampler") or "auto").lower()
    if sampler not in SAMPLERS:
        raise ValueError(f"sampler must be one of {SAMPLERS}")
    multi = aggregation == "pareto" and len(objectives) > 1
    if sampler == "cmaes" and multi:
        raise ValueError("CMA-ES only supports a single objective (use weighted aggregation)")
    if sampler == "auto":
        sampler = "nsga2" if multi else "tpe"

    dof = int(base["general_parameters"]["dof_per_node"])
    features = compute_matrix_features(matrix_id, dof)
    space = normalize_search_space(raw.get("search_space"), base, features)

    n_trials = int(raw.get("n_trials") or 30)
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    repeats = max(1, int(raw.get("repeats") or 1))
    timeout = raw.get("timeout_sec")
    patience = raw.get("patience")
    warm = raw.get("warm_start") or {}
    return {
        "matrix_id": matrix_id,
        "simulation": raw.get("simulation"),
        "base_parameters": base,
        "objectives": objectives,
        "aggregation": aggregation,
        "weights": weights,
        "band_percent": float(raw.get("band_percent") or DEFAULT_BAND_PERCENT),
        "sampler": sampler,
        "population_size": int(raw.get("population_size") or 20),
        "n_trials": n_trials,
        "timeout_sec": float(timeout) if timeout not in (None, "") else None,
        "patience": int(patience) if patience not in (None, "") else None,
        "repeats": repeats,
        "seed": int(raw.get("seed") if raw.get("seed") is not None else 0),
        "search_space": space,
        "tolerance_unit": TOLERANCE_UNIT,
        "warm_start": {
            "base": bool(warm.get("base", True)),
            "auto": bool(warm.get("auto", True)),
            "history": bool(warm.get("history", True)),
        },
    }


def is_multi_objective(config: dict[str, Any]) -> bool:
    return config["aggregation"] == "pareto" and len(config["objectives"]) > 1


def create_study_dir(config: dict[str, Any], parent: Path | None = None) -> Path:
    """Write a normalized config into a new study folder and return it."""
    if parent is None:
        sim = config.get("simulation")
        parent = (workspace.simulations_dir() / sim / "tuning") if sim else (workspace.tuning_dir() / "studies")
    parent.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("study_%Y%m%d_%H%M%S")
    study_dir = parent / name
    suffix = 1
    while study_dir.exists():
        study_dir = parent / f"{name}_{suffix:02d}"
        suffix += 1
    study_dir.mkdir()
    _write_json(study_dir / STUDY_CONFIG, config)
    _write_json(study_dir / SUMMARY, {"state": "created", "created_at": _now(), "trials_done": 0, "n_trials": config["n_trials"]})
    return study_dir


# --------------------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=float), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_trials(study_dir: Path) -> list[dict[str, Any]]:
    path = Path(study_dir) / TRIALS
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _legacy_tolerance_to_percent(params: Any) -> None:
    common = ((params or {}).get("partitioning_parameters") or {}).get("common") if isinstance(params, dict) else None
    if isinstance(common, dict) and isinstance(common.get("balance_tolerance"), (int, float)):
        common["balance_tolerance"] = legacy_tolerance_percent(common["balance_tolerance"])


def migrate_legacy_study(study_dir: str | Path) -> bool:
    """Rewrite a study created before ``balance_tolerance`` became percent-only. Idempotent.

    Converts the search range, the base parameters, the best and pending parameter sets and the
    trial log. Trials already stored in Optuna's database keep their old values, so the sampler
    learns less from them, but every run from now on uses the correct unit.
    """
    study_dir = Path(study_dir)
    config = _read_json(study_dir / STUDY_CONFIG)
    if not isinstance(config, dict) or config.get("tolerance_unit") == TOLERANCE_UNIT:
        return False
    entry = (config.get("search_space") or {}).get("balance_tolerance")
    if isinstance(entry, dict) and "high" in entry and float(entry["high"]) <= 1.0:
        entry["low"], entry["high"] = float(entry["low"]) * 100.0, float(entry["high"]) * 100.0
    _legacy_tolerance_to_percent(config.get("base_parameters"))

    best = _read_json(study_dir / BEST)
    if isinstance(best, dict):
        _legacy_tolerance_to_percent(best)
        _write_json(study_dir / BEST, best)
    pending = _read_json(study_dir / PENDING)
    if isinstance(pending, dict):
        for item in pending.values():
            if isinstance(item, dict):
                _legacy_tolerance_to_percent(item.get("parameters"))
        _write_json(study_dir / PENDING, pending)
    trials = load_trials(study_dir)
    if trials:
        for row in trials:
            _legacy_tolerance_to_percent(row.get("parameters"))
        tmp = study_dir / (TRIALS + ".tmp")
        tmp.write_text("".join(json.dumps(row, default=float) + "\n" for row in trials), encoding="utf-8")
        tmp.replace(study_dir / TRIALS)

    config["tolerance_unit"] = TOLERANCE_UNIT
    _write_json(study_dir / STUDY_CONFIG, config)  # last: an interrupted migration runs again
    return True


def _load_config(study_dir: Path) -> dict[str, Any] | None:
    migrate_legacy_study(study_dir)
    return _read_json(study_dir / STUDY_CONFIG)


def _append_trial(study_dir: Path, row: dict[str, Any]) -> None:
    with (study_dir / TRIALS).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=float) + "\n")


def _make_sampler(config: dict[str, Any]):
    import optuna

    import warnings

    warnings.filterwarnings("ignore", category=optuna.exceptions.ExperimentalWarning)
    seed = config["seed"]
    # Infeasible trials carry trial.set_constraint("infeasible", 1.0); TPE/NSGA-II rank them last.
    name = config["sampler"]
    if name == "tpe":
        return optuna.samplers.TPESampler(seed=seed, multivariate=True, group=True)
    if name == "nsga2":
        return optuna.samplers.NSGAIISampler(seed=seed, population_size=config["population_size"])
    if name == "random":
        return optuna.samplers.RandomSampler(seed=seed)
    if name == "qmc":
        return optuna.samplers.QMCSampler(seed=seed, warn_independent_sampling=False)
    if name == "cmaes":
        return optuna.samplers.CmaEsSampler(seed=seed, warn_independent_sampling=False)
    raise ValueError(name)


def open_study(study_dir: Path, config: dict[str, Any]):
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    directions = ["minimize"] * (len(config["objectives"]) if is_multi_objective(config) else 1)
    return optuna.create_study(
        study_name="hdd",
        storage=f"sqlite:///{Path(study_dir).resolve() / 'study.db'}",
        sampler=_make_sampler(config),
        directions=directions,
        load_if_exists=True,
    )


class _Context:
    """Matrix graph + reference values shared by all trials of a study."""

    def __init__(self, study_dir: Path, config: dict[str, Any]):
        self.study_dir = Path(study_dir)
        self.config = config
        matrix_id = config["matrix_id"]
        self.matrix = load_mtx(str(resolve_matrix(matrix_id)), matrix_id)
        self.graphs: dict[tuple[int, str], Any] = {}
        summary = _read_json(self.study_dir / SUMMARY, {}) or {}
        self.reference: dict[str, float] | None = summary.get("reference")

    def graph(self, params: dict[str, Any]):
        key = (int(params["general_parameters"]["dof_per_node"]), str(params["coarsening_parameters"].get("weight", "weight")))
        if key not in self.graphs:
            self.graphs[key] = build_pipeline_graph(self.matrix, *key)
        return self.graphs[key]


def _evaluate(ctx: _Context, params: dict[str, Any], trial_number: int) -> dict[str, Any]:
    """Feasibility check + ``repeats`` pipeline runs. Returns status, objective values, run dirs."""
    from libs.runtime.runtime import run_simulation

    config = ctx.config
    try:
        params = validate_and_normalize_simulation_parameters(params)
    except ValueError as exc:
        return {"status": "infeasible", "reasons": [str(exc)], "parameters": params}
    feas = check_feasibility(ctx.graph(params), params)
    if not feas["feasible"]:
        return {"status": "infeasible", "reasons": feas["reasons"], "parameters": params, "dry_run": feas["dry_run"]}

    per_repeat: list[dict[str, float]] = []
    run_dirs: list[str] = []
    errors: list[str] = []
    for r in range(config["repeats"]):
        run_params = copy.deepcopy(params)
        run_params["general_parameters"]["seed"] = int(params["general_parameters"]["seed"]) + r
        try:
            run_dir = run_simulation(
                None,
                simulation_parameters_override=run_params,
                simulation_config_override={
                    "input_matrix": config["matrix_id"],
                    "parameters_file_path": "tuning_parameters.json",
                    "save_output": ["run_metrics", "run_simulation_parameters"],
                },
                results_dir_override=ctx.study_dir / "trials" / f"trial_{trial_number:03d}",
                run_label=f"tuning trial {trial_number} (repeat {r + 1}/{config['repeats']})",
                history_source="tuning",
            )
        except Exception as exc:  # pipeline failure counts as an infeasible point
            errors.append(f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
            continue
        run_dirs.append(str(run_dir))
        per_repeat.append(objective_values(read_run_metrics(run_dir), config["objectives"], band_percent=config["band_percent"]))

    if not per_repeat:
        return {"status": "error", "reasons": errors, "parameters": params, "run_dirs": run_dirs}
    values = {o: float(statistics.median(v[o] for v in per_repeat)) for o in config["objectives"]}
    return {"status": "ok", "values": values, "parameters": params, "run_dirs": run_dirs, "reasons": errors,
            "dry_run": feas["dry_run"]}


def _optuna_values(ctx: _Context, result: dict[str, Any]) -> list[float]:
    config = ctx.config
    if result["status"] != "ok":
        return [PENALTY] * (len(config["objectives"]) if is_multi_objective(config) else 1)
    if is_multi_objective(config):
        return [result["values"][o] for o in config["objectives"]]
    if ctx.reference is None:
        ctx.reference = dict(result["values"])
    return [weighted_score(result["values"], config["weights"], ctx.reference if len(config["objectives"]) > 1 else None)]


# --------------------------------------------------------------------------- summaries

def pareto_front(rows: list[dict[str, Any]], objectives: list[str]) -> list[dict[str, Any]]:
    ok = [r for r in rows if r.get("status") == "ok" and r.get("values")]
    front = []
    for r in ok:
        dominated = False
        for other in ok:
            if other is r:
                continue
            better_eq = all(other["values"][o] <= r["values"][o] for o in objectives)
            strictly = any(other["values"][o] < r["values"][o] for o in objectives)
            if better_eq and strictly:
                dominated = True
                break
        if not dominated:
            front.append(r)
    return sorted(front, key=lambda r: r["values"][objectives[0]])


def _knee(front: list[dict[str, Any]], objectives: list[str]) -> dict[str, Any] | None:
    """Pareto point with the smallest sum of min-max normalised objectives."""
    if not front:
        return None
    lo = {o: min(r["values"][o] for r in front) for o in objectives}
    hi = {o: max(r["values"][o] for r in front) for o in objectives}

    def norm(r):
        return sum((r["values"][o] - lo[o]) / (hi[o] - lo[o]) if hi[o] > lo[o] else 0.0 for o in objectives)

    return min(front, key=norm)


def summarize(study_dir: Path, config: dict[str, Any], *, state: str | None = None, reference=None) -> dict[str, Any]:
    rows = load_trials(study_dir)
    previous = _read_json(Path(study_dir) / SUMMARY, {}) or {}
    ok = [r for r in rows if r.get("status") == "ok"]
    summary: dict[str, Any] = {
        **previous,
        "state": state or previous.get("state", "running"),
        "updated_at": _now(),
        "n_trials": config["n_trials"],
        "trials_done": len(rows),
        "trials_ok": len(ok),
        "trials_infeasible": sum(1 for r in rows if r.get("status") == "infeasible"),
        "trials_error": sum(1 for r in rows if r.get("status") == "error"),
        "objectives": config["objectives"],
        "aggregation": config["aggregation"],
        "multi_objective": is_multi_objective(config),
    }
    if reference is not None:
        summary["reference"] = reference
    best_row = None
    if is_multi_objective(config):
        front = pareto_front(rows, config["objectives"])
        summary["pareto_front"] = [r["number"] for r in front]
        best_row = _knee(front, config["objectives"])
    elif ok:
        best_row = min(ok, key=lambda r: r["score"])
    # best-so-far curve (single objective score, or knee score is not monotone -> only single)
    curve, best = [], math.inf
    for r in rows:
        if r.get("status") == "ok" and r.get("score") is not None:
            best = min(best, r["score"])
        curve.append(None if math.isinf(best) else best)
    summary["best_curve"] = curve
    if best_row is not None:
        summary["best_trial"] = best_row["number"]
        summary["best_values"] = best_row["values"]
        summary["best_score"] = best_row.get("score")
        _write_json(Path(study_dir) / BEST, best_row["parameters"])
    _write_json(Path(study_dir) / SUMMARY, summary)
    return summary


# --------------------------------------------------------------------------- warm start

def _warm_start(study, ctx: _Context) -> list[str]:
    config, space, base = ctx.config, ctx.config["search_space"], ctx.config["base_parameters"]
    notes: list[str] = []
    if len(study.trials) > 0:
        return notes  # resuming
    if config["warm_start"]["history"]:
        imported = import_history(study, config)
        if imported:
            notes.append(f"imported {imported} previous run(s) on {config['matrix_id']} from the history")
    if config["warm_start"]["base"]:
        study.enqueue_trial(parameters_to_trial_values(base, space), skip_if_exists=True)
        notes.append("enqueued the simulation's current parameters")
    if config["warm_start"]["auto"]:
        try:
            from libs.tuning.auto_select import auto_select_parameters

            auto = auto_select_parameters(config["matrix_id"], base)
            if auto["feasible"]:
                study.enqueue_trial(parameters_to_trial_values(auto["parameters"], space), skip_if_exists=True)
                notes.append("enqueued the auto-selected parameters")
        except Exception as exc:  # pragma: no cover - warm start is best effort
            notes.append(f"auto-select warm start skipped: {exc}")
    return notes


def import_history(study, config: dict[str, Any]) -> int:
    """Add history runs on this matrix that fit the search space as completed trials."""
    import optuna

    space, base = config["search_space"], config["base_parameters"]
    dof = base["general_parameters"]["dof_per_node"]
    multi = is_multi_objective(config)
    rows = history_mod.load_history(config["matrix_id"])
    scored = []
    for row in rows:
        params = row.get("parameters") or {}
        try:
            if params["general_parameters"]["dof_per_node"] != dof:
                continue
            if not (trial_values_in_range(params, space) and fixed_keys_match(params, base, space)):
                continue
            values = objective_values(row["metrics"], config["objectives"], band_percent=config["band_percent"])
        except (KeyError, TypeError, ValueError):
            continue
        scored.append((params, values))
    if not scored:
        return 0
    reference = None
    if not multi and len(config["objectives"]) > 1:
        reference = {o: float(statistics.median(v[o] for _, v in scored)) for o in config["objectives"]}
    count = 0
    for params, values in scored[-200:]:
        dists = distributions_for(space, params)
        trial_values = parameters_to_trial_values(params, space)
        if set(trial_values) != set(dists):
            continue
        optuna_values = [values[o] for o in config["objectives"]] if multi else [
            weighted_score(values, config["weights"], reference)
        ]
        study.add_trial(optuna.trial.create_trial(
            params=trial_values, distributions=dists, values=optuna_values,
            user_attrs={"source": "history"}, constraints={"infeasible": 0.0},
        ))
        count += 1
    return count


# --------------------------------------------------------------------------- main loop

def run_study(study_dir: str | Path) -> dict[str, Any]:
    study_dir = Path(study_dir)
    config = _load_config(study_dir)
    if not config:
        raise FileNotFoundError(f"{study_dir / STUDY_CONFIG} not found")
    ctx = _Context(study_dir, config)
    study = open_study(study_dir, config)
    for note in _warm_start(study, ctx):
        print(f"[tuning] warm start: {note}", flush=True)

    done = len(load_trials(study_dir))
    total = config["n_trials"]
    started = time.monotonic()
    summary = summarize(study_dir, config, state="running")
    best_score, stale, consecutive_errors = math.inf, 0, 0
    events.emit("tuning", total=total)
    print(f"[tuning] study {study_dir.name}: {total} trials, sampler={config['sampler']}, "
          f"objectives={','.join(config['objectives'])} ({config['aggregation']})", flush=True)

    stop_reason = "budget reached"
    while done < total:
        if (study_dir / STOP_FILE).exists():
            stop_reason = "stopped by user"
            break
        if config["timeout_sec"] and time.monotonic() - started > config["timeout_sec"]:
            stop_reason = "time limit reached"
            break
        trial = study.ask()
        params = suggest_parameters(trial, config["search_space"], config["base_parameters"])
        t0 = time.monotonic()
        result = _evaluate(ctx, params, trial.number)
        values = _optuna_values(ctx, result)
        trial.set_constraint("infeasible", 0.0 if result["status"] == "ok" else 1.0)
        trial.set_user_attr("status", result["status"])
        study.tell(trial, values if len(values) > 1 else values[0])

        row = {
            "number": trial.number,
            "status": result["status"],
            "suggested": trial.params,
            "parameters": result["parameters"],
            "values": result.get("values"),
            "score": values[0] if (result["status"] == "ok" and not is_multi_objective(config)) else None,
            "reasons": result.get("reasons", []),
            "run_dirs": result.get("run_dirs", []),
            "dry_run": result.get("dry_run"),
            "duration_sec": round(time.monotonic() - t0, 3),
            "finished_at": _now(),
        }
        _append_trial(study_dir, row)
        done += 1
        summary = summarize(study_dir, config, state="running", reference=ctx.reference)

        value_txt = "-" if row["values"] is None else " ".join(f"{k}={v:.4g}" for k, v in row["values"].items())
        best_txt = summary.get("best_trial", "-")
        print(f"[tuning] trial {done}/{total} status={row['status']} {value_txt} best_trial={best_txt}", flush=True)
        events.emit("trial", done=done, total=total, status=row["status"])
        if row["status"] != "ok" and row["reasons"]:
            print(f"[tuning]   reason: {row['reasons'][0]}", flush=True)

        consecutive_errors = consecutive_errors + 1 if row["status"] == "error" else 0
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            stop_reason = f"{consecutive_errors} consecutive pipeline errors (last: {row['reasons'][:1]})"
            break

        if config["patience"] and not is_multi_objective(config):
            if row["score"] is not None and row["score"] < best_score - 1e-12:
                best_score, stale = row["score"], 0
            else:
                stale += 1
            if stale >= config["patience"]:
                stop_reason = f"no improvement in {config['patience']} trials"
                break

    (study_dir / STOP_FILE).unlink(missing_ok=True)
    summary = summarize(study_dir, config, state="completed", reference=ctx.reference)
    summary["stop_reason"] = stop_reason
    _write_json(study_dir / SUMMARY, summary)
    print(f"[tuning] finished ({stop_reason}); best trial: {summary.get('best_trial', '-')}", flush=True)
    return summary


# --------------------------------------------------------------------------- human in the loop

def suggest_next(study_dir: str | Path) -> dict[str, Any]:
    """Ask the study for one candidate without running it (the user runs it from the Studio)."""
    study_dir = Path(study_dir)
    config = _load_config(study_dir)
    ctx = _Context(study_dir, config)
    study = open_study(study_dir, config)
    _warm_start(study, ctx)
    for _ in range(25):  # skip candidates that fail the cheap checks
        trial = study.ask()
        params = suggest_parameters(trial, config["search_space"], config["base_parameters"])
        try:
            params = validate_and_normalize_simulation_parameters(params)
            feas = check_feasibility(ctx.graph(params), params)
        except ValueError as exc:
            feas = {"feasible": False, "reasons": [str(exc)]}
        if feas["feasible"]:
            trial.set_constraint("infeasible", 0.0)
            pending = _read_json(study_dir / PENDING, {}) or {}
            pending[str(trial.number)] = {"parameters": params, "created_at": _now(), "suggested": trial.params}
            _write_json(study_dir / PENDING, pending)
            return {"trial_number": trial.number, "parameters": params, "dry_run": feas.get("dry_run")}
        trial.set_constraint("infeasible", 1.0)
        trial.set_user_attr("status", "infeasible")
        n_values = len(config["objectives"]) if is_multi_objective(config) else 1
        study.tell(trial, [PENALTY] * n_values if n_values > 1 else PENALTY)
        _append_trial(study_dir, {"number": trial.number, "status": "infeasible", "suggested": trial.params,
                                  "parameters": params, "values": None, "score": None,
                                  "reasons": feas["reasons"], "run_dirs": [], "finished_at": _now(), "manual": True})
    raise RuntimeError("Could not find a feasible candidate in 25 attempts; widen the search space")


def report_run(study_dir: str | Path, trial_number: int, run_dir: str | Path) -> dict[str, Any]:
    """Score a finished run of a suggested trial and tell the study."""
    study_dir = Path(study_dir)
    config = _load_config(study_dir)
    pending = _read_json(study_dir / PENDING, {}) or {}
    entry = pending.pop(str(trial_number), None)
    if entry is None:
        raise ValueError(f"Trial {trial_number} is not pending in this study")
    ctx = _Context(study_dir, config)
    study = open_study(study_dir, config)
    values = objective_values(read_run_metrics(Path(run_dir)), config["objectives"], band_percent=config["band_percent"])
    result = {"status": "ok", "values": values}
    optuna_values = _optuna_values(ctx, result)
    study.tell(trial_number, optuna_values if len(optuna_values) > 1 else optuna_values[0])
    _append_trial(study_dir, {
        "number": trial_number, "status": "ok", "suggested": entry.get("suggested"),
        "parameters": entry["parameters"], "values": values,
        "score": None if is_multi_objective(config) else optuna_values[0],
        "reasons": [], "run_dirs": [str(run_dir)], "finished_at": _now(), "manual": True,
    })
    _write_json(study_dir / PENDING, pending)
    return summarize(study_dir, config, state="manual", reference=ctx.reference)
