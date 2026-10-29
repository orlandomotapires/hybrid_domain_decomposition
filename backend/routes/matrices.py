from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import time
from typing import Any
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from libs.multilevel_scheme.coarsening.coarsening import coarsen_graph
from libs.runtime.utils import (
    AVAILABLE_SAVE_OUTPUTS,
    load_mtx,
    matrix_to_graph,
    resolve_matrix_input_path,
    resolve_parameters_file_path,
    validate_and_normalize_simulation_config,
    validate_and_normalize_simulation_parameters,
    write_json,
)
from backend.services.matrix_service import (
    generate_demo_fem_matrices,
    list_demonstrator_matrices,
)

router = APIRouter(prefix="/api/demonstrators", tags=["matrices"])

ROOT_DIR = Path(__file__).resolve().parents[2]
DEMONSTRATORS_ROOT = ROOT_DIR / "matrices"


class CreateDemonstratorRequest(BaseModel):
    name: str
    clone_from: str | None = "matrix_01"


class GenerateDemoMatricesRequest(BaseModel):
    nx_nodes: int = 12
    ny_nodes: int = 5
    nz_nodes: int = 4
    dof_per_node: int = 3
    seed: int = 42


class SavePresetRequest(BaseModel):
    filename: str
    parameters: dict[str, Any]
    set_active: bool = True


def _sanitize_dem_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip())
    if not cleaned:
        raise HTTPException(status_code=400, detail="Demonstrator name must contain alphanumeric characters")
    return cleaned


def _compute_quantum_estimates(normalized_params: dict[str, Any]) -> dict[str, Any]:
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

    if strategy == "quantum_annealing":
        num_starts = int(strat_block.get("num_starts", 1))
        num_reads = int(strat_block.get("num_reads", 1))
        simulated = bool(strat_block.get("simulated", True))
        expected_submissions = max(1, num_starts) * bipartitions_per_start
        expected_reads = expected_submissions * max(1, num_reads)
        estimates["simulated"] = simulated
        estimates["expected_qpu_submissions"] = expected_submissions
        estimates["expected_qpu_reads"] = expected_reads
        if not simulated and expected_submissions > 50:
            estimates["warnings"].append(
                f"High QPU submission count ({expected_submissions}). Reduce num_starts/k_target or use simulated=true for pilot runs."
            )
    elif strategy == "quantum_approximation_optimizer":
        num_starts = int(strat_block.get("num_starts", 1))
        num_steps = int(strat_block.get("num_steps", 1))
        num_shots = int(strat_block.get("num_shots", 1))
        simulated = bool(strat_block.get("simulated", True))
        expected_jobs = max(1, num_starts) * bipartitions_per_start * (max(1, num_steps) + 1)
        estimates["simulated"] = simulated
        estimates["expected_qlm_jobs"] = expected_jobs
        estimates["total_circuit_shots"] = expected_jobs * max(1, num_shots)
        if not simulated and expected_jobs > 100:
            estimates["warnings"].append(
                f"High remote QLM job count ({expected_jobs}). Consider reducing num_starts/num_steps or coarsening further."
            )

    return estimates


def _inspect_demonstrator(dem_dir: Path) -> dict[str, Any]:
    data_dir = dem_dir / "data"
    config_path = data_dir / "simulation_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing simulation_config.json in {dem_dir.name}")

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

    matrices_info = list_demonstrator_matrices(data_dir, simulation_config)

    results_dir = dem_dir / "results"
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
            latest_run = f"matrices/{dem_dir.name}/results/{run_dirs[0].name}"

    return {
        "id": dem_dir.name,
        "demonstrator_dir": f"matrices/{dem_dir.name}",
        "simulation_config": simulation_config,
        "simulation_parameters": simulation_parameters,
        "active_parameters_file": params_path.name,
        "preset_files": preset_files,
        "matrices": matrices_info,
        "runs_count": runs_count,
        "latest_run": latest_run,
        "estimates": _compute_quantum_estimates(simulation_parameters),
        "available_save_outputs": sorted(AVAILABLE_SAVE_OUTPUTS),
    }


