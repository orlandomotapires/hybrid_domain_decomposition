"""Default simulation parameters: the single source for the Studio, the validator and the docs.

New simulations start from :data:`DEFAULT_SIMULATION_PARAMETERS`, and
:func:`libs.runtime.utils.validate_and_normalize_simulation_parameters` fills partitioning keys a
parameter file leaves out from the same values. ``tests/test_wiki.py`` checks that the "Default:"
badges in ``hdd/services/data/wiki.json`` agree with it.
"""

from __future__ import annotations

import copy
from typing import Any

QA = "quantum_annealing"
QAOA = "quantum_approximation_optimizer"

DEFAULT_SIMULATION_PARAMETERS: dict[str, Any] = {
    "general_parameters": {"dof_per_node": 1, "seed": 42},
    "coarsening_parameters": {
        "coarsen_inferior_limit": 100,
        "coarsen_superior_limit": 175,
        "max_levels": 15,
        "weight": "weight",
        "strategy": "modified",
        "coarsen_ratio": 0.85,
    },
    "partitioning_parameters": {
        "partitioning_strategy": "metis_partitioning",
        "common": {"k_target": 4, "balance_tolerance": 2.0},  # balance_tolerance in percent
        "strategies": {
            "metis_partitioning": {},
            QA: {
                "qubo_balance_lambda": 2.0,
                "num_starts": 20,
                "num_reads": 20,
                "balance_violation_lambda": 5.0,
                "simulated": True,
            },
            QAOA: {
                "qubo_balance_lambda": 2.0,
                "num_starts": 5,
                "num_steps": 5,
                "num_shots": 10,
                "balance_violation_lambda": 5.0,
                "circuit_depth": 1,
                "adam_learning_rate": 0.1,
                "simulated": True,
            },
        },
    },
    "uncoarsening_parameters": {
        "refine_objective": "cut_balance",
        "refine_balance_lambda": 1.0,
        "refine_max_passes_per_level": 50,
        "refine_max_moves_per_pass": 5000,
        "validate_node_weights": True,
    },
}


# Keys a parameter file may set that have no default (optional settings).
OPTIONAL_KEYS: dict[tuple[str, ...], set[str]] = {
    ("coarsening_parameters",): {"max_node_weight"},
    ("partitioning_parameters", "strategies", QA): {"qpu_solver_name", "qpu_region", "qpu_problem_label"},
    ("partitioning_parameters", "strategies", QAOA): {"qlm_qpu_name", "qlm_job_timeout_seconds"},
}


def unknown_parameter_keys(parameters: dict[str, Any]) -> list[str]:
    """Dotted paths of keys the pipeline does not know (most often a typo that silently keeps a default)."""
    unknown: list[str] = []

    def walk(given: Any, known: Any, path: tuple[str, ...]) -> None:
        if not isinstance(given, dict) or not isinstance(known, dict):
            return
        allowed = set(known) | OPTIONAL_KEYS.get(path, set())
        for key, value in given.items():
            if key not in allowed:
                unknown.append(".".join((*path, str(key))))
            elif isinstance(known.get(key), dict) and known.get(key):
                walk(value, known[key], (*path, key))
            elif path[-1:] == ("strategies",):
                walk(value, known.get(key, {}), (*path, key))

    walk(parameters, DEFAULT_SIMULATION_PARAMETERS, ())
    return unknown


def default_parameters() -> dict[str, Any]:
    """A fresh, mutable copy of the defaults."""
    return copy.deepcopy(DEFAULT_SIMULATION_PARAMETERS)


def common_defaults() -> dict[str, Any]:
    return dict(DEFAULT_SIMULATION_PARAMETERS["partitioning_parameters"]["common"])


def strategy_defaults(strategy: str) -> dict[str, Any]:
    return dict(DEFAULT_SIMULATION_PARAMETERS["partitioning_parameters"]["strategies"].get(strategy, {}))
