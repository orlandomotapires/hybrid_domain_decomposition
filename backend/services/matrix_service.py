from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
import scipy.sparse as sp
from scipy.io import mmwrite

from libs.runtime.matrix_library import SIMULATIONS_DIR, load_matrix_meta


def inspect_mtx_file(path: Path) -> dict[str, Any]:
    """Quickly parse Matrix Market (.mtx) header without loading the entire sparse matrix into memory."""
    if not path.exists() or not path.is_file():
        return {
            "filename": path.name,
            "exists": False,
            "size_bytes": 0,
            "rows": None,
            "cols": None,
            "nnz": None,
            "symmetry": None,
            "format_type": None,
            "field_type": None,
        }

    size_bytes = path.stat().st_size
    rows = None
    cols = None
    nnz = None
    format_type = "coordinate"
    field_type = "real"
    symmetry = "general"

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            first_line = fh.readline().strip()
            if first_line.startswith("%%MatrixMarket"):
                parts = first_line.split()
                if len(parts) >= 5:
                    format_type = parts[2].lower()
                    field_type = parts[3].lower()
                    symmetry = parts[4].lower()

            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("%"):
                    continue
                dims = stripped.split()
                if len(dims) >= 3:
                    rows = int(dims[0])
                    cols = int(dims[1])
                    nnz = int(dims[2])
                elif len(dims) == 2:
                    rows = int(dims[0])
                    cols = int(dims[1])
                break
    except Exception:
        pass

    return {
        "filename": path.name,
        "exists": True,
        "size_bytes": size_bytes,
        "rows": rows,
        "cols": cols,
        "nnz": nnz,
        "symmetry": symmetry,
        "format_type": format_type,
        "field_type": field_type,
    }


def validate_mtx_header(path: Path) -> str | None:
    """Strictly check a Matrix Market header. Returns an error message, or None if the file looks valid."""
    try:
        with path.open("r", encoding="utf-8", errors="strict") as fh:
            banner = fh.readline().strip()
            parts = banner.split()
            if len(parts) < 5 or parts[0] != "%%MatrixMarket" or parts[1].lower() != "matrix":
                return "Missing '%%MatrixMarket matrix ...' header line — is this a Matrix Market file?"
            fmt, field, symmetry = (p.lower() for p in parts[2:5])
            if fmt != "coordinate":
                return f"Unsupported format '{fmt}': only sparse 'coordinate' matrices are supported"
            if field not in {"real", "integer", "double", "pattern"}:
                return f"Unsupported field type '{field}': expected real, integer or pattern"
            if symmetry not in {"general", "symmetric"}:
                return f"Unsupported symmetry '{symmetry}': expected general or symmetric"

            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("%"):
                    continue
                dims = stripped.split()
                if len(dims) != 3:
                    return "Size line must contain three integers: rows cols nnz"
                rows, cols, nnz = (int(d) for d in dims)
                if rows <= 0 or cols <= 0:
                    return f"Invalid matrix dimensions {rows} × {cols}"
                if rows != cols:
                    return f"Matrix must be square, got {rows} × {cols}"
                if nnz <= 0:
                    return "Matrix has no nonzero entries"
                return None
        return "File ends before the size line (rows cols nnz)"
    except UnicodeDecodeError:
        return "File is not a text Matrix Market file"
    except ValueError:
        return "Size line must contain three integers: rows cols nnz"
    except OSError as exc:
        return f"Could not read file: {exc}"


def inspect_matrix(matrix_id: str) -> dict[str, Any]:
    """Library matrix summary: name, header info (size, nnz, symmetry) and which simulations use it."""
    meta = load_matrix_meta(matrix_id)
    info = inspect_mtx_file(meta["dir"] / meta["file"])
    return {
        "id": matrix_id,
        "name": meta["name"],
        "description": meta.get("description"),
        "info": info,
        "ready": bool(info.get("exists")),
        "square": bool(info.get("exists")) and info.get("rows") == info.get("cols"),
        "used_by": simulations_using_matrix(matrix_id),
    }


def simulations_using_matrix(matrix_id: str) -> list[str]:
    users: list[str] = []
    if not SIMULATIONS_DIR.exists():
        return users
    for sim in sorted(SIMULATIONS_DIR.iterdir()):
        cfg_path = sim / "data" / "simulation_config.json"
        if not cfg_path.exists():
            continue
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if cfg.get("input_matrix") == matrix_id:
            users.append(sim.name)
    return users


def simulation_matrix_info(simulation_config: dict[str, Any]) -> dict[str, Any]:
    """The matrix a simulation uses, with its header info (or an error when it's not in the library)."""
    matrix_id = simulation_config.get("input_matrix")
    try:
        m = inspect_matrix(str(matrix_id))
    except (FileNotFoundError, ValueError) as exc:
        return {
            "id": matrix_id,
            "name": None,
            "error": str(exc),
            "info": {"filename": "", "exists": False},
            "ready": False,
        }
    return {"id": matrix_id, "name": m["name"], "info": m["info"], "ready": m["ready"]}


