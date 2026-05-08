# Partitioning Backends

This directory contains the backend-specific partitioning implementations used on the coarse graph.

## Supported Partitioning Strategies

### METIS

- Implemented through `pymetis` in [partitioning.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/partitioning.py).
- Used as the classical baseline on the coarse graph.
- The repository passes weighted coarse graphs into METIS so the baseline is comparable to the weighted quantum formulations.

### Quantum Annealing

- Builds a balanced-cut QUBO and solves recursive bipartitions.
- Supports:
  - local simulated annealing through [annealing.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/qa/annealing.py)
  - remote D-Wave QPU access through [dwave_access.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/qa/dwave_access.py)

### QAOA

- Builds recursive bipartitions from a balanced-cut QUBO.
- Supports:
  - local PennyLane simulation
  - QLM/myQLM execution through [qaoa.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/qaoa/qaoa.py)
- QLM backend connection and probing helpers live in [qlm_access.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/qaoa/qlm_access.py).

## Configuring D-Wave Access

Use this section only when `partitioning_strategy` is `quantum_annealing` and the strategy block has `simulated: false`.

1. Make sure the active environment contains the D-Wave client tooling.
   - This repository already depends on `dwave-system`.
   - If the `dwave` CLI is missing, install `dwave-ocean-sdk` in the same environment.

```sh
dwave --help
pip install dwave-ocean-sdk
```

2. Create or update your Leap configuration.

```sh
dwave setup --auth
dwave config create --auto-token
```

3. Verify which QPUs are visible to the current token and region.

```sh
dwave ping --client qpu
dwave solvers --list --region eu-central-1
dwave solvers --list --region na-west-1
```

4. Set the simulation JSON.

- `partitioning_parameters.partitioning_strategy = "quantum_annealing"`
- `partitioning_parameters.strategies.quantum_annealing.simulated = false`
- optionally set `qpu_region`, `qpu_solver_name`, and `qpu_problem_label`

Minimal example:

```json
"quantum_annealing": {
  "qubo_balance_lambda": 2,
  "num_starts": 15,
  "num_reads": 50,
  "balance_violation_lambda": 1000000.0,
  "simulated": false,
  "qpu_region": "eu-central-1",
  "qpu_solver_name": "Advantage2_system2.1",
  "qpu_problem_label": "my_domain_decomposition_run"
}
```

Important note:

- solver visibility is account- and region-dependent
- if the configured solver is not visible, [dwave_access.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/qa/dwave_access.py) will fail before job submission during the capacity pre-check

Official references:

- D-Wave Ocean installation: https://docs.dwavequantum.com/en/latest/ocean/install.html
- D-Wave Leap access configuration: https://docs.dwavequantum.com/en/latest/ocean/sapi_access_basic.html
- Leap dashboard: https://cloud.dwavesys.com/leap/

## Configuring QLM Access

Use this section only when `partitioning_strategy` is `quantum_approximation_optimizer` and the strategy block has `simulated: false`.

### Local QAOA testing

Set:

- `simulated: true`
- an `adam_learning_rate` value

Minimal example:

```json
"quantum_approximation_optimizer": {
  "qubo_balance_lambda": 2,
  "num_starts": 1,
  "num_steps": 20,
  "num_shots": 32,
  "balance_violation_lambda": 5.0,
  "circuit_depth": 1,
  "adam_learning_rate": 0.1,
  "simulated": true
}
```

### QLM access

When `simulated` is false, this project uses `qat.qlmaas.QLMaaSConnection` and submits QAOA jobs to the QPU named by `qlm_qpu_name`.

Recommended steps:

1. Install myQLM in the same Python environment as this project.

```sh
pip install myqlm
```

2. Obtain the connection details from your QLM administrator.
   - hostname
   - port
   - authentication mode
   - certificate and key for SSL mode, or the site-specific password-based credentials

3. Create the local QLMaaS configuration once.

Example using SSL authentication:

```python
from qat.qlmaas import QLMaaSConnection

conn = QLMaaSConnection(
    hostname="your-qlm-host",
    port=443,
    authentication="ssl",
    certificate="/path/to/client.crt",
    key="/path/to/client.key",
    check_host=True,
)
conn.create_config()
```

4. Verify that the connection works and list the available QPUs.

```python
from qat.qlmaas import QLMaaSConnection

conn = QLMaaSConnection()
print(conn.get_qpus())
```

5. Set the simulation JSON.

- `partitioning_strategy: "quantum_approximation_optimizer"`
- `simulated: false`
- `qlm_qpu_name: "qat.qpus:QSolidQPU10"` or another real QPU exposed by your server
- set `coarsen_inferior_limit` and `coarsen_superior_limit` so the selected hardware can embed the resulting coarse graph

6. Run the simulation and check `run_log` for `Running QAOA on QLM backend ...`.

For interactive backend inspection, use [qlm_inspect.py](/home/operation/Thesis/hybrid_domain_decomposition/src/libs/multilevel_scheme/partitioning/qaoa/qlm_inspect.py).

Official references:

- myQLM installation: https://myqlm.github.io/01_getting_started/%3Amyqlm%3A01_install.html
- myQLM execution model: https://myqlm.github.io/02_user_guide/02_execute.html
- myQLM API reference: https://myqlm.github.io/04_api_reference/module_qat.html