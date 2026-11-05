"""Shared matrix library: ``<project>/matrices/<matrix_id>/`` holds one sparse matrix.

Each folder contains one Matrix Market file plus ``matrix.json``::

    {"name": "Turbine blade", "file": "blade.mtx", "description": "optional"}

The pipeline is matrix-agnostic: any square sparse matrix can be partitioned and permuted.
Simulations (``<project>/simulations/<simulation_id>/``) pick a matrix through
``simulation_config.input_matrix``; batch studies list matrices directly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATRIX_LIBRARY_DIR = PROJECT_ROOT / "matrices"
SIMULATIONS_DIR = PROJECT_ROOT / "simulations"
MATRIX_META_FILE = "matrix.json"

_MATRIX_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def sanitize_matrix_id(raw: str) -> str:
    """Turn a free-form name into a safe folder id (letters, digits, ``_`` and ``-``)."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw).strip()).strip("_")
    if not cleaned:
        raise ValueError("Matrix name must contain letters or digits")
    return cleaned


def matrix_dir(matrix_id: str, library_dir: Path | None = None) -> Path:
    if not isinstance(matrix_id, str) or not _MATRIX_ID_RE.match(matrix_id):
        raise ValueError(f"Invalid matrix id: {matrix_id!r}")
    return (library_dir or MATRIX_LIBRARY_DIR) / matrix_id


def load_matrix_meta(matrix_id: str, library_dir: Path | None = None) -> dict[str, Any]:
    """Read ``matrix.json`` for ``matrix_id``. Raises FileNotFoundError / ValueError."""
    directory = matrix_dir(matrix_id, library_dir)
    meta_path = directory / MATRIX_META_FILE
    if not meta_path.exists():
        raise FileNotFoundError(f"Matrix {matrix_id!r} not found in the matrix library ({meta_path})")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    filename = meta.get("file")
    if not isinstance(filename, str) or not filename.strip() or Path(filename).name != filename:
        raise ValueError(f"{meta_path}: 'file' must be a plain .mtx filename inside the matrix folder")
    if Path(filename).suffix.lower() != ".mtx":
        raise ValueError(f"{meta_path}: 'file' must reference a Matrix Market .mtx file")
    return {
        "id": matrix_id,
        "name": str(meta.get("name") or matrix_id),
        "description": meta.get("description"),
        "file": filename,
        "dir": directory,
    }


def resolve_matrix(matrix_id: str, library_dir: Path | None = None) -> Path:
    """Absolute path of a library matrix's .mtx file (must exist)."""
    meta = load_matrix_meta(matrix_id, library_dir)
    path = meta["dir"] / meta["file"]
    if not path.exists():
        raise FileNotFoundError(f"File of matrix {matrix_id!r} not found: {path}")
    return path


def list_matrix_ids(library_dir: Path | None = None) -> list[str]:
    root = library_dir or MATRIX_LIBRARY_DIR
    if not root.exists():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir() and (d / MATRIX_META_FILE).exists())


def write_matrix_meta(
    matrix_id: str,
    *,
    file: str,
    name: str | None = None,
    description: str | None = None,
    library_dir: Path | None = None,
) -> Path:
    directory = matrix_dir(matrix_id, library_dir)
    directory.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"name": name or matrix_id, "file": file}
    if description:
        payload["description"] = description
    meta_path = directory / MATRIX_META_FILE
    meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return meta_path
