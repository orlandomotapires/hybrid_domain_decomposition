"""Matrix library: the matrices under ``matrices/`` that simulations and batches pick from."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from libs.runtime import workspace
from libs.runtime.matrix_library import list_matrix_ids, matrix_dir, sanitize_matrix_id, write_matrix_meta

from .errors import Conflict, InvalidInput, NotFound
from .matrix_files import generate_demo_fem_matrices, inspect_matrix, simulations_using_matrix, validate_mtx_header


def sparsity_pattern(matrix_id: str) -> tuple[int, Any, Any]:
    """``(n, rows, cols)`` of the matrix's nonzeros, as int64 arrays, for plotting."""
    import numpy as np

    from libs.runtime.matrix_library import resolve_matrix
    from libs.runtime.utils import load_mtx

    try:
        path = resolve_matrix(matrix_id)
    except FileNotFoundError as exc:
        raise NotFound(str(exc)) from exc
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
    coo = load_mtx(path, label=matrix_id).tocoo()
    return int(coo.shape[0]), coo.row.astype(np.int64), coo.col.astype(np.int64)


def new_matrix_id(raw_name: str) -> str:
    """Folder id for a new matrix named ``raw_name``; the id must be free."""
    try:
        matrix_id = sanitize_matrix_id(raw_name)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
    if (workspace.matrices_dir() / matrix_id).exists():
        raise Conflict(f"Matrix {matrix_id!r} already exists")
    return matrix_id


def unique_matrix_id(base: str) -> str:
    """``base`` as an id, suffixed with a number when taken."""
    base = sanitize_matrix_id(base)
    candidate, n = base, 2
    while (workspace.matrices_dir() / candidate).exists():
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def _batch_matrices() -> set[str]:
    path = workspace.batch_config_path()
    if not path.exists():
        return set()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {str(m.get("key")) for m in config.get("matrices", []) if isinstance(m, dict)}


def list_matrices() -> dict[str, Any]:
    matrices: list[dict[str, Any]] = []
    for matrix_id in list_matrix_ids():
        try:
            matrices.append(inspect_matrix(matrix_id))
        except Exception as exc:
            matrices.append({"id": matrix_id, "name": matrix_id, "error": str(exc), "ready": False, "used_by": []})
    return {"matrices": matrices}


def get_matrix(matrix_id: str) -> dict[str, Any]:
    try:
        return inspect_matrix(matrix_id)
    except FileNotFoundError as exc:
        raise NotFound(str(exc)) from exc
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc


def safe_file_name(file_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(file_name).name)


def register_matrix_file(matrix_id: str, staged: Path, file_name: str, display_name: str) -> dict[str, Any]:
    """Validate ``staged`` (already inside the matrix folder) and publish it as the matrix's file.

    On any failure the whole matrix folder is removed.
    """
    target = matrix_dir(matrix_id)
    try:
        error = validate_mtx_header(staged)
        if error:
            raise InvalidInput(f"{file_name}: {error}")
        safe_name = safe_file_name(file_name)
        staged.replace(target / safe_name)
        write_matrix_meta(matrix_id, file=safe_name, name=display_name.strip() or matrix_id)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return inspect_matrix(matrix_id)


def import_matrix(name: str, source: str | Path) -> dict[str, Any]:
    """Copy a Matrix Market file from disk into the library under ``name``."""
    source = Path(source)
    if source.suffix.lower() != ".mtx":
        raise InvalidInput("Only Matrix Market (.mtx) files are supported")
    if not source.is_file():
        raise NotFound(f"File not found: {source}")
    matrix_id = new_matrix_id(name)
    target = matrix_dir(matrix_id)
    target.mkdir(parents=True)
    staged = target / f".{safe_file_name(source.name)}.importing"
    try:
        shutil.copyfile(source, staged)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return register_matrix_file(matrix_id, staged, source.name, name)


def generate_demo_matrix(
    name: str | None = None,
    *,
    nx_nodes: int = 12,
    ny_nodes: int = 5,
    nz_nodes: int = 4,
    dof_per_node: int = 3,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate a synthetic sparse test matrix (3D FEM mesh stiffness) into the library."""
    n_nodes = nx_nodes * ny_nodes * nz_nodes
    try:
        matrix_id = unique_matrix_id(name or f"demo_fem_{n_nodes}_nodes")
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
    target = matrix_dir(matrix_id)
    try:
        generate_demo_fem_matrices(
            target, "demo_fem.mtx", nx_nodes=nx_nodes, ny_nodes=ny_nodes, nz_nodes=nz_nodes, dof_per_node=dof_per_node, seed=seed
        )
        write_matrix_meta(
            matrix_id,
            file="demo_fem.mtx",
            name=f"Demo FEM mesh ({n_nodes} nodes)",
            description=f"Synthetic {nx_nodes}x{ny_nodes}x{nz_nodes} mesh, {dof_per_node} rows per node, seed {seed}",
        )
    except Exception as exc:
        shutil.rmtree(target, ignore_errors=True)
        raise InvalidInput(str(exc)) from exc
    return inspect_matrix(matrix_id)


def delete_matrix(matrix_id: str) -> dict[str, Any]:
    try:
        target = matrix_dir(matrix_id)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc
    if not (target / "matrix.json").exists():
        raise NotFound(f"Matrix {matrix_id!r} not found")
    users = simulations_using_matrix(matrix_id)
    if users:
        raise Conflict(f"Matrix {matrix_id!r} is used by {', '.join(users)}. Pick another matrix there first.")
    if matrix_id in _batch_matrices():
        raise Conflict(f"Matrix {matrix_id!r} is selected in the batch configuration. Untick it in Batch Run first.")
    shutil.rmtree(target)
    return {"deleted": matrix_id}
