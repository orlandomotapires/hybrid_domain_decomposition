"""User-facing names of methods and options. Pure data, shared by every front end."""

from __future__ import annotations

METHOD_LABELS = {
    "metis": "METIS (Classical)",
    "qa_emulated": "Quantum Annealing (Emulated)",
    "qa_hardware": "Quantum Annealing (D-Wave QPU)",
    "qaoa_emulated": "QAOA (Emulated)",
    "qaoa_hardware": "QAOA (QLM Hardware)",
}

METHOD_SHORT_LABELS = {
    "metis": "METIS",
    "qa_emulated": "QA Emulated",
    "qa_hardware": "QA D-Wave",
    "qaoa_emulated": "QAOA Emulated",
    "qaoa_hardware": "QAOA QLM",
}

#: Categorical colour slot of each method in plots, fixed so a method keeps its colour everywhere.
METHOD_SLOT = {"metis": 0, "qa_emulated": 1, "qa_hardware": 3, "qaoa_emulated": 2, "qaoa_hardware": 4}

STAGE_LABELS = {
    "initialization": "Graph construction",
    "coarsening": "Coarsening",
    "partitioning": "Partitioning",
    "uncoarsening": "Refinement",
    "permutation": "Permutation",
}

JOB_TYPE_LABELS = {"single": "Simulation", "batch": "Batch", "tuning": "Tuning"}
JOB_STATUS_LABELS = {"running": "Running", "completed": "Completed", "failed": "Failed", "cancelled": "Cancelled"}


def method_key(strategy: str | None, simulated: bool | None = None) -> str | None:
    """Method key of a partitioning strategy (or a batch algorithm key) and its ``simulated`` flag."""
    if not strategy:
        return None
    if strategy in METHOD_LABELS:
        return strategy
    if strategy in ("metis_partitioning", "metis"):
        return "metis"
    hardware = simulated is False
    if strategy == "quantum_approximation_optimizer" or strategy.startswith("qaoa"):
        return "qaoa_hardware" if hardware else "qaoa_emulated"
    if strategy == "quantum_annealing" or strategy.startswith("qa"):
        return "qa_hardware" if hardware else "qa_emulated"
    return None


def method_label(strategy: str | None, simulated: bool | None = None, short: bool = False) -> str:
    key = method_key(strategy, simulated)
    if key is None:
        return strategy or "—"
    return (METHOD_SHORT_LABELS if short else METHOD_LABELS)[key]
