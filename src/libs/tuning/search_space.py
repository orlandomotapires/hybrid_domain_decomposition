"""Declarative search space for the tuner.

Each tunable parameter has a stable ``key``. A study's ``search_space`` maps keys to
``{"free": bool, "low"/"high"/"log" | "choices"}``. Fixed keys keep the value from the base
parameters. ``k_target`` and ``partitioning_strategy`` are fixed by default (the user ticks them
free in the Studio).

Two keys are virtual and expand into ``coarsen_inferior_limit``/``coarsen_superior_limit``:

* ``coarse_target``: superior limit = number of coarse-graph nodes we aim for;
* ``coarse_window``: inferior = max(k, round(target * (1 - window))).

Expressing coarsening as a target size makes the space transferable between matrices.
"""

from __future__ import annotations

import copy
from typing import Any

from libs.tuning.feasibility import DWAVE_CLIQUE_LIMIT, QAOA_EMULATED_QUBIT_LIMIT, backend_capacity

STRATEGIES = ["metis_partitioning", "quantum_annealing", "quantum_approximation_optimizer"]
QA = "quantum_annealing"
QAOA = "quantum_approximation_optimizer"

# key, label, group, type, path (None = virtual), defaults, condition on partitioning strategy
PARAMETERS: list[dict[str, Any]] = [
    {"key": "partitioning_strategy", "label": "Partitioning strategy", "group": "partitioning", "type": "categorical",
     "path": ["partitioning_parameters", "partitioning_strategy"], "choices": STRATEGIES, "free": False},
    {"key": "k_target", "label": "k (number of parts)", "group": "partitioning", "type": "int",
     "path": ["partitioning_parameters", "common", "k_target"], "low": 2, "high": 16, "free": False},
    {"key": "balance_tolerance", "label": "Balance tolerance", "group": "partitioning", "type": "float",
     "path": ["partitioning_parameters", "common", "balance_tolerance"], "low": 1.0, "high": 30.0, "free": True},  # percent
    {"key": "coarse_target", "label": "Coarse graph target size", "group": "coarsening", "type": "int",
     "path": None, "low": 20, "high": 400, "free": True},
    {"key": "coarse_window", "label": "Coarse size window", "group": "coarsening", "type": "float",
     "path": None, "low": 0.2, "high": 0.8, "free": False},
    {"key": "coarsening_strategy", "label": "Matching strategy", "group": "coarsening", "type": "categorical",
     "path": ["coarsening_parameters", "strategy"], "choices": ["random", "sorted", "modified", "light"], "free": True},
    {"key": "coarsen_ratio", "label": "Coarsen ratio", "group": "coarsening", "type": "float",
     "path": ["coarsening_parameters", "coarsen_ratio"], "low": 0.6, "high": 0.95, "free": True},
    {"key": "max_levels", "label": "Max levels", "group": "coarsening", "type": "int",
     "path": ["coarsening_parameters", "max_levels"], "low": 5, "high": 40, "free": False},
    {"key": "refine_objective", "label": "Refine objective", "group": "uncoarsening", "type": "categorical",
     "path": ["uncoarsening_parameters", "refine_objective"], "choices": ["cut", "cut_balance"], "free": True},
    {"key": "refine_balance_lambda", "label": "Refine balance lambda", "group": "uncoarsening", "type": "float",
     "path": ["uncoarsening_parameters", "refine_balance_lambda"], "low": 0.01, "high": 100.0, "log": True, "free": True},
    {"key": "refine_max_passes_per_level", "label": "Refine passes per level", "group": "uncoarsening", "type": "int",
     "path": ["uncoarsening_parameters", "refine_max_passes_per_level"], "low": 1, "high": 100, "log": True, "free": True},
    # Quantum annealing
    {"key": "qa.qubo_balance_lambda", "label": "QA QUBO balance lambda", "group": "quantum_annealing", "type": "float",
     "path": ["partitioning_parameters", "strategies", QA, "qubo_balance_lambda"], "low": 0.01, "high": 100.0, "log": True,
     "free": True, "when": QA},
    {"key": "qa.num_reads", "label": "QA reads", "group": "quantum_annealing", "type": "int",
     "path": ["partitioning_parameters", "strategies", QA, "num_reads"], "low": 1, "high": 50, "free": True, "when": QA},
    {"key": "qa.num_starts", "label": "QA starts", "group": "quantum_annealing", "type": "int",
     "path": ["partitioning_parameters", "strategies", QA, "num_starts"], "low": 1, "high": 30, "free": False, "when": QA},
    # QAOA
    {"key": "qaoa.qubo_balance_lambda", "label": "QAOA QUBO balance lambda", "group": "qaoa", "type": "float",
     "path": ["partitioning_parameters", "strategies", QAOA, "qubo_balance_lambda"], "low": 0.01, "high": 100.0, "log": True,
     "free": True, "when": QAOA},
    {"key": "qaoa.circuit_depth", "label": "QAOA circuit depth", "group": "qaoa", "type": "int",
     "path": ["partitioning_parameters", "strategies", QAOA, "circuit_depth"], "low": 1, "high": 6, "free": True, "when": QAOA},
    {"key": "qaoa.num_steps", "label": "QAOA optimizer steps", "group": "qaoa", "type": "int",
     "path": ["partitioning_parameters", "strategies", QAOA, "num_steps"], "low": 1, "high": 50, "free": True, "when": QAOA},
    {"key": "qaoa.num_shots", "label": "QAOA shots", "group": "qaoa", "type": "int",
     "path": ["partitioning_parameters", "strategies", QAOA, "num_shots"], "low": 1, "high": 50, "free": False, "when": QAOA},
    {"key": "qaoa.adam_learning_rate", "label": "QAOA Adam learning rate", "group": "qaoa", "type": "float",
     "path": ["partitioning_parameters", "strategies", QAOA, "adam_learning_rate"], "low": 0.001, "high": 1.0, "log": True,
     "free": True, "when": QAOA},
    {"key": "qaoa.num_starts", "label": "QAOA starts", "group": "qaoa", "type": "int",
     "path": ["partitioning_parameters", "strategies", QAOA, "num_starts"], "low": 1, "high": 30, "free": False, "when": QAOA},
]
PARAMETERS_BY_KEY = {p["key"]: p for p in PARAMETERS}


def _get(d: dict, path: list[str], default=None):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return default
        d = d[p]
    return d


def _set(d: dict, path: list[str], value) -> None:
    for p in path[:-1]:
        d = d.setdefault(p, {})
    d[path[-1]] = value


def _base_coarse_values(base: dict[str, Any]) -> tuple[int, float]:
    cp = base.get("coarsening_parameters", {})
    inferior = int(cp.get("coarsen_inferior_limit") or 1)
    superior = cp.get("coarsen_superior_limit")
    superior = int(superior) if superior is not None else inferior
    window = 1.0 - inferior / superior if superior > 0 else 0.5
    return superior, round(min(max(window, 0.0), 0.95), 4)


def fixed_value(key: str, base: dict[str, Any]):
    spec = PARAMETERS_BY_KEY[key]
    if key == "coarse_target":
        return _base_coarse_values(base)[0]
    if key == "coarse_window":
        return _base_coarse_values(base)[1]
    return _get(base, spec["path"])


def default_search_space(base: dict[str, Any], features: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Full search-space config with ranges adapted to the matrix (graph size) when known."""
    space: dict[str, dict[str, Any]] = {}
    n_nodes = int((features or {}).get("graph", {}).get("nodes") or 0)
    for spec in PARAMETERS:
        entry: dict[str, Any] = {"free": bool(spec["free"])}
        if spec["type"] == "categorical":
            entry["choices"] = list(spec["choices"])
        else:
            entry["low"], entry["high"] = spec["low"], spec["high"]
            if spec.get("log"):
                entry["log"] = True
        space[spec["key"]] = entry
    if n_nodes:
        k = int(fixed_value("k_target", base) or 2)
        space["coarse_target"]["low"] = max(2 * k, 10)
        space["coarse_target"]["high"] = max(space["coarse_target"]["low"] + 1, min(n_nodes // 2, 2000))
        space["k_target"]["high"] = max(2, min(64, n_nodes // 4))
    return space


def normalize_search_space(
    space: dict[str, Any] | None,
    base: dict[str, Any],
    features: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fill missing keys with defaults and validate ranges."""
    result = default_search_space(base, features)
    for key, entry in (space or {}).items():
        if key not in PARAMETERS_BY_KEY:
            raise ValueError(f"Unknown search-space parameter: {key}")
        if not isinstance(entry, dict):
            raise ValueError(f"search_space[{key}] must be an object")
        merged = {**result[key], **entry}
        spec = PARAMETERS_BY_KEY[key]
        if spec["type"] == "categorical":
            choices = list(merged.get("choices") or [])
            invalid = [c for c in choices if c not in spec["choices"]]
            if not choices or invalid:
                raise ValueError(f"search_space[{key}].choices must be a non-empty subset of {spec['choices']}")
            merged["choices"] = choices
        else:
            low, high = float(merged["low"]), float(merged["high"])
            if spec["type"] == "int":
                low, high = int(round(low)), int(round(high))
            if low > high:
                raise ValueError(f"search_space[{key}]: low must be <= high")
            if merged.get("log") and low <= 0:
                raise ValueError(f"search_space[{key}]: log ranges need low > 0")
            merged["low"], merged["high"] = low, high
        merged["free"] = bool(merged.get("free"))
        result[key] = merged
    return result


def free_keys(space: dict[str, dict[str, Any]]) -> list[str]:
    return [k for k, v in space.items() if v.get("free")]


def _distribution_name(key: str, strategy: str) -> str:
    # Quantum backends cap the coarse size, so their coarse_target range is a separate dimension.
    if key == "coarse_target" and strategy in (QA, QAOA):
        return f"coarse_target.{strategy}"
    return key


def _coarse_cap(parameters: dict[str, Any]) -> int | None:
    cap, _ = backend_capacity(parameters["partitioning_parameters"])
    return cap


def suggest_parameters(trial, space: dict[str, dict[str, Any]], base: dict[str, Any]) -> dict[str, Any]:
    """Ask an Optuna trial for every free parameter and return a full parameter set."""
    params = copy.deepcopy(base)
    values: dict[str, Any] = {}

    def _suggest(key: str, name: str | None = None, high_cap: float | None = None):
        spec, entry = PARAMETERS_BY_KEY[key], space[key]
        name = name or key
        if spec["type"] == "categorical":
            return trial.suggest_categorical(name, entry["choices"])
        low, high = entry["low"], entry["high"]
        if high_cap is not None:
            high = max(low, min(high, high_cap))
        if spec["type"] == "int":
            return trial.suggest_int(name, int(low), int(high), log=bool(entry.get("log")))
        return trial.suggest_float(name, float(low), float(high), log=bool(entry.get("log")))

    strategy = _suggest("partitioning_strategy") if space["partitioning_strategy"]["free"] else fixed_value("partitioning_strategy", base)
    values["partitioning_strategy"] = strategy
    _set(params, PARAMETERS_BY_KEY["partitioning_strategy"]["path"], strategy)

    for spec in PARAMETERS:
        key = spec["key"]
        if key == "partitioning_strategy" or (spec.get("when") and spec["when"] != strategy):
            continue
        if not space[key]["free"]:
            values[key] = fixed_value(key, base)
            continue
        cap = _coarse_cap(params) if key == "coarse_target" else None
        values[key] = _suggest(key, _distribution_name(key, strategy), cap)
        if spec["path"] is not None:
            _set(params, spec["path"], values[key])

    apply_coarse_virtuals(params, values["coarse_target"], values["coarse_window"])
    return params


def apply_coarse_virtuals(params: dict[str, Any], target: int, window: float) -> None:
    k = int(params["partitioning_parameters"]["common"]["k_target"])
    target = max(1, int(target))
    inferior = max(1, min(target, max(k, int(round(target * (1.0 - float(window)))))))
    cp = params["coarsening_parameters"]
    cp["coarsen_superior_limit"] = target
    cp["coarsen_inferior_limit"] = inferior


def parameters_to_trial_values(params: dict[str, Any], space: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Distribution values that reproduce ``params`` (for enqueue_trial / warm starts)."""
    strategy = _get(params, PARAMETERS_BY_KEY["partitioning_strategy"]["path"])
    out: dict[str, Any] = {}
    for spec in PARAMETERS:
        key = spec["key"]
        if not space[key]["free"] or (spec.get("when") and spec["when"] != strategy):
            continue
        value = fixed_value(key, params)
        if value is None:
            continue
        entry = space[key]
        if spec["type"] == "categorical":
            if value not in entry["choices"]:
                continue
        else:
            value = int(value) if spec["type"] == "int" else float(value)
            value = min(max(value, entry["low"]), entry["high"])
        out[_distribution_name(key, strategy)] = value
    return out


def distributions_for(space: dict[str, dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    """Optuna distributions of the free parameters active for ``params``' strategy."""
    from optuna.distributions import CategoricalDistribution, FloatDistribution, IntDistribution

    strategy = _get(params, PARAMETERS_BY_KEY["partitioning_strategy"]["path"])
    cap = _coarse_cap(params)
    out: dict[str, Any] = {}
    for spec in PARAMETERS:
        key, entry = spec["key"], space[spec["key"]]
        if not entry["free"] or (spec.get("when") and spec["when"] != strategy):
            continue
        name = _distribution_name(key, strategy)
        if spec["type"] == "categorical":
            out[name] = CategoricalDistribution(entry["choices"])
            continue
        low, high = entry["low"], entry["high"]
        if key == "coarse_target" and cap is not None:
            high = max(low, min(high, cap))
        if spec["type"] == "int":
            out[name] = IntDistribution(int(low), int(high), log=bool(entry.get("log")))
        else:
            out[name] = FloatDistribution(float(low), float(high), log=bool(entry.get("log")))
    return out


def trial_values_in_range(params: dict[str, Any], space: dict[str, dict[str, Any]]) -> bool:
    """True when every free value of ``params`` lies inside the space (no clamping needed)."""
    strategy = _get(params, PARAMETERS_BY_KEY["partitioning_strategy"]["path"])
    for spec in PARAMETERS:
        key, entry = spec["key"], space[spec["key"]]
        if not entry["free"] or (spec.get("when") and spec["when"] != strategy):
            continue
        value = fixed_value(key, params)
        if value is None:
            return False
        if spec["type"] == "categorical":
            if value not in entry["choices"]:
                return False
        elif not (entry["low"] <= float(value) <= entry["high"]):
            return False
    return True


def fixed_keys_match(params: dict[str, Any], base: dict[str, Any], space: dict[str, dict[str, Any]]) -> bool:
    """True when ``params`` agrees with ``base`` on every fixed (non-free) parameter."""
    strategy = _get(params, PARAMETERS_BY_KEY["partitioning_strategy"]["path"])
    for spec in PARAMETERS:
        key = spec["key"]
        if space[key]["free"] or (spec.get("when") and spec["when"] != strategy):
            continue
        if fixed_value(key, params) != fixed_value(key, base):
            return False
    return True


def describe_parameters() -> list[dict[str, Any]]:
    """Static metadata for the Studio form."""
    return [
        {k: v for k, v in spec.items() if k != "path"} | {"virtual": spec["path"] is None}
        for spec in PARAMETERS
    ]


__all__ = [
    "DWAVE_CLIQUE_LIMIT",
    "QAOA_EMULATED_QUBIT_LIMIT",
    "PARAMETERS",
    "default_search_space",
    "normalize_search_space",
    "suggest_parameters",
    "parameters_to_trial_values",
    "describe_parameters",
    "apply_coarse_virtuals",
]
