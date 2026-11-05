"""Shared matrix library API: list, upload, generate and delete matrices in matrices/."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from libs.runtime.matrix_library import (
    MATRIX_LIBRARY_DIR,
    list_matrix_ids,
    matrix_dir,
    sanitize_matrix_id,
    write_matrix_meta,
)
from backend.services.matrix_service import (
    generate_demo_fem_matrices,
    inspect_matrix,
    simulations_using_matrix,
    validate_mtx_header,
)

router = APIRouter(prefix="/api/matrix-library", tags=["matrix-library"])

ROOT_DIR = Path(__file__).resolve().parents[2]
BATCH_CONFIG_PATH = ROOT_DIR / "batch" / "batch_configuration.json"


class GenerateDemoMatrixRequest(BaseModel):
    name: str | None = None
    nx_nodes: int = 12
    ny_nodes: int = 5
    nz_nodes: int = 4
    dof_per_node: int = 3
    seed: int = 42


def _new_matrix_id(raw_name: str) -> str:
    try:
        matrix_id = sanitize_matrix_id(raw_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if (MATRIX_LIBRARY_DIR / matrix_id).exists():
        raise HTTPException(status_code=409, detail=f"Matrix {matrix_id!r} already exists")
    return matrix_id


def _unique_matrix_id(base: str) -> str:
    base = sanitize_matrix_id(base)
    candidate, n = base, 2
    while (MATRIX_LIBRARY_DIR / candidate).exists():
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def _batch_matrices() -> set[str]:
    if not BATCH_CONFIG_PATH.exists():
        return set()
    try:
        cfg = json.loads(BATCH_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {str(m.get("key")) for m in cfg.get("matrices", []) if isinstance(m, dict)}


@router.get("")
def list_library_matrices() -> dict[str, Any]:
    matrices: list[dict[str, Any]] = []
    for matrix_id in list_matrix_ids():
        try:
            matrices.append(inspect_matrix(matrix_id))
        except Exception as exc:
            matrices.append({"id": matrix_id, "name": matrix_id, "error": str(exc), "ready": False, "used_by": []})
    return {"matrices": matrices}


@router.get("/{matrix_id}")
def get_library_matrix(matrix_id: str) -> dict[str, Any]:
    try:
        return inspect_matrix(matrix_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload")
async def upload_matrix(
    name: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Add one uploaded Matrix Market (.mtx) file to the library."""
    if not file.filename or not file.filename.lower().endswith(".mtx"):
        raise HTTPException(status_code=400, detail="Only Matrix Market (.mtx) files are supported")
    matrix_id = _new_matrix_id(name)
    target = matrix_dir(matrix_id)
    target.mkdir(parents=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(file.filename).name)
    tmp = target / f".{safe_name}.uploading"
    try:
        with tmp.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                fh.write(chunk)
        error = validate_mtx_header(tmp)
        if error:
            raise HTTPException(status_code=400, detail=f"{file.filename}: {error}")
        tmp.replace(target / safe_name)
        write_matrix_meta(matrix_id, file=safe_name, name=name.strip() or matrix_id)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return inspect_matrix(matrix_id)


@router.post("/generate-demo")
def generate_demo_matrix(req: GenerateDemoMatrixRequest) -> dict[str, Any]:
    """Generate a synthetic sparse test matrix (3D FEM mesh stiffness) into the library."""
    n_nodes = req.nx_nodes * req.ny_nodes * req.nz_nodes
    matrix_id = _unique_matrix_id(req.name or f"demo_fem_{n_nodes}_nodes")
    target = matrix_dir(matrix_id)
    try:
        generate_demo_fem_matrices(
            target,
            "demo_fem.mtx",
            nx_nodes=req.nx_nodes,
            ny_nodes=req.ny_nodes,
            nz_nodes=req.nz_nodes,
            dof_per_node=req.dof_per_node,
            seed=req.seed,
        )
        write_matrix_meta(
            matrix_id,
            file="demo_fem.mtx",
            name=f"Demo FEM mesh ({n_nodes} nodes)",
            description=(
                f"Synthetic {req.nx_nodes}x{req.ny_nodes}x{req.nz_nodes} mesh, "
                f"{req.dof_per_node} rows per node, seed {req.seed}"
            ),
        )
    except Exception as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return inspect_matrix(matrix_id)


@router.delete("/{matrix_id}")
def delete_library_matrix(matrix_id: str) -> dict[str, Any]:
    try:
        target = matrix_dir(matrix_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not (target / "matrix.json").exists():
        raise HTTPException(status_code=404, detail=f"Matrix {matrix_id!r} not found")
    users = simulations_using_matrix(matrix_id)
    if users:
        raise HTTPException(
            status_code=409,
            detail=f"Matrix {matrix_id!r} is used by {', '.join(users)}. Pick another matrix there first.",
        )
    if matrix_id in _batch_matrices():
        raise HTTPException(
            status_code=409,
            detail=f"Matrix {matrix_id!r} is selected in the batch configuration. Untick it in Batch Run first.",
        )
    shutil.rmtree(target)
    return {"deleted": matrix_id}
