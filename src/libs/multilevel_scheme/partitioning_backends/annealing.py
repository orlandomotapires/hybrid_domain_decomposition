from __future__ import annotations

from typing import Any, Mapping

import neal
import networkx as nx

from .dwave_access import sample_qubo_on_dwave_qpu
from libs.multilevel_scheme.partitioning_utils import build_qubo_from_graph


def _run_simulated_annealing(
    qubo: Mapping[tuple[Any, Any], float],
    *,
    num_reads: int,
    seed: int | None,
) -> tuple[dict[Any, int], float]:
    sampler = neal.SimulatedAnnealingSampler()
    best = sampler.sample_qubo(dict(qubo), num_reads=int(num_reads), seed=seed).first
    return dict(best.sample), float(best.energy)


def anneal_bipartition(
    G: nx.Graph,
    *,
    num_reads: int = 200,
    balance_lambda: float = 1.0,
    target_weight: float | None = None,
    seed: int | None = None,
    return_qubo: bool = False,
    simulated: bool = True,
    qpu_solver_name: str | None = None,
    qpu_region: str | None = None,
    qpu_problem_label: str | None = None,
):
    """Solve one coarse 2-way split either locally or through the D-Wave QPU entry point."""
    qubo = build_qubo_from_graph(G, balance_lambda=balance_lambda, target_weight=target_weight)

    if simulated:
        sample, energy = _run_simulated_annealing(
            qubo,
            num_reads=num_reads,
            seed=seed,
        )
    else:
        sample, energy = sample_qubo_on_dwave_qpu(
            qubo,
            logical_variables=list(G.nodes()),
            balance_lambda=balance_lambda,
            num_reads=num_reads,
            qpu_solver_name=qpu_solver_name,
            qpu_region=qpu_region,
            qpu_problem_label=qpu_problem_label,
        )

    if sample and all(bit == 0 for bit in sample.values()):
        sample[next(iter(sample))] = 1

    if return_qubo:
        return sample, energy, qubo
    return sample, energy