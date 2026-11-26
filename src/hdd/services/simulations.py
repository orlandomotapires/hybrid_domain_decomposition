"""Simulations: folders under ``simulations/`` holding a config, parameter presets and results."""

from __future__ import annotations

import copy
import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any

from libs.graph_prep import build_pipeline_graph
from libs.tuning.feasibility import coarsening_dry_run
from libs.multilevel_scheme.partitioning.capacity import qpu_workload
from libs.runtime import workspace
from libs.runtime.defaults import DEFAULT_SIMULATION_PARAMETERS
from libs.runtime.matrix_library import list_matrix_ids
from libs.runtime.utils import (
    AVAILABLE_SAVE_OUTPUTS,
    load_mtx,
    resolve_parameters_file_path,
    resolve_simulation_matrix,
    validate_and_normalize_simulation_config,
    validate_and_normalize_simulation_parameters,
    write_json,
)

from .errors import Conflict, InvalidInput, NotFound
from .matrix_files import simulation_matrix_info

_log = logging.getLogger("hdd.services")

# Errors that mean the user's files or request are wrong. Anything else (a full disk, a permission
# problem, a bug) is not "invalid input": it propagates and is logged with its traceback.
_INPUT_ERRORS = (ValueError, KeyError, TypeError, FileNotFoundError)


def _input_error(exc: Exception) -> Exception:
    # A missing file here is one the simulation's own config points to: the config is wrong.
    if isinstance(exc, KeyError):
        return InvalidInput(f"Missing value: {exc.args[0] if exc.args else exc}")
    return InvalidInput(str(exc))



def default_parameters_for(matrix_id: str | None) -> dict[str, Any]:
    """Starting parameters for a new simulation.

    The generic defaults target a coarse graph of 100 to 175 nodes, which a given
    matrix may be unable to reach. When the matrix is in the library, the rule-based
    auto-selection adapts the coarsening range to it so a new simulation runs as created.
    """
    parameters = copy.deepcopy(DEFAULT_SIMULATION_PARAMETERS)
    if not matrix_id or matrix_id not in list_matrix_ids():
        return parameters
    try:
        from libs.tuning.auto_select import auto_select_parameters

        selection = auto_select_parameters(matrix_id, parameters)
    except Exception:  # the generic defaults still make a valid simulation
        _log.warning("Auto-selection failed for matrix %s; using the default parameters", matrix_id, exc_info=True)
        return parameters
    return selection["parameters"] if selection.get("feasible") else parameters


def sanitize_simulation_id(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())
    if not cleaned:
        raise InvalidInput("Simulation name must contain alphanumeric characters")
    return cleaned


def next_simulation_id() -> str:
    used = {d.name for d in workspace.simulations_dir().iterdir()} if workspace.simulations_dir().exists() else set()
    n = 1
    while f"simulation_{n:02d}" in used:
        n += 1
    return f"simulation_{n:02d}"


def quantum_estimates(normalized_params: dict[str, Any]) -> dict[str, Any]:
    pp = normalized_params.get("partitioning_parameters", {})
    strategy = pp.get("partitioning_strategy", "metis_partitioning")
    common = pp.get("common", {})
    k_target = int(common.get("k_target", 2))
    strat_block = pp.get("strategies", {}).get(strategy, {})
    bipartitions_per_start = max(1, k_target - 1)

    estimates: dict[str, Any] = {
        "partitioning_strategy": strategy,
        "bipartitions_per_start": bipartitions_per_start,
        "warnings": [],
    }

    workload = qpu_workload(strategy, strat_block, k_target)
    if strategy == "quantum_annealing":
        simulated = bool(strat_block.get("simulated", True))
        expected_submissions = workload["submissions"]
        estimates["simulated"] = simulated
        estimates["expected_qpu_submissions"] = expected_submissions
        estimates["expected_qpu_reads"] = workload["samples"]
        if not simulated and expected_submissions > 50:
            estimates["warnings"].append(
                f"High QPU submission count ({expected_submissions}). Reduce num_starts/k_target or use simulated=true for pilot runs."
            )
    elif strategy == "quantum_approximation_optimizer":
        simulated = bool(strat_block.get("simulated", True))
        expected_jobs = workload["submissions"]
        estimates["simulated"] = simulated
        estimates["expected_qlm_jobs"] = expected_jobs
        estimates["total_circuit_shots"] = workload["samples"]
        if not simulated and expected_jobs > 100:
            estimates["warnings"].append(
                f"High remote QLM job count ({expected_jobs}). Consider reducing num_starts/num_steps or coarsening further."
            )

    return estimates