@router.get("")
def list_demonstrators() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if DEMONSTRATORS_ROOT.exists():
        for d in sorted(DEMONSTRATORS_ROOT.iterdir()):
            if d.is_dir() and (d / "data" / "simulation_config.json").exists():
                try:
                    items.append(_inspect_demonstrator(d))
                except Exception as exc:
                    items.append(
                        {
                            "id": d.name,
                            "demonstrator_dir": f"matrices/{d.name}",
                            "error": str(exc),
                        }
                    )
    return {"demonstrators": items}


@router.get("/{dem_id}")
def get_demonstrator(dem_id: str) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")
    try:
        return _inspect_demonstrator(dem_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
def create_demonstrator(req: CreateDemonstratorRequest) -> dict[str, Any]:
    dem_id = _sanitize_dem_name(req.name)
    target_dir = DEMONSTRATORS_ROOT / dem_id
    if target_dir.exists():
        raise HTTPException(status_code=409, detail=f"Demonstrator {dem_id!r} already exists")

    target_data_dir = target_dir / "data"
    target_data_dir.mkdir(parents=True, exist_ok=True)
    (target_data_dir / "matrices").mkdir(parents=True, exist_ok=True)

    if req.clone_from:
        src_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(req.clone_from)
        src_data_dir = src_dir / "data"
        if src_data_dir.exists():
            for json_file in src_data_dir.glob("*.json"):
                shutil.copy2(json_file, target_data_dir / json_file.name)
            src_mat_dir = src_data_dir / "matrices"
            if src_mat_dir.exists():
                for mtx_file in src_mat_dir.glob("*.mtx"):
                    shutil.copy2(mtx_file, target_data_dir / "matrices" / mtx_file.name)

    if not (target_data_dir / "simulation_config.json").exists():
        write_json(
            target_data_dir / "simulation_config.json",
            {
                "parameters_file_path": "simulation_parameters.json",
                "input_matrices": {
                    "matrix_k_file_path": f"K_{dem_id}.mtx",
                    "matrix_m_file_path": f"M_{dem_id}.mtx",
                },
                "save_output": sorted(AVAILABLE_SAVE_OUTPUTS),
            },
        )

    if not (target_data_dir / "simulation_parameters.json").exists():
        write_json(
            target_data_dir / "simulation_parameters.json",
            {
                "general_parameters": {"dof_per_node": 3, "seed": 42},
                "coarsening_parameters": {
                    "coarsen_inferior_limit": 100,
                    "coarsen_superior_limit": 175,
                    "max_levels": 15,
                    "weight": "weight",
                    "strategy": "modified",
                    "coarsen_ratio": 0.85,
                },
                "partitioning_parameters": {
                    "partitioning_strategy": "metis_partitioning",
                    "common": {"k_target": 4, "balance_tolerance": 2.0},
                    "strategies": {
                        "metis_partitioning": {},
                        "quantum_annealing": {
                            "qubo_balance_lambda": 2.0,
                            "num_starts": 20,
                            "num_reads": 20,
                            "balance_violation_lambda": 5.0,
                            "simulated": True,
                        },
                        "quantum_approximation_optimizer": {
                            "qubo_balance_lambda": 2.0,
                            "num_starts": 5,
                            "num_steps": 5,
                            "num_shots": 10,
                            "balance_violation_lambda": 5.0,
                            "circuit_depth": 1,
                            "adam_learning_rate": 0.1,
                            "simulated": True,
                        },
                    },
                },
                "uncoarsening_parameters": {
                    "refine_objective": "cut_balance",
                    "refine_balance_lambda": 1.0,
                    "refine_max_passes_per_level": 50,
                    "refine_max_moves_per_pass": 5000,
                    "validate_node_weights": True,
                },
            },
        )

    return _inspect_demonstrator(target_dir)


@router.put("/{dem_id}/config")
def update_simulation_config(dem_id: str, config_payload: dict[str, Any]) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")
    data_dir = dem_dir / "data"
    try:
        normalized = validate_and_normalize_simulation_config(config_payload)
        resolve_parameters_file_path(data_dir, normalized["parameters_file_path"])
        write_json(data_dir / "simulation_config.json", normalized)
        return _inspect_demonstrator(dem_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{dem_id}/parameters")
def update_simulation_parameters(dem_id: str, params_payload: dict[str, Any]) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")
    data_dir = dem_dir / "data"
    try:
        raw_config = json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8"))
        sim_config = validate_and_normalize_simulation_config(raw_config)
        params_path = resolve_parameters_file_path(data_dir, sim_config["parameters_file_path"])

        # Preserve all strategy blocks even when validating a single active strategy
        existing_params = {}
        if params_path.exists():
            try:
                existing_params = json.loads(params_path.read_text(encoding="utf-8"))
            except Exception:
                pass

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
        return _inspect_demonstrator(dem_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dem_id}/presets/{preset_file}")
def get_parameter_preset(dem_id: str, preset_file: str) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    data_dir = dem_dir / "data"
    try:
        preset_path = resolve_parameters_file_path(data_dir, preset_file)
        raw_params = json.loads(preset_path.read_text(encoding="utf-8"))
        normalized = validate_and_normalize_simulation_parameters(raw_params)
        return {
            "filename": preset_path.name,
            "parameters": normalized,
            "estimates": _compute_quantum_estimates(normalized),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dem_id}/presets")
def save_parameter_preset(dem_id: str, req: SavePresetRequest) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")
    data_dir = dem_dir / "data"

    fname = req.filename.strip()
    if not fname.endswith(".json"):
        fname += ".json"
    fname = re.sub(r"[^a-zA-Z0-9_.-]", "_", fname)
    if fname == "simulation_config.json":
        raise HTTPException(status_code=400, detail="Preset filename cannot be simulation_config.json")

    try:
        normalized = validate_and_normalize_simulation_parameters(req.parameters)
        preset_path = data_dir / fname
        write_json(preset_path, normalized)

        if req.set_active:
            config_path = data_dir / "simulation_config.json"
            sim_config = validate_and_normalize_simulation_config(
                json.loads(config_path.read_text(encoding="utf-8"))
            )
            sim_config["parameters_file_path"] = fname
            write_json(config_path, sim_config)

        return _inspect_demonstrator(dem_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/validate-parameters")
def validate_parameters_endpoint(params_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        normalized = validate_and_normalize_simulation_parameters(params_payload)
        return {
            "valid": True,
            "normalized_parameters": normalized,
            "estimates": _compute_quantum_estimates(normalized),
        }
    except Exception as exc:
        return {
            "valid": False,
            "error": str(exc),
        }


@router.post("/{dem_id}/matrices/generate-demo")
def generate_demo_matrices_endpoint(dem_id: str, req: GenerateDemoMatricesRequest) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")
    data_dir = dem_dir / "data"
    try:
        raw_config = json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8"))
        sim_config = validate_and_normalize_simulation_config(raw_config)
        generate_demo_fem_matrices(
            data_dir,
            sim_config,
            nx_nodes=req.nx_nodes,
            ny_nodes=req.ny_nodes,
            nz_nodes=req.nz_nodes,
            dof_per_node=req.dof_per_node,
            seed=req.seed,
        )
        return _inspect_demonstrator(dem_dir)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dem_id}/matrices/upload")
async def upload_matrix_file(dem_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")

    if not file.filename or not file.filename.lower().endswith(".mtx"):
        raise HTTPException(status_code=400, detail="Only Matrix Market (.mtx) files are supported")

    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(file.filename).name)
    matrices_dir = dem_dir / "data" / "matrices"
    matrices_dir.mkdir(parents=True, exist_ok=True)
    dest_path = matrices_dir / safe_name

    with dest_path.open("wb") as out_fh:
        while chunk := await file.read(1024 * 1024):
            out_fh.write(chunk)

    return _inspect_demonstrator(dem_dir)


class RenameDemonstratorRequest(BaseModel):
    new_name: str


@router.put("/{dem_id}/rename")
def rename_demonstrator(dem_id: str, req: RenameDemonstratorRequest) -> dict[str, Any]:
    src_id = _sanitize_dem_name(dem_id)
    dst_id = _sanitize_dem_name(req.new_name)
    src_dir = DEMONSTRATORS_ROOT / src_id
    dst_dir = DEMONSTRATORS_ROOT / dst_id

    if not src_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {src_id!r} not found")
    if dst_dir.exists():
        raise HTTPException(status_code=409, detail=f"Demonstrator {dst_id!r} already exists")

    src_dir.rename(dst_dir)
    return _inspect_demonstrator(dst_dir)


@router.delete("/{dem_id}")
def delete_demonstrator(dem_id: str) -> dict[str, Any]:
    target_id = _sanitize_dem_name(dem_id)
    target_dir = DEMONSTRATORS_ROOT / target_id
    if not target_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {target_id!r} not found")

    existing_dirs = [
        d for d in DEMONSTRATORS_ROOT.iterdir()
        if d.is_dir() and (d / "data" / "simulation_config.json").exists()
    ]
    if len(existing_dirs) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last remaining demonstrator in the workspace.",
        )

    shutil.rmtree(target_dir)
    return {"deleted": target_id}


@router.delete("/{dem_id}/presets/{preset_file}")
def delete_parameter_preset(dem_id: str, preset_file: str) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")
    data_dir = dem_dir / "data"

    preset_path = resolve_parameters_file_path(data_dir, preset_file)
    if preset_path.name in ("simulation_config.json", "simulation_parameters.json"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete default file {preset_path.name!r}",
        )

    config_path = data_dir / "simulation_config.json"
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    sim_config = validate_and_normalize_simulation_config(raw_config)

    preset_path.unlink()

    if sim_config["parameters_file_path"] == preset_path.name:
        sim_config["parameters_file_path"] = "simulation_parameters.json"
        write_json(config_path, sim_config)

    return _inspect_demonstrator(dem_dir)


@router.post("/{dem_id}/preview-coarsening")
def preview_coarsening_trajectory(dem_id: str, params_payload: dict[str, Any]) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / _sanitize_dem_name(dem_id)
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Demonstrator {dem_id!r} not found")
    data_dir = dem_dir / "data"

    t0 = time.perf_counter()
    try:
        raw_config = json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8"))
        sim_config = validate_and_normalize_simulation_config(raw_config)
        normalized = validate_and_normalize_simulation_parameters(params_payload)

        k_path = resolve_matrix_input_path(
            data_dir / "matrices",
            sim_config["input_matrices"],
            key="matrix_k_file_path",
            label="K",
        )
        K = load_mtx(k_path, label="K")
        dof_per_node = int(normalized["general_parameters"]["dof_per_node"])
        if K.shape[0] % dof_per_node != 0:
            raise ValueError(
                f"Global matrix size N={K.shape[0]} is not divisible by dof_per_node={dof_per_node}"
            )

        G_curr = matrix_to_graph(K, dof_per_node=dof_per_node)
        for u in G_curr.nodes():
            if "vweight" not in G_curr.nodes[u]:
                G_curr.nodes[u]["vweight"] = 1.0

        cp = normalized["coarsening_parameters"]
        pp = normalized["partitioning_parameters"]
        seed = int(normalized["general_parameters"]["seed"])
        inferior_limit = int(cp["coarsen_inferior_limit"])
        superior_limit = cp.get("coarsen_superior_limit")
        if superior_limit is not None:
            superior_limit = int(superior_limit)
        max_levels = int(cp["max_levels"])
        coarsen_ratio = float(cp["coarsen_ratio"])
        strategy = str(cp["strategy"])
        weight_attr = str(cp.get("weight", "weight"))
        k_target = int(pp["common"]["k_target"])

        total_vw = sum(float(G_curr.nodes[u].get("vweight", 1.0)) for u in G_curr.nodes())
        max_node_weight = cp.get("max_node_weight")
        if max_node_weight is None:
            max_node_weight = 1.5 * (total_vw / max(1, k_target))
        else:
            max_node_weight = float(max_node_weight)

        def _level_info(g, lvl: int, prev_n: int | None, accepted: bool = True) -> dict[str, Any]:
            n = g.number_of_nodes()
            e = g.number_of_edges()
            vws = [float(g.nodes[u].get("vweight", 1.0)) for u in g.nodes()] or [1.0]
            in_range = (
                n >= inferior_limit and (superior_limit is None or n <= superior_limit)
            )
            return {
                "level": lvl,
                "nodes": n,
                "edges": e,
                "reduction_ratio": round(n / prev_n, 4) if prev_n else 1.0,
                "min_vweight": round(min(vws), 2),
                "max_vweight": round(max(vws), 2),
                "in_target_range": in_range,
                "accepted": accepted,
            }

        levels = [_level_info(G_curr, 0, None, True)]
        stop_reason = None

        if superior_limit is not None and inferior_limit <= G_curr.number_of_nodes() <= superior_limit:
            stop_reason = "Initial graph G_0 is already inside [inferior, superior] range."
        else:
            while G_curr.number_of_nodes() > inferior_limit and len(levels) < max_levels:
                n_prev = G_curr.number_of_nodes()
                lvl_idx = len(levels)
                Gc, _ = coarsen_graph(
                    G_curr,
                    weight=weight_attr,
                    seed=seed,
                    strategy=strategy,
                    max_node_weight=max_node_weight,
                )
                n_coarse = Gc.number_of_nodes()

                if n_coarse < inferior_limit:
                    levels.append(_level_info(Gc, lvl_idx, n_prev, accepted=False))
                    stop_reason = (
                        f"Level {lvl_idx} would undershoot inferior limit ({n_coarse} < {inferior_limit})."
                    )
                    break

                if superior_limit is not None and n_coarse <= superior_limit:
                    levels.append(_level_info(Gc, lvl_idx, n_prev, accepted=True))
                    G_curr = Gc
                    stop_reason = f"Reached target range [{inferior_limit}, {superior_limit}] at level {lvl_idx}."
                    break

                ratio = n_coarse / n_prev if n_prev > 0 else 1.0
                if n_coarse >= n_prev:
                    levels.append(_level_info(Gc, lvl_idx, n_prev, accepted=False))
                    stop_reason = f"Level {lvl_idx} produced no further node reduction ({n_coarse} >= {n_prev})."
                    break

                if ratio > coarsen_ratio:
                    levels.append(_level_info(Gc, lvl_idx, n_prev, accepted=False))
                    stop_reason = (
                        f"Level {lvl_idx} reduction ratio ({ratio:.3f}) exceeded coarsen_ratio ({coarsen_ratio:.3f})."
                    )
                    break

                levels.append(_level_info(Gc, lvl_idx, n_prev, accepted=True))
                G_curr = Gc

        accepted_levels = [lv for lv in levels if lv["accepted"]]
        final_nodes = accepted_levels[-1]["nodes"]
        reachable = (
            final_nodes >= inferior_limit
            and (superior_limit is None or final_nodes <= superior_limit)
        )
        if not stop_reason:
            if reachable:
                stop_reason = f"Reached {final_nodes} coarse nodes."
            else:
                stop_reason = f"Stopped at max_levels={max_levels} with {final_nodes} coarse nodes (above superior_limit={superior_limit})."

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
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


