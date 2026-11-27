"""How large a coarse graph each partitioning backend can take.

Quantum backends only see the coarse graph, so its node count must fit them. The pipeline
checks the local backends right after coarsening (:func:`local_capacity_error`), before any
expensive work; the tuner and the Studio use :func:`backend_capacity` to plan runs.
"""

from __future__ import annotations

import os
import re
from typing import Any

DWAVE_CLIQUE_LIMIT = 175
# PennyLane statevector emulation: 2**n amplitudes per state, kept several times over by the
# optimizer's backpropagation. 18 qubits stays within a laptop's memory.
QAOA_EMULATED_QUBIT_LIMIT = 18
QLM_DEFAULT_QUBITS = 10
# Simulated annealing builds a dense QUBO (n**2 / 2 terms). The thesis' "Big" scale runs it on
# 1500-2500 coarse nodes; well beyond that (a coarsening that stalled at the fine graph) it
# would need many gigabytes.
SIMULATED_ANNEALING_NODE_LIMIT = 3000
SIMULATED_ANNEALING_LIMIT_ENV = "HDD_SIMULATED_QA_NODE_LIMIT"


def simulated_annealing_node_limit() -> int:
    """Node limit for simulated annealing; ``HDD_SIMULATED_QA_NODE_LIMIT`` raises it on big machines."""
    raw = os.environ.get(SIMULATED_ANNEALING_LIMIT_ENV, "").strip()
    try:
        value = int(raw) if raw else SIMULATED_ANNEALING_NODE_LIMIT
    except ValueError:
        value = SIMULATED_ANNEALING_NODE_LIMIT
    return max(2, value)


def qlm_qubit_limit(qpu_name: str | None) -> int:
    m = re.search(r"(\d+)QPU|QPU(\d+)", qpu_name or "", re.IGNORECASE)
    if m:
        n = int(m.group(1) or m.group(2))
        if n > 0:
            return n
    return QLM_DEFAULT_QUBITS


def backend_capacity(partitioning_parameters: dict[str, Any]) -> tuple[int | None, str | None]:
    """Largest coarse graph the partitioning backend accepts, or (None, None) when unbounded."""
    strategy = partitioning_parameters.get("partitioning_strategy")
    sp = (partitioning_parameters.get("strategies") or {}).get(strategy) or {}
    simulated = sp.get("simulated", True)
    if strategy == "quantum_annealing":
        if simulated:
            return simulated_annealing_node_limit(), "simulated annealing (dense QUBO)"
        return DWAVE_CLIQUE_LIMIT, "D-Wave clique embedding"
    if strategy == "quantum_approximation_optimizer":
        if simulated:
            return QAOA_EMULATED_QUBIT_LIMIT, "QAOA statevector emulation"
        limit = qlm_qubit_limit(sp.get("qlm_qpu_name"))
        return limit, f"QLM QPU ({limit} qubits)"
    return None, None


def qpu_workload(strategy: str, strategy_parameters: dict[str, Any] | None, k_target: int) -> dict[str, Any] | None:
    """Remote calls one run makes: ``{"submissions", "samples", "unit"}``, or None for METIS.

    Recursive bisection into k parts runs k - 1 bipartitions per start. Annealing submits one
    problem per bipartition; QAOA one circuit job per optimizer step plus a final sampling job.
    Parameters left out take the pipeline's defaults.
    """
    from libs.runtime.defaults import strategy_defaults

    params = {**strategy_defaults(strategy), **(strategy_parameters or {})}
    bisections = max(1, int(k_target) - 1)
    starts = max(1, int(params.get("num_starts", 1)))
    if strategy == "quantum_annealing":
        submissions = starts * bisections
        return {"submissions": submissions, "samples": submissions * max(1, int(params.get("num_reads", 1))), "unit": "reads"}
    if strategy == "quantum_approximation_optimizer":
        submissions = starts * bisections * (max(1, int(params.get("num_steps", 1))) + 1)
        return {"submissions": submissions, "samples": submissions * max(1, int(params.get("num_shots", 1))), "unit": "shots"}
    return None


def local_capacity_error(partitioning_parameters: dict[str, Any], coarse_nodes: int) -> str | None:
    """Why a local (simulated) backend cannot take a coarse graph of ``coarse_nodes``, else None.

    Remote backends are left to their own checks, which know the real device size.
    """
    strategy = partitioning_parameters.get("partitioning_strategy")
    sp = (partitioning_parameters.get("strategies") or {}).get(strategy) or {}
    if strategy not in ("quantum_annealing", "quantum_approximation_optimizer") or not sp.get("simulated", True):
        return None
    capacity, what = backend_capacity(partitioning_parameters)
    if capacity is None or coarse_nodes <= capacity:
        return None
    hint = (f" (set {SIMULATED_ANNEALING_LIMIT_ENV} to allow more)" if strategy == "quantum_annealing" else "")
    return (
        f"The coarse graph has {coarse_nodes} nodes, above the {what} limit of {capacity}{hint}. "
        "Lower coarsen_superior_limit / coarsen_inferior_limit so coarsening goes further, "
        "or use a hardware backend or METIS."
    )