def inspect_simulation(simulation_dir: Path) -> dict[str, Any]:
    data_dir = simulation_dir / "data"
    config_path = data_dir / "simulation_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing simulation_config.json in {simulation_dir.name}")

    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    simulation_config = validate_and_normalize_simulation_config(raw_config)

    params_path = resolve_parameters_file_path(data_dir, simulation_config["parameters_file_path"])
    raw_params = json.loads(params_path.read_text(encoding="utf-8"))
    simulation_parameters = validate_and_normalize_simulation_parameters(raw_params)

    preset_files = [
        f.name
        for f in sorted(data_dir.glob("*.json"))
        if f.name != "simulation_config.json"
    ]

    matrix_info = simulation_matrix_info(simulation_config)

    results_dir = simulation_dir / "results"
    runs_count = 0
    latest_run = None
    if results_dir.exists() and results_dir.is_dir():
        run_dirs = sorted(
            [d for d in results_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
            key=lambda p: p.name,
            reverse=True,
        )
        runs_count = len(run_dirs)
        if run_dirs:
            latest_run = f"simulations/{simulation_dir.name}/results/{run_dirs[0].name}"

    return {
        "id": simulation_dir.name,
        "demonstrator_dir": f"simulations/{simulation_dir.name}",
        "simulation_config": simulation_config,
        "simulation_parameters": simulation_parameters,
        "active_parameters_file": params_path.name,
        "preset_files": preset_files,
        "matrix": matrix_info,
        "runs_count": runs_count,
        "latest_run": latest_run,
        "estimates": quantum_estimates(simulation_parameters),
        "available_save_outputs": sorted(AVAILABLE_SAVE_OUTPUTS),
    }


def list_simulations() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if workspace.simulations_dir().exists():
        for d in sorted(workspace.simulations_dir().iterdir()):
            if d.is_dir() and (d / "data" / "simulation_config.json").exists():
                try:
                    items.append(inspect_simulation(d))
                except Exception as exc:
                    items.append(
                        {
                            "id": d.name,
                            "demonstrator_dir": f"simulations/{d.name}",
                            "error": str(exc),
                        }
                    )
    return {"demonstrators": items}


def get_simulation(simulation_id: str) -> dict[str, Any]:
    simulation_dir = workspace.simulations_dir() / sanitize_simulation_id(simulation_id)
    if not simulation_dir.exists():
        raise NotFound(f"Simulation {simulation_id!r} not found")
    try:
        return inspect_simulation(simulation_dir)
    except _INPUT_ERRORS as exc:
        raise _input_error(exc) from exc


def create_simulation(name: str | None = None, clone_from: str | None = None, matrix: str | None = None) -> dict[str, Any]:
    simulation_id = sanitize_simulation_id(name) if name and name.strip() else next_simulation_id()
    target_dir = workspace.simulations_dir() / simulation_id
    if target_dir.exists():
        raise Conflict(f"Simulation {simulation_id!r} already exists")

    target_data_dir = target_dir / "data"
    target_data_dir.mkdir(parents=True, exist_ok=True)

    if clone_from:
        src_data_dir = workspace.simulations_dir() / sanitize_simulation_id(clone_from) / "data"
        if src_data_dir.exists():
            for json_file in src_data_dir.glob("*.json"):
                shutil.copy2(json_file, target_data_dir / json_file.name)

    config_path = target_data_dir / "simulation_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {
        "parameters_file_path": "simulation_parameters.json",
        "save_output": sorted(AVAILABLE_SAVE_OUTPUTS),
    }
    matrix_id = matrix or config.get("input_matrix")
    if not matrix_id:
        ids = list_matrix_ids()
        # Empty library: keep a placeholder until a matrix is uploaded/generated in Single Run.
        matrix_id = ids[0] if ids else "none"
    config["input_matrix"] = matrix_id
    write_json(config_path, config)

    if not (target_data_dir / "simulation_parameters.json").exists():
        write_json(target_data_dir / "simulation_parameters.json", default_parameters_for(matrix_id))

    return inspect_simulation(target_dir)


