"""Quantum-annealing partitioning: simulated (neal) or on a D-Wave QPU.

Imports are lazy: the Studio's hardware probe imports ``qa.dwave_access`` and must not load
neal, PennyLane or the QAOA stack with it. The QAOA names are re-exported here for older callers.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "anneal_bipartition": ".annealing",
    "get_qpu_dense_clique_capacity": ".dwave_access",
    "uses_dense_balance_qubo": ".dwave_access",
    "get_qlm_qpu_api_summary": "..qaoa.qlm_access",
    "probe_qlm_backend_qubit_limit": "..qaoa.qlm_access",
    "qaoa_bipartition": "..qaoa.qaoa",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(_EXPORTS[name], __name__), name)