def generate_demo_fem_matrices(
    target_dir: Path,
    k_filename: str,
    m_filename: str | None = None,
    *,
    nx_nodes: int = 12,
    ny_nodes: int = 5,
    nz_nodes: int = 4,
    dof_per_node: int = 3,
    seed: int = 42,
) -> dict[str, Any]:
    """Generate a synthetic sparse test matrix from a 3D Finite Element (FEM) blade mesh.

    Writes the stiffness-like matrix to ``k_filename`` (and the mass-like one to ``m_filename`` when
    given). Returns the header info of the written matrix.

    Constructs a 3D hexahedral/tetrahedral elastic lattice with `dof_per_node` DOFs per vertex,
    numbered initially in a non-optimal/scrambled finite-element assembly order so that graph
    partitioning and permutation demonstrably improve bandwidth and locality metrics.
    """
    matrices_dir = Path(target_dir)
    matrices_dir.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(seed)
    num_nodes = int(nx_nodes) * int(ny_nodes) * int(nz_nodes)
    d = max(1, int(dof_per_node))
    n_total = num_nodes * d

    # Scramble node numbering slightly (as often occurs in CAD/ANSYS unstructured mesh exports)
    # so bandwidth reduction from domain decomposition is clearly observable
    grid_nodes = np.arange(num_nodes, dtype=np.int64)
    # Block-interleaved assembly order
    assembly_order = np.argsort((grid_nodes * 37 + (grid_nodes // max(1, nx_nodes)) * 13) % num_nodes)

    def node_id(ix: int, iy: int, iz: int) -> int:
        raw = (iz * ny_nodes + iy) * nx_nodes + ix
        return int(assembly_order[raw])

    rows_k: list[int] = []
    cols_k: list[int] = []
    vals_k: list[float] = []

    rows_m: list[int] = []
    cols_m: list[int] = []
    vals_m: list[float] = []

    diag_k = np.zeros(n_total, dtype=np.float64)
    diag_m = np.zeros(n_total, dtype=np.float64)

    # 26-point 3D finite element stencil (hexahedral element connectivity)
    offsets = [
        (dx, dy, dz)
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        for dz in (-1, 0, 1)
        if not (dx == 0 and dy == 0 and dz == 0)
    ]

    for iz in range(nz_nodes):
        for iy in range(ny_nodes):
            for ix in range(nx_nodes):
                u = node_id(ix, iy, iz)
                for dx, dy, dz in offsets:
                    jx, jy, jz = ix + dx, iy + dy, iz + dz
                    if 0 <= jx < nx_nodes and 0 <= jy < ny_nodes and 0 <= jz < nz_nodes:
                        v = node_id(jx, jy, jz)
                        if u >= v:
                            continue
                        dist = float(np.sqrt(dx * dx + dy * dy + dz * dz))
                        # Elastic stiffness coupling (stronger along primary axes)
                        base_k = (210.0 / (dist ** 2)) * float(rng.uniform(0.92, 1.08))
                        base_m = (7.8 / (dist ** 3)) * float(rng.uniform(0.95, 1.05))

                        for di in range(d):
                            for dj in range(d):
                                row_u = u * d + di
                                col_v = v * d + dj
                                scale = 1.0 if di == dj else 0.28
                                k_val = -base_k * scale
                                m_val = base_m * (0.35 if di == dj else 0.08)

                                rows_k.extend([row_u, col_v])
                                cols_k.extend([col_v, row_u])
                                vals_k.extend([k_val, k_val])
                                diag_k[row_u] += abs(k_val)
                                diag_k[col_v] += abs(k_val)

                                rows_m.extend([row_u, col_v])
                                cols_m.extend([col_v, row_u])
                                vals_m.extend([m_val, m_val])
                                diag_m[row_u] += abs(m_val) * 1.5
                                diag_m[col_v] += abs(m_val) * 1.5

    # Ensure strictly positive-definite diagonal
    for i in range(n_total):
        rows_k.append(i)
        cols_k.append(i)
        vals_k.append(float(diag_k[i] * 1.15 + 100.0))

        rows_m.append(i)
        cols_m.append(i)
        vals_m.append(float(diag_m[i] * 1.25 + 10.0))

    mat_k = sp.coo_matrix((vals_k, (rows_k, cols_k)), shape=(n_total, n_total)).tocsr()
    mat_m = sp.coo_matrix((vals_m, (rows_m, cols_m)), shape=(n_total, n_total)).tocsr()

    k_path = matrices_dir / k_filename
    m_path = matrices_dir / m_filename if m_filename else None

    mmwrite(k_path, mat_k, comment=f"Demo 3D FEM Stiffness Matrix K ({nx_nodes}x{ny_nodes}x{nz_nodes} nodes, {d} DOF/node)")
    if m_path is not None:
        mmwrite(m_path, mat_m, comment=f"Demo 3D FEM Mass Matrix M ({nx_nodes}x{ny_nodes}x{nz_nodes} nodes, {d} DOF/node)")

    return inspect_mtx_file(k_path)