def save_config(simulation_id: str, config_payload: dict[str, Any]) -> dict[str, Any]:
    simulation_dir = workspace.simulations_dir() / sanitize_simulation_id(simulation_id)
    if not simulation_dir.exists():
        raise NotFound(f"Simulation {simulation_id!r} not found")
    data_dir = simulation_dir / "data"
    try:
        normalized = validate_and_normalize_simulation_config(config_payload)
        resolve_parameters_file_path(data_dir, normalized["parameters_file_path"])
        write_json(data_dir / "simulation_config.json", normalized)
        return inspect_simulation(simulation_dir)
    except _INPUT_ERRORS as exc:
        raise _input_error(exc) from exc


def save_parameters(simulation_id: str, params_payload: dict[str, Any]) -> dict[str, Any]:
    simulation_dir = workspace.simulations_dir() / sanitize_simulation_id(simulation_id)
    if not simulation_dir.exists():
        raise NotFound(f"Simulation {simulation_id!r} not found")
    data_dir = simulation_dir / "data"
    try:
        raw_config = json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8"))
        sim_config = validate_and_normalize_simulation_config(raw_config)
        params_path = resolve_parameters_file_path(data_dir, sim_config["parameters_file_path"])

        # Preserve all strategy blocks even when validating a single active strategy
        existing_params = {}
        if params_path.exists():
            try:
                existing_params = json.loads(params_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                # The other strategies' settings cannot be carried over; keep the old file aside
                # instead of overwriting it silently.
                backup = params_path.with_name(params_path.name + ".unreadable")
                shutil.copy2(params_path, backup)
                _log.warning("%s was unreadable (%s); kept a copy as %s", params_path, exc, backup.name)

        normalized = validate_and_normalize_simulation_parameters(params_payload)

        # Keep non-active strategy configurations intact so switching strategies doesn't lose user settings
        existing_strategies = existing_params.get("partitioning_parameters", {}).get("strategies", {})
        incoming_strategies = params_payload.get("partitioning_parameters", {}).get("strategies", {})
        merged_strategies = {
            **existing_strategies,
            **incoming_strategies,
            **normalized["partitioning_parameters"]["strategies"],
        }
        normalized["partitioning_parameters"]["strategies"] = merged_strategies

        write_json(params_path, normalized)
        return inspect_simulation(simulation_dir)
    except _INPUT_ERRORS as exc:
        raise _input_error(exc) from exc


def load_preset(simulation_id: str, preset_file: str) -> dict[str, Any]:
    simulation_dir = workspace.simulations_dir() / sanitize_simulation_id(simulation_id)
    data_dir = simulation_dir / "data"
    try:
        preset_path = resolve_parameters_file_path(data_dir, preset_file)
        raw_params = json.loads(preset_path.read_text(encoding="utf-8"))
        normalized = validate_and_normalize_simulation_parameters(raw_params)
        return {
            "filename": preset_path.name,
            "parameters": normalized,
            "estimates": quantum_estimates(normalized),
        }
    except _INPUT_ERRORS as exc:
        raise _input_error(exc) from exc


def save_preset(simulation_id: str, filename: str, parameters: dict[str, Any], set_active: bool = True) -> dict[str, Any]:
    simulation_dir = workspace.simulations_dir() / sanitize_simulation_id(simulation_id)
    if not simulation_dir.exists():
        raise NotFound(f"Simulation {simulation_id!r} not found")
    data_dir = simulation_dir / "data"

    fname = filename.strip()
    if not fname.endswith(".json"):
        fname += ".json"
    fname = re.sub(r"[^a-zA-Z0-9_.-]", "_", fname)
    if fname == "simulation_config.json":
        raise InvalidInput("Preset filename cannot be simulation_config.json")

    try:
        normalized = validate_and_normalize_simulation_parameters(parameters)
        preset_path = data_dir / fname
        write_json(preset_path, normalized)

        if set_active:
            config_path = data_dir / "simulation_config.json"
            sim_config = validate_and_normalize_simulation_config(
                json.loads(config_path.read_text(encoding="utf-8"))
            )
            sim_config["parameters_file_path"] = fname
            write_json(config_path, sim_config)

        return inspect_simulation(simulation_dir)
    except _INPUT_ERRORS as exc:
        raise _input_error(exc) from exc


def validate_parameters(params_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        normalized = validate_and_normalize_simulation_parameters(params_payload)
        return {
            "valid": True,
            "normalized_parameters": normalized,
            "estimates": quantum_estimates(normalized),
        }
    except Exception as exc:
        return {
            "valid": False,
            "error": str(exc),
        }


def rename_simulation(simulation_id: str, new_name: str) -> dict[str, Any]:
    src_id = sanitize_simulation_id(simulation_id)
    dst_id = sanitize_simulation_id(new_name)
    src_dir = workspace.simulations_dir() / src_id
    dst_dir = workspace.simulations_dir() / dst_id

    if not src_dir.exists():
        raise NotFound(f"Simulation {src_id!r} not found")
    if dst_dir.exists():
        raise Conflict(f"Simulation {dst_id!r} already exists")

    src_dir.rename(dst_dir)
    return inspect_simulation(dst_dir)


def delete_simulation(simulation_id: str) -> dict[str, Any]:
    target_id = sanitize_simulation_id(simulation_id)
    target_dir = workspace.simulations_dir() / target_id
    if not target_dir.exists():
        raise NotFound(f"Simulation {target_id!r} not found")

    existing_dirs = [
        d for d in workspace.simulations_dir().iterdir()
        if d.is_dir() and (d / "data" / "simulation_config.json").exists()
    ]
    if len(existing_dirs) <= 1:
        raise InvalidInput("Cannot delete the last remaining simulation.",
        )

    shutil.rmtree(target_dir)
    remaining = sorted(d.name for d in existing_dirs if d.name != target_id)
    return {"deleted": target_id, "remaining_demonstrators": remaining}


def delete_preset(simulation_id: str, preset_file: str) -> dict[str, Any]:
    simulation_dir = workspace.simulations_dir() / sanitize_simulation_id(simulation_id)
    if not simulation_dir.exists():
        raise NotFound(f"Simulation {simulation_id!r} not found")
    data_dir = simulation_dir / "data"

    preset_path = resolve_parameters_file_path(data_dir, preset_file)
    if preset_path.name in ("simulation_config.json", "simulation_parameters.json"):
        raise InvalidInput(f"Cannot delete default file {preset_path.name!r}",
        )

    config_path = data_dir / "simulation_config.json"
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    sim_config = validate_and_normalize_simulation_config(raw_config)

    preset_path.unlink()

    if sim_config["parameters_file_path"] == preset_path.name:
        sim_config["parameters_file_path"] = "simulation_parameters.json"
        write_json(config_path, sim_config)

    return inspect_simulation(simulation_dir)


def preview_coarsening(simulation_id: str, params_payload: dict[str, Any]) -> dict[str, Any]:
    simulation_dir = workspace.simulations_dir() / sanitize_simulation_id(simulation_id)
    if not simulation_dir.exists():
        raise NotFound(f"Simulation {simulation_id!r} not found")
    data_dir = simulation_dir / "data"

    t0 = time.perf_counter()
    try:
        raw_config = json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8"))
        sim_config = validate_and_normalize_simulation_config(raw_config)
        # Preview the matrix being edited (may be unsaved) when the client sends it. The caller's
        # dict is left untouched.
        payload = dict(params_payload) if isinstance(params_payload, dict) else params_payload
        preview_matrix = payload.pop("_matrix", None) if isinstance(payload, dict) else None
        normalized = validate_and_normalize_simulation_parameters(payload)

        matrix_path = resolve_simulation_matrix({"input_matrix": preview_matrix} if preview_matrix else sim_config)
        A = load_mtx(matrix_path, label="matrix")
        dof_per_node = int(normalized["general_parameters"]["dof_per_node"])
        if A.shape[0] % dof_per_node != 0:
            raise ValueError(
                f"Matrix size N={A.shape[0]} is not divisible by dof_per_node={dof_per_node}"
            )

        cp = normalized["coarsening_parameters"]
        weight_attr = str(cp.get("weight", "weight"))
        inferior_limit = int(cp["coarsen_inferior_limit"])
        superior_limit = None if cp.get("coarsen_superior_limit") is None else int(cp["coarsen_superior_limit"])
        # The same weighted graph the run uses; the coarsening is the pipeline's own dry run.
        G0 = build_pipeline_graph(A, dof_per_node, weight_attr)

        def _level_info(g, lvl: int, prev_n: int | None, accepted: bool) -> dict[str, Any]:
            n = g.number_of_nodes()
            vws = [float(g.nodes[u].get("vweight", 1.0)) for u in g.nodes()] or [1.0]
            return {
                "level": lvl,
                "nodes": n,
                "edges": g.number_of_edges(),
                "reduction_ratio": round(n / prev_n, 4) if prev_n else 1.0,
                "min_vweight": round(min(vws), 2),
                "max_vweight": round(max(vws), 2),
                "in_target_range": n >= inferior_limit and (superior_limit is None or n <= superior_limit),
                "accepted": accepted,
            }

        levels = [_level_info(G0, 0, None, True)]
        stops: list[str] = []

        def on_level(g, accepted: bool, reason: str | None) -> None:
            levels.append(_level_info(g, len(levels), levels[-1]["nodes"] if levels else None, accepted))
            if reason:
                stops.append(f"Level {len(levels) - 1}: {reason}.")

        coarsening_dry_run(G0, normalized, on_level=on_level)  # an unreachable range shows in the levels

        accepted_levels = [lv for lv in levels if lv["accepted"]]
        final_nodes = accepted_levels[-1]["nodes"]
        reachable = final_nodes >= inferior_limit and (superior_limit is None or final_nodes <= superior_limit)
        if len(levels) == 1 and reachable:
            stop_reason = "Initial graph G_0 is already inside [inferior, superior] range."
        elif reachable:
            stop_reason = f"Reached {final_nodes} coarse nodes at level {len(accepted_levels) - 1}."
        elif stops:
            stop_reason = stops[-1]
        else:
            stop_reason = f"Stopped at max_levels={cp['max_levels']} with {final_nodes} coarse nodes (above superior_limit={superior_limit})."

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "reachable": reachable,
            "final_coarse_nodes": final_nodes,
            "final_coarse_edges": accepted_levels[-1]["edges"],
            "accepted_levels_count": len(accepted_levels),
            "stop_reason": stop_reason,
            "elapsed_ms": elapsed_ms,
            "levels": levels,
        }
    except _INPUT_ERRORS as exc:
        raise _input_error(exc) from exc


