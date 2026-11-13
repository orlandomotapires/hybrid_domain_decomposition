"""Matrix library API. Thin adapter over ``hdd.services.matrices``."""

from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from hdd.services import matrices
from hdd.services.errors import InvalidInput
from libs.runtime.matrix_library import matrix_dir

router = APIRouter(prefix="/api/matrix-library", tags=["matrix-library"])


class GenerateDemoMatrixRequest(BaseModel):
    name: str | None = None
    nx_nodes: int = 12
    ny_nodes: int = 5
    nz_nodes: int = 4
    dof_per_node: int = 3
    seed: int = 42


@router.get("")
def list_library_matrices() -> dict[str, Any]:
    return matrices.list_matrices()


@router.get("/{matrix_id}")
def get_library_matrix(matrix_id: str) -> dict[str, Any]:
    return matrices.get_matrix(matrix_id)


@router.post("/upload")
async def upload_matrix(name: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    """Add one uploaded Matrix Market (.mtx) file to the library."""
    if not file.filename or not file.filename.lower().endswith(".mtx"):
        raise InvalidInput("Only Matrix Market (.mtx) files are supported")
    matrix_id = matrices.new_matrix_id(name)
    target = matrix_dir(matrix_id)
    target.mkdir(parents=True)
    staged = target / f".{matrices.safe_file_name(file.filename)}.uploading"
    try:
        with staged.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                handle.write(chunk)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return matrices.register_matrix_file(matrix_id, staged, file.filename, name)


@router.post("/generate-demo")
def generate_demo_matrix(req: GenerateDemoMatrixRequest) -> dict[str, Any]:
    return matrices.generate_demo_matrix(
        req.name, nx_nodes=req.nx_nodes, ny_nodes=req.ny_nodes, nz_nodes=req.nz_nodes, dof_per_node=req.dof_per_node, seed=req.seed
    )


@router.delete("/{matrix_id}")
def delete_library_matrix(matrix_id: str) -> dict[str, Any]:
    return matrices.delete_matrix(matrix_id)
