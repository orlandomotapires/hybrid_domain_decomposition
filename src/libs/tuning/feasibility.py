"""Cheap pre-checks that reject parameter sets before a full pipeline run.

Checks the partitioning backend's qubit/clique capacity and dry-runs the real
``coarsen_chain``, so unreachable coarsening ranges are caught in milliseconds.
"""

from __future__ import annotations

import re
from typing import Any

import networkx as nx

from libs.multilevel_scheme.coarsening.coarsening import coarsen_chain

DWAVE_CLIQUE_LIMIT = 175
QAOA_EMULATED_QUBIT_LIMIT = 18
QLM_DEFAULT_QUBITS = 10


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
    if strategy == "quantum_annealing" and not simulated:
        return DWAVE_CLIQUE_LIMIT, "D-Wave clique embedding"
    if strategy == "quantum_approximation_optimizer":
        if simulated:
            return QAOA_EMULATED_QUBIT_LIMIT, "QAOA statevector emulation"
        limit = qlm_qubit_limit(sp.get("qlm_qpu_name"))
        return limit, f"QLM QPU ({limit} qubits)"
    return None, None


def resolve_max_node_weight(G: nx.Graph, coarsening_parameters: dict[str, Any], k_target: int) -> float | None:
    mnw = coarsening_parameters.get("max_node_weight")
    if mnw is not None:
        return float(mnw)
    if int(k_target) > 1:
        total = sum(float(G.nodes[u].get("vweight", 1.0)) for u in G.nodes())
        return 1.5 * total / float(k_target)
    return None


def coarsening_dry_run(G: nx.Graph, parameters: dict[str, Any]) -> dict[str, Any]:
    """Run only the coarsening stage. Returns reachability, coarse size and levels."""
    cp = parameters["coarsening_parameters"]
    k = int(parameters["partitioning_parameters"]["common"]["k_target"])
    superior = cp.get("coarsen_superior_limit")
    try:
        graphs, _ = coarsen_chain(
            G,
            trial_seed=int(parameters["general_parameters"]["seed"]),
            coarsen_inferior_limit=int(cp["coarsen_inferior_limit"]),
            coarsen_superior_limit=None if superior is None else int(superior),
            max_levels=int(cp["max_levels"]),
            weight=str(cp.get("weight", "weight")),
            strategy=str(cp["strategy"]),
            coarsen_ratio=float(cp["coarsen_ratio"]),
            max_node_weight=resolve_max_node_weight(G, cp, k),
        )
    except ValueError as exc:
        return {"reachable": False, "reason": str(exc)}
    Gc = graphs[-1]
    vw = [float(Gc.nodes[u].get("vweight", 1.0)) for u in Gc.nodes()] or [1.0]
    return {
        "reachable": True,
        "coarse_nodes": int(Gc.number_of_nodes()),
        "coarse_edges": int(Gc.number_of_edges()),
        "levels": len(graphs),
        "vweight_spread": float(max(vw) / max(min(vw), 1e-12)),
        "reason": None,
    }


def check_feasibility(G: nx.Graph, parameters: dict[str, Any]) -> dict[str, Any]:
    """``{"feasible": bool, "reasons": [...], "dry_run": {...}}`` for a full parameter set."""
    reasons: list[str] = []
    n_nodes_total = G.number_of_nodes()
    pp = parameters["partitioning_parameters"]
    k = int(pp["common"]["k_target"])
    if k < 1:
        reasons.append("k_target must be >= 1")
    dry = coarsening_dry_run(G, parameters)
    if not dry["reachable"]:
        reasons.append(dry["reason"])
    else:
        capacity, what = backend_capacity(pp)
        if capacity is not None and dry["coarse_nodes"] > capacity:
            reasons.append(
                f"Coarse graph has {dry['coarse_nodes']} nodes, above the {what} capacity of {capacity}"
            )
        if dry["coarse_nodes"] < k:
            reasons.append(f"Coarse graph has {dry['coarse_nodes']} nodes, fewer than k_target={k}")
    if k > n_nodes_total:
        reasons.append(f"k_target={k} exceeds the {n_nodes_total} graph nodes")
    return {"feasible": not reasons, "reasons": reasons, "dry_run": dry}
