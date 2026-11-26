# Quantum backends

The coarse graph can be partitioned by three methods. Quantum methods split it by recursive bipartition: each split is a balanced-cut QUBO (annealing) or Ising problem (QAOA), solved locally on an emulator or remotely on hardware.

| Method | Emulated | Hardware |
| --- | --- | --- |
| METIS | — (classical, via `pymetis`) | — |
| Quantum annealing | Simulated annealing (`dwave-neal`) | D-Wave QPU through Leap |
| QAOA | PennyLane | QLM QPU through QLMaaS (myQLM) |

Choose the method and backend on a simulation's **Partitioning** page, or in its preset (`partitioning_parameters.partitioning_strategy` and the method's `simulated` flag). The coarse graph must fit the hardware: one qubit per coarse node for QAOA, a clique embedding for D-Wave. The app warns when the coarsening range is too large for the chosen backend, and a run on a local backend stops right after coarsening, with the reason, when the coarse graph is too large: 18 nodes for emulated QAOA and 3000 for simulated annealing (see `HDD_SIMULATED_QA_NODE_LIMIT` in [Command line](command-line.md#environment-variables)).

## Check access

In the desktop app, **Quantum hardware** shows, per backend, whether its SDK is installed and its credentials are configured. **Probe D-Wave Leap** reports whether a solver is reachable and the largest dense problem it embeds; **Probe QLM** inspects a QLM QPU. Probes contact the remote service with your saved credentials.

The code is in `src/libs/multilevel_scheme/partitioning/` (`qa/` for annealing and D-Wave, `qaoa/` for QAOA and QLM).

## D-Wave Leap

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
- if the configured solver is not visible, `src/libs/multilevel_scheme/partitioning/qa/dwave_access.py` will fail before job submission during the capacity pre-check

Official references:

- D-Wave Ocean installation: https://docs.dwavequantum.com/en/latest/ocean/install.html
- D-Wave Leap access configuration: https://docs.dwavequantum.com/en/latest/ocean/sapi_access_basic.html
- Leap dashboard: https://cloud.dwavesys.com/leap/

## QLM

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

For interactive backend inspection, use `./run.sh --qlm_inspect` (see [Command line](command-line.md#qlm-inspector)).

Official references:

- myQLM installation: https://myqlm.github.io/01_getting_started/%3Amyqlm%3A01_install.html
- myQLM execution model: https://myqlm.github.io/02_user_guide/02_execute.html
- myQLM API reference: https://myqlm.github.io/04_api_reference/module_qat.html
