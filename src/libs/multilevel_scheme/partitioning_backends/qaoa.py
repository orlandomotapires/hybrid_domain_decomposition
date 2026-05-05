from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np
import pennylane as qml
from scipy.optimize import minimize

from .qlm_access import (
    DEFAULT_QLM_QPU_NAME,
    get_qlm_qpu,
    get_qlm_runtime,
    submit_qlm_job,
    validate_qlm_problem_size,
)
from libs.multilevel_scheme.partitioning_utils import (
    build_qubo_from_graph,
    qubo_dense_from_dict,
    qubo_energy,
    qubo_to_ising,
)


LOCAL_PYLINALG_QUBIT_SAFETY_LIMIT = 24


def _build_cost_observable(h: np.ndarray, J: np.ndarray):
    from qat.core import Observable, Term

    n = int(h.shape[0])
    terms = []
    for i in range(n):
        if not np.isclose(h[i], 0.0):
            terms.append(Term(float(h[i]), "Z", [i]))
    for i in range(n):
        for j in range(i + 1, n):
            if not np.isclose(J[i, j], 0.0):
                terms.append(Term(float(J[i, j]), "ZZ", [i, j]))
    return Observable(n, pauli_terms=terms, constant_coeff=0.0)


def _build_qaoa_circuit(
    h: np.ndarray,
    J: np.ndarray,
    params: np.ndarray,
    *,
    circuit_depth: int,
):
    """Build the standard alternating cost/mixer QAOA circuit for an Ising Hamiltonian."""
    runtime = get_qlm_runtime()
    Program = runtime["Program"]
    H = runtime["H"]
    CNOT = runtime["CNOT"]
    RX = runtime["RX"]
    RZ = runtime["RZ"]
    n = int(h.shape[0])
    p = int(circuit_depth)
    prog = Program()
    qbits = prog.qalloc(n)

    for i in range(n):
        prog.apply(H, qbits[i])

    gammas = params[:p]
    betas = params[p:]
    for layer in range(p):
        gamma = float(gammas[layer])
        beta = float(betas[layer])

        for i in range(n):
            if not np.isclose(h[i], 0.0):
                prog.apply(RZ(2.0 * gamma * float(h[i])), qbits[i])

        for i in range(n):
            for j in range(i + 1, n):
                if np.isclose(J[i, j], 0.0):
                    continue
                prog.apply(CNOT, qbits[i], qbits[j])
                prog.apply(RZ(2.0 * gamma * float(J[i, j])), qbits[j])
                prog.apply(CNOT, qbits[i], qbits[j])

        for i in range(n):
            prog.apply(RX(2.0 * beta), qbits[i])

    return prog.to_circ()


def _bits_from_qlm_state(state: Any, n: int) -> np.ndarray:
    text = str(state).strip()
    if text.startswith("|") and text.endswith(">"):
        text = text[1:-1]

    if len(text) == n and set(text).issubset({"0", "1"}):
        return np.asarray([int(ch) for ch in text], dtype=int)

    value = int(text)
    return np.asarray([int(ch) for ch in format(value, f"0{n}b")[-n:]], dtype=int)


def _qlm_result_energy(result: Any, Qm: np.ndarray, n: int) -> float:
    value = getattr(result, "value", None)
    if value is not None:
        return float(np.real(value))

    raw_data = list(getattr(result, "raw_data", None) or [])
    if not raw_data:
        raise RuntimeError("QLM result did not contain a scalar value or any samples")

    weighted_energy = 0.0
    total_weight = 0.0
    for sample in raw_data:
        bits = _bits_from_qlm_state(sample.state, n)
        weight = getattr(sample, "probability", None)
        if weight is None:
            weight = 1.0
        weight = float(weight)
        weighted_energy += weight * qubo_energy(Qm, bits)
        total_weight += weight

    if total_weight <= 0.0:
        raise RuntimeError("QLM samples had zero total probability")

    return float(weighted_energy / total_weight)


