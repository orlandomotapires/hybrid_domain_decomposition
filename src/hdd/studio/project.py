"""A snapshot of everything in the workspace that the project tree shows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hdd.services import batch, matrices, results, simulations, tuning
from libs.runtime import workspace


@dataclass
class ProjectSnapshot:
    root: Path
    matrices: list[dict[str, Any]] = field(default_factory=list)
    simulations: list[dict[str, Any]] = field(default_factory=list)
    runs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    studies: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    batch_runs: list[dict[str, Any]] = field(default_factory=list)
    has_batch_config: bool = False
    problems: list[tuple[str, str, str]] = field(default_factory=list)  # (severity, message, location)


def load_snapshot(jobs: Any = None) -> ProjectSnapshot:
    """Read the workspace through the services. Runs on a worker thread; never raises for one bad item.

    ``jobs`` (the job manager) lets running tuning studies show as running.
    """
    snap = ProjectSnapshot(root=workspace.root())
    snap.matrices = matrices.list_matrices()["matrices"]
    for matrix in snap.matrices:
        if matrix.get("error"):
            snap.problems.append(("error", matrix["error"], f"Matrices › {matrix['id']}"))
    snap.simulations = simulations.list_simulations()["demonstrators"]
    studies_by_sim: dict[str, list] = {}
    try:
        for study in tuning.list_studies(None, jobs):
            studies_by_sim.setdefault(study["simulation"], []).append(study)
    except Exception as exc:
        snap.problems.append(("warning", f"Tuning studies could not be read: {exc}", "Simulations"))
    for sim in snap.simulations:
        sim_id = sim["id"]
        if sim.get("error"):
            snap.problems.append(("error", sim["error"], f"Simulations › {sim_id}"))
            continue
        matrix = sim.get("matrix") or {}
        if matrix.get("error") or not matrix.get("ready", True):
            snap.problems.append(("warning", f"Input matrix {sim['simulation_config'].get('input_matrix')!r} is not available", f"Simulations › {sim_id}"))
        snap.runs[sim_id] = results.list_runs(sim_id)["runs"]
        snap.studies[sim_id] = studies_by_sim.get(sim_id, [])
    snap.batch_runs = batch.list_batch_runs()["batch_runs"]
    snap.has_batch_config = workspace.batch_config_path().exists()
    return snap
