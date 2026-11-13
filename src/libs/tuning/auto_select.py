"""Mode A: one-shot parameter selection from the matrix features.

A1 (rules) picks the block size, a coarse-graph target size and refinement settings; A2 (guided
dry-run) tries a small grid of coarsening settings with the real ``coarsen_chain`` and keeps the
one that lands closest to the target with the most even supernode weights. The partitioning
strategy and k come from the base parameters (the user's choice).
"""

from __future__ import annotations

import copy
import math
from typing import Any

from libs.runtime.matrix_library import resolve_matrix
from libs.runtime.utils import load_mtx, validate_and_normalize_simulation_parameters
from libs.tuning.feasibility import backend_capacity, check_feasibility
from libs.tuning.features import build_pipeline_graph, compute_matrix_features
from libs.tuning.search_space import apply_coarse_virtuals

STRATEGY_GRID = ["light", "sorted", "modified", "random"]
RATIO_GRID = [0.85, 0.95]
WINDOW = 0.5


def _metis_like_target(n_nodes: int, k: int) -> int:
    # METIS coarsens to roughly max(n / (20 log2 k), 30 k) vertices.
    by_k = 30 * max(k, 2)
    by_n = n_nodes / (20.0 * max(math.log2(max(k, 2)), 1.0))
    return int(max(min(max(by_k, by_n), n_nodes // 2), 2 * k, 10))


def auto_select_parameters(matrix_id: str, base_parameters: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"parameters", "rationale", "dry_run", "feasible", "candidates"}``."""
    params = copy.deepcopy(validate_and_normalize_simulation_parameters(base_parameters))
    rationale: list[str] = []

    A = load_mtx(str(resolve_matrix(matrix_id)), matrix_id)
    n = int(A.shape[0])
    dof = int(params["general_parameters"]["dof_per_node"])
    if n % dof != 0:
        rationale.append(f"dof_per_node={dof} does not divide n={n}; using 1")
        dof = 1
        params["general_parameters"]["dof_per_node"] = 1
    features = compute_matrix_features(matrix_id, dof)
    n_nodes = int(features["graph"]["nodes"])
    rationale.append(
        f"Graph has {n_nodes} nodes, {features['graph']['edges']} edges "
        f"(mean degree {features['graph']['degree_mean']:.1f}, {features['graph']['connected_components']} component(s))"
    )

    pp = params["partitioning_parameters"]
    k = int(pp["common"]["k_target"])
    if k > n_nodes:
        k = max(1, n_nodes // 2)
        pp["common"]["k_target"] = k
        rationale.append(f"k_target above the number of graph nodes; reduced to {k}")

    capacity, what = backend_capacity(pp)
    if capacity is not None:
        target = max(min(capacity, n_nodes), k)
        rationale.append(f"{pp['partitioning_strategy']} is capped at {capacity} coarse nodes ({what}); target = {target}")
    else:
        target = _metis_like_target(n_nodes, k)
        rationale.append(f"METIS-style rule max(n/(20·log2 k), 30·k) gives a coarse target of {target} nodes")
    if target >= n_nodes:
        rationale.append("Graph is already at/below the target; coarsening will be skipped")

    G = build_pipeline_graph(A, dof, str(params["coarsening_parameters"].get("weight", "weight")))
    params["coarsening_parameters"]["max_levels"] = max(int(params["coarsening_parameters"]["max_levels"]), 30)
    params["coarsening_parameters"]["max_node_weight"] = None

    targets = sorted({target, max(k, int(target * 0.75))} | ({int(target * 1.25)} if capacity is None else set()))
    candidates: list[dict[str, Any]] = []
    for strategy in STRATEGY_GRID:
        for ratio in RATIO_GRID:
            for t in targets:
                cand = copy.deepcopy(params)
                cand["coarsening_parameters"]["strategy"] = strategy
                cand["coarsening_parameters"]["coarsen_ratio"] = ratio
                apply_coarse_virtuals(cand, min(t, n_nodes), WINDOW)
                check = check_feasibility(G, cand)
                dry = check["dry_run"]
                score = math.inf
                if check["feasible"]:
                    score = abs(dry["coarse_nodes"] - target) / max(target, 1) + 0.05 * math.log10(max(dry["vweight_spread"], 1.0))
                candidates.append({
                    "strategy": strategy, "coarsen_ratio": ratio, "coarse_target": t,
                    "feasible": check["feasible"], "score": score, "dry_run": dry,
                    "reasons": check["reasons"], "_params": cand,
                })

    feasible = [c for c in candidates if c["feasible"]]
    if feasible:
        best = min(feasible, key=lambda c: c["score"])
        params = best["_params"]
        rationale.append(
            f"Dry-run of {len(candidates)} coarsening settings: best = strategy '{best['strategy']}', "
            f"ratio {best['coarsen_ratio']}, range [{params['coarsening_parameters']['coarsen_inferior_limit']}, "
            f"{params['coarsening_parameters']['coarsen_superior_limit']}] -> {best['dry_run']['coarse_nodes']} coarse nodes "
            f"in {best['dry_run']['levels']} levels"
        )
    else:
        rationale.append("No coarsening setting in the grid was feasible; keeping the target range with the base strategy")
        apply_coarse_virtuals(params, min(target, n_nodes), WINDOW)

    up = params["uncoarsening_parameters"]
    if k > 1:
        up["refine_objective"] = "cut_balance"
        rationale.append("Refinement uses cut_balance so KL moves keep parts balanced")
    up["refine_max_passes_per_level"] = max(int(up.get("refine_max_passes_per_level") or 0), 10)

    params = validate_and_normalize_simulation_parameters(params)
    final_check = check_feasibility(G, params)
    return {
        "matrix_id": matrix_id,
        "parameters": params,
        "rationale": rationale,
        "feasible": final_check["feasible"],
        "reasons": final_check["reasons"],
        "dry_run": final_check["dry_run"],
        "features": features,
        "candidates": [{k2: v for k2, v in c.items() if k2 != "_params"} for c in candidates],
    }
