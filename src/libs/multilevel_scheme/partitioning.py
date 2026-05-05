from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx
import pymetis

from libs.multilevel_scheme.partitioning_backends import anneal_bipartition, qaoa_bipartition
from libs.multilevel_scheme.partitioning_utils import (
    recursive_kway_via_bipartition,
)

def partition_graph_metis(
    G: nx.Graph,
    nparts: int = 2,
) -> Dict[Any, int]:
    """Partition a graph directly with METIS and return node-to-part assignments."""

    nodes = list(G.nodes())
    index = {u: i for i, u in enumerate(nodes)}
    adjacency: List[List[int]] = [[index[v] for v in G.neighbors(u)] for u in nodes]
    _, membership = pymetis.part_graph(nparts, adjacency=adjacency)
    return {nodes[i]: int(membership[i]) for i in range(len(nodes))}

def recursive_kway_anneal(
    Gc: nx.Graph,
    k: int,
    *,
    balance_lambda: float = 1.0,
    num_reads: int = 200,
    weight: str = 'vweight',
    balance_tolerance: float = 0.0,
    seed: int | None = None,
    num_starts: int = 1,
    balance_violation_lambda: float = 1.0e6,
    simulated: bool = True,
    qpu_solver_name: str | None = None,
    qpu_region: str | None = None,
    qpu_problem_label: str | None = None,
):
    """Recursive k-way partitioning using QUBO bipartitions from simulated or hardware annealing."""
    def _bipartition(G: nx.Graph, target_weight: float, split_seed: int | None, simulated: bool) -> dict[Any, int]:
        x, _ = anneal_bipartition(
            G,
            num_reads=num_reads,
            balance_lambda=balance_lambda,
            target_weight=target_weight,
            seed=split_seed,
            simulated=simulated,
            qpu_solver_name=qpu_solver_name,
            qpu_region=qpu_region,
            qpu_problem_label=qpu_problem_label,
        )
        return {n: int(b) for n, b in x.items()}

    return recursive_kway_via_bipartition(
        Gc,
        int(k),
        weight=weight,
        balance_tolerance=balance_tolerance,
        seed=seed,
        num_starts=num_starts,
        balance_violation_lambda=balance_violation_lambda,
        bipartition=_bipartition,
        simulated=simulated,
    )


def recursive_kway_qaoa(
    Gc: nx.Graph,
    k: int,
    *,
    balance_lambda: float = 1.0,
    weight: str = 'vweight',
    balance_tolerance: float = 0.0,
    seed: int | None = None,
    num_starts: int = 1,
    balance_violation_lambda: float = 1.0e6,
    circuit_depth: int = 1,
    num_steps: int = 60,
    adam_learning_rate: float | None = None,
    num_shots: int = 200,
    simulated: bool = True,
    qlm_qpu_name: str | None = None,
):
    """Recursive k-way partitioning using PennyLane when simulated=True, else QLM."""
    def _bipartition(G: nx.Graph, target_weight: float, split_seed: int | None, simulated: bool) -> dict[Any, int]:
        if simulated and adam_learning_rate is None:
            raise ValueError("Local PennyLane QAOA requires adam_learning_rate to be configured")
        x, _ = qaoa_bipartition(
            G,
            p=circuit_depth,
            steps=num_steps,
            lr=adam_learning_rate,
            shots=num_shots,
            balance_lambda=balance_lambda,
            target_weight=target_weight,
            seed=split_seed,
            simulated=simulated,
            qlm_qpu_name=qlm_qpu_name,
        )
        return {n: int(b) for n, b in x.items()}

    return recursive_kway_via_bipartition(
        Gc,
        int(k),
        weight=weight,
        balance_tolerance=balance_tolerance,
        seed=seed,
        num_starts=num_starts,
        balance_violation_lambda=balance_violation_lambda,
        bipartition=_bipartition,
        simulated=simulated,
    )