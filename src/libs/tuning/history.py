"""Global run history (``tuning/history.jsonl``): one line per finished pipeline run.

Every run (single, batch or tuning trial) appends its parameters and quality metrics, so studies
can warm-start from previous runs on the same matrix and auto-select can reuse the best settings
found for similar matrices (kNN on :func:`libs.tuning.features.feature_vector`).

Set ``HDD_DISABLE_HISTORY=1`` to skip recording (tests), ``HDD_HISTORY_PATH`` to relocate it.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from libs.runtime import workspace
from libs.tuning.objectives import objective_values, read_run_metrics, weighted_score


def history_path() -> Path:
    return workspace.history_path()


def record_run(
    run_dir: Path,
    *,
    matrix_id: str,
    parameters: dict[str, Any],
    simulation: str | None,
    source: str,
) -> None:
    if os.environ.get("HDD_DISABLE_HISTORY"):
        return
    metrics = read_run_metrics(Path(run_dir))
    if not metrics.get("decomposition"):
        return
    try:
        run_rel = str(Path(run_dir).resolve().relative_to(workspace.root()))
    except ValueError:
        run_rel = str(run_dir)
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "matrix_id": matrix_id,
        "simulation": simulation,
        "source": source,
        "run_dir": run_rel,
        "parameters": parameters,
        "metrics": metrics,
    }
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=float) + "\n")


def load_history(matrix_id: str | None = None) -> list[dict[str, Any]]:
    path = history_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if matrix_id is None or row.get("matrix_id") == matrix_id:
            rows.append(row)
    return rows


def best_runs(
    rows: list[dict[str, Any]],
    objectives: list[str],
    *,
    weights: dict[str, float] | None = None,
    band_percent: float = 1.0,
    top: int = 3,
) -> list[dict[str, Any]]:
    """Rows ranked by the weighted objective score (normalised by the per-objective median)."""
    scored: list[tuple[dict[str, float], dict[str, Any]]] = []
    for row in rows:
        try:
            scored.append((objective_values(row["metrics"], objectives, band_percent=band_percent), row))
        except (KeyError, TypeError, ValueError):
            continue
    if not scored:
        return []
    reference = {o: float(np.median([v[o] for v, _ in scored])) for o in objectives}
    ranked = sorted(scored, key=lambda item: weighted_score(item[0], weights or {}, reference))
    return [dict(row, objective_values=values) for values, row in ranked[:top]]


def similar_matrix_runs(
    matrix_id: str,
    dof_per_node: int,
    objectives: list[str],
    *,
    neighbours: int = 3,
    band_percent: float = 1.0,
) -> list[dict[str, Any]]:
    """Best history runs on the matrices whose features are closest to ``matrix_id`` (A3)."""
    from libs.tuning.features import compute_matrix_features, feature_vector

    rows = load_history()
    others = sorted({r["matrix_id"] for r in rows if r.get("matrix_id") and r["matrix_id"] != matrix_id})
    if not others:
        return []
    target = feature_vector(compute_matrix_features(matrix_id, dof_per_node))
    distances: list[tuple[float, str]] = []
    for other in others:
        try:
            dof = dof_per_node if compute_matrix_features(other, 1)["matrix"]["n"] % dof_per_node == 0 else 1
            distances.append((float(np.linalg.norm(feature_vector(compute_matrix_features(other, dof)) - target)), other))
        except (FileNotFoundError, ValueError):
            continue
    result: list[dict[str, Any]] = []
    for dist, other in sorted(distances)[:neighbours]:
        for row in best_runs([r for r in rows if r["matrix_id"] == other], objectives, band_percent=band_percent, top=1):
            result.append(dict(row, feature_distance=dist))
    return result