def _qaoa_bipartition_on_pennylane(
    dense_qubo: np.ndarray,
    *,
    nodes: list[Any],
    p: int,
    steps: int,
    lr: float,
    shots: int,
    seed: int | None,
) -> tuple[dict[Any, int], float]:
    n = len(nodes)
    if n > LOCAL_PYLINALG_QUBIT_SAFETY_LIMIT:
        raise ValueError(
            f"QAOA bipartition is too large to simulate locally with PennyLane (n={n}). "
            "Coarsen more, set simulated=False to use a QLM backend, or use a different method."
        )

    h, J = qubo_to_ising(dense_qubo)

    coeffs = []
    ops = []
    for i in range(n):
        if h[i] != 0.0:
            coeffs.append(float(h[i]))
            ops.append(qml.PauliZ(i))
    for i in range(n):
        for j in range(i + 1, n):
            if J[i, j] != 0.0:
                coeffs.append(float(J[i, j]))
                ops.append(qml.PauliZ(i) @ qml.PauliZ(j))

    Hc = qml.Hamiltonian(coeffs, ops) if coeffs else qml.Hamiltonian([0.0], [qml.Identity(0)])
    Hm = qml.Hamiltonian([1.0] * n, [qml.PauliX(i) for i in range(n)])

    dev = qml.device("default.qubit", wires=n)

    @qml.qnode(dev)
    def cost_qnode(params):
        gammas = params[:p]
        betas = params[p:]
        for i in range(n):
            qml.Hadamard(wires=i)
        for layer in range(p):
            qml.qaoa.cost_layer(gammas[layer], Hc)
            qml.qaoa.mixer_layer(betas[layer], Hm)
        return qml.expval(Hc)

    rng = np.random.default_rng(seed)
    params = rng.uniform(low=0.0, high=0.5, size=(2 * int(p),)).astype(float)
    opt = qml.AdamOptimizer(stepsize=float(lr))
    for _ in range(max(1, int(steps))):
        params = opt.step(cost_qnode, params)

    dev_s = qml.device("default.qubit", wires=n, shots=int(shots), seed=seed)

    @qml.qnode(dev_s)
    def sample_qnode(params):
        gammas = params[:p]
        betas = params[p:]
        for i in range(n):
            qml.Hadamard(wires=i)
        for layer in range(p):
            qml.qaoa.cost_layer(gammas[layer], Hc)
            qml.qaoa.mixer_layer(betas[layer], Hm)
        return [qml.sample(qml.PauliZ(i)) for i in range(n)]

    z_samples = np.stack(sample_qnode(params), axis=1)
    x_samples = ((1.0 - z_samples) / 2.0).astype(int)

    best_x = x_samples[0]
    best_energy = qubo_energy(dense_qubo, best_x)
    for xs in x_samples[1:]:
        energy = qubo_energy(dense_qubo, xs)
        if energy < best_energy:
            best_energy = energy
            best_x = xs

    partition = {nodes[i]: int(best_x[i]) for i in range(n)}
    if all(v == 0 for v in partition.values()):
        partition[nodes[0]] = 1
    return partition, float(best_energy)


def _qaoa_bipartition_on_qlm(
    Qm: np.ndarray,
    *,
    nodes: list[Any],
    circuit_depth: int = 1,
    num_steps: int = 60,
    num_shots: int = 200,
    seed: int | None = None,
    qlm_qpu_name: str | None = DEFAULT_QLM_QPU_NAME,
) -> tuple[dict[Any, int], float]:
    """Optimize a QAOA ansatz on QLM and return the best measured balanced cut bitstring."""
    variables = list(nodes)
    n = len(variables)
    if n == 0:
        return {}, 0.0
    if n == 1:
        return {variables[0]: 0}, 0.0

    validate_qlm_problem_size(
        n=n,
        qlm_qpu_name=qlm_qpu_name,
    )

    Qm = np.asarray(Qm, dtype=float)
    h, J = qubo_to_ising(Qm)
    observable = _build_cost_observable(h, J)
    qpu = get_qlm_qpu(qlm_qpu_name=qlm_qpu_name)

    p = max(1, int(circuit_depth))
    rng = np.random.default_rng(seed)
    initial_params = rng.uniform(low=0.0, high=0.5, size=(2 * p,)).astype(float)

    def objective(params: np.ndarray) -> float:
        circuit = _build_qaoa_circuit(h, J, np.asarray(params, dtype=float), circuit_depth=p)
        job = circuit.to_job(observable=observable, nbshots=0)
        result = submit_qlm_job(qpu, job)
        return _qlm_result_energy(result, Qm, n)

    opt_result = minimize(
        objective,
        initial_params,
        method="COBYLA",
        options={"maxiter": max(1, int(num_steps)), "rhobeg": 0.2},
    )
    best_params = np.asarray(opt_result.x, dtype=float)

    circuit = _build_qaoa_circuit(h, J, best_params, circuit_depth=p)
    result = submit_qlm_job(qpu, circuit.to_job(nbshots=max(1, int(num_shots))))

    best_bits = None
    best_energy = None
    for sample in getattr(result, "raw_data", None) or []:
        bits = _bits_from_qlm_state(sample.state, n)
        energy = qubo_energy(Qm, bits)
        if best_energy is None or energy < best_energy:
            best_energy = energy
            best_bits = bits

    if best_bits is None:
        raise RuntimeError("QLM QAOA sampling returned no bitstring samples")

    x_dict = {variables[i]: int(best_bits[i]) for i in range(n)}
    if all(bit == 0 for bit in x_dict.values()):
        x_dict[variables[0]] = 1

    return x_dict, float(best_energy)


def qaoa_bipartition(
    G: nx.Graph,
    *,
    p: int = 1,
    steps: int = 60,
    lr: float = 0.2,
    shots: int = 200,
    balance_lambda: float = 1.0,
    target_weight: float | None = None,
    seed: int | None = None,
    simulated: bool = True,
    qlm_qpu_name: str | None = None,
) -> tuple[dict[Any, int], float]:
    """Run a small QAOA instance on the 2-way balanced-cut QUBO."""
    nodes = list(G.nodes())
    n = len(nodes)
    if n == 0:
        return {}, 0.0
    if n == 1:
        return {nodes[0]: 0}, 0.0

    qubo = build_qubo_from_graph(G, balance_lambda=balance_lambda, target_weight=target_weight)
    dense_qubo = qubo_dense_from_dict(qubo, nodes)

    if not simulated:
        return _qaoa_bipartition_on_qlm(
            dense_qubo,
            nodes=nodes,
            circuit_depth=p,
            num_steps=steps,
            num_shots=shots,
            seed=seed,
            qlm_qpu_name=qlm_qpu_name,
        )

    return _qaoa_bipartition_on_pennylane(
        dense_qubo,
        nodes=nodes,
        p=p,
        steps=steps,
        lr=lr,
        shots=shots,
        seed=seed,
    )