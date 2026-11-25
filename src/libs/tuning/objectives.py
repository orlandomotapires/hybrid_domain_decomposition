"""Objective metrics a tuning study can optimise (all minimised).

The user picks one or more of :data:`OBJECTIVES` (checkboxes in the Studio). With a single
objective the study is single-objective; with several it is either a Pareto study (one Optuna
direction per objective) or a weighted sum of objectives normalised by a reference run.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

DEFAULT_BAND_PERCENT = 1.0

OBJECTIVES: dict[str, dict[str, str]] = {
    "edge_cut": {
        "label": "Edge cut",
        "description": "Cut weight / total edge weight of the fine graph (lower = less coupling between subdomains).",
    },
    "imbalance": {
        "label": "Imbalance",
        "description": "Heaviest part / ideal part weight - 1 (0 = perfectly balanced).",
    },
    "band_quality": {
        "label": "Band quality",
        "description": "1 - fraction of nonzeros within X% of n from the diagonal in the reordered matrix.",
    },
    "bandwidth": {
        "label": "Bandwidth",
        "description": "Bandwidth of the reordered matrix divided by n.",
    },
    "time": {
        "label": "Run time",
        "description": "Wall time of the decomposition pipeline in seconds.",
    },
}


def _percent_label(percent: float) -> str:
    value = round(float(percent), 10)
    if float(value).is_integer():
        return f"{value:.1f}%"
    return f"{value:.10f}".rstrip("0").rstrip(".") + "%"


def validate_objectives(objectives: list[str]) -> list[str]:
    cleaned = [str(o) for o in objectives or []]
    if not cleaned:
        raise ValueError("Select at least one objective")
    unknown = [o for o in cleaned if o not in OBJECTIVES]
    if unknown:
        raise ValueError(f"Unknown objectives: {unknown}. Valid: {sorted(OBJECTIVES)}")
    return list(dict.fromkeys(cleaned))


def read_run_metrics(run_dir: Path) -> dict[str, Any]:
    """Merge decomposition_metrics.json and run_metrics.json of one run folder."""
    run_dir = Path(run_dir)
    out: dict[str, Any] = {"decomposition": {}, "structural": {}}
    dm = run_dir / "decomposition_metrics.json"
    if dm.exists():
        out["decomposition"] = json.loads(dm.read_text(encoding="utf-8"))
    rm = run_dir / "run_metrics.json"
    if rm.exists():
        matrix = json.loads(rm.read_text(encoding="utf-8")).get("matrix", {})
        out["structural"] = matrix.get("structural_metrics", {})
        if not out["decomposition"]:
            out["decomposition"] = matrix.get("decomposition_metrics", {})
    return out


def objective_values(
    metrics: dict[str, Any],
    objectives: list[str],
    *,
    band_percent: float = DEFAULT_BAND_PERCENT,
) -> dict[str, float]:
    """Raw value of each objective from :func:`read_run_metrics` output. Raises KeyError if missing."""
    dec = metrics.get("decomposition") or {}
    permuted = (metrics.get("structural") or {}).get("permuted") or {}
    values: dict[str, float] = {}
    for name in objectives:
        if name == "edge_cut":
            values[name] = float(dec["edge_cut_fraction"])
        elif name == "imbalance":
            values[name] = float(dec["imbalance"])
        elif name == "time":
            values[name] = float(dec["timing"]["total_sec"])
        elif name == "bandwidth":
            values[name] = float(permuted["bandwidth"]) / max(float(permuted["n"]), 1.0)
        elif name == "band_quality":
            key = f"frac_within_|i-j|<={_percent_label(band_percent)}_of_n"
            values[name] = 1.0 - float(permuted[key])
        else:  # pragma: no cover - guarded by validate_objectives
            raise KeyError(name)
    return values


def weighted_score(
    values: dict[str, float],
    weights: dict[str, float],
    reference: dict[str, float] | None,
) -> float:
    """Sum of w_i * v_i / ref_i (ref = reference run values, so objectives are scale-free)."""
    total = 0.0
    for name, value in values.items():
        w = float(weights.get(name, 1.0))
        ref = abs(float((reference or {}).get(name, 1.0)))
        total += w * value / (ref if ref > 1e-12 else 1.0)
    return float(total)


def is_finite(values: dict[str, float]) -> bool:
    return all(math.isfinite(v) for v in values.values())
