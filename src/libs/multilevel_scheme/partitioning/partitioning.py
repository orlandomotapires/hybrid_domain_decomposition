from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx
import pymetis

from libs.multilevel_scheme.partitioning.qa import anneal_bipartition, qaoa_bipartition
from libs.multilevel_scheme.partitioning.utils import (
    recursive_kway_via_bipartition,
)


def _weights_to_metis_ints(values: List[float]) -> List[int]:
    positive_values = [float(value) for value in values if float(value) > 0.0]
    if not positive_values:
        return [1 for _ in values]

    min_positive = min(positive_values)
    scale = 1.0 / min_positive if min_positive < 1.0 else 1.0
    max_weight = 1_000_000
    weights: List[int] = []
    for value in values:
        scaled = int(round(float(value) * scale))
        weights.append(max(1, min(max_weight, scaled)))
    return weights


def _graph_to_metis_csr(G: nx.Graph) -> tuple[List[int], List[int], List[int], List[int]]:
    nodes = list(G.nodes())
    index = {u: i for i, u in enumerate(nodes)}

    xadj: List[int] = [0]
    adjncy: List[int] = []
    edge_weights_raw: List[float] = []
    node_weights_raw: List[float] = []

    for node in nodes:
        node_weights_raw.append(float(G.nodes[node].get("vweight", 1.0)))
        neighbors = sorted(G.neighbors(node), key=lambda other: index[other])
        for neighbor in neighbors:
            adjncy.append(index[neighbor])
            edge_weights_raw.append(float(G[node][neighbor].get("weight", 1.0)))
        xadj.append(len(adjncy))

    vweights = _weights_to_metis_ints(node_weights_raw)
    eweights = _weights_to_metis_ints(edge_weights_raw)
    return xadj, adjncy, vweights, eweights

def partition_graph_metis(
    G: nx.Graph,
    nparts: int = 2,
) -> Dict[Any, int]:
    """Partition a graph directly with METIS and return node-to-part assignments."""

    nodes = list(G.nodes())
    effective_parts = max(1, min(int(nparts), len(nodes)))
    if not nodes:
        return {}

    xadj, adjncy, vweights, eweights = _graph_to_metis_csr(G)
    _, membership = pymetis.part_graph(
        effective_parts,
        xadj=xadj,
        adjncy=adjncy,
        vweights=vweights,
        eweights=eweights,
    )
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
    qlm_job_timeout_seconds: float | None = None,
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
            qlm_job_timeout_seconds=qlm_job_timeout_seconds,
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