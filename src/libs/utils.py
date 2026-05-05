from __future__ import annotations

from scipy.io import mmread
from scipy.io import mmwrite
import scipy.sparse as sp
import numpy as np
import networkx as nx

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from scipy import sparse


def validate_and_normalize_simulation_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("simulation_config must be a JSON object")

    out = dict(config)
    allowed_keys = {
        "parameters_file_path",
        "input_matrices",
        "save_output",
    }
    unsupported_keys = sorted(set(out.keys()) - allowed_keys)
    if unsupported_keys:
        raise ValueError(
            "Unsupported simulation_config keys: " + ", ".join(unsupported_keys)
        )

    parameters_file_path = out.get("parameters_file_path")
    if not isinstance(parameters_file_path, str) or not parameters_file_path.strip():
        raise ValueError("simulation_config.parameters_file_path must be a non-empty string")

    input_matrices = out.get("input_matrices")
    if not isinstance(input_matrices, dict):
        raise ValueError("simulation_config.input_matrices must be a JSON object")

    save_output = out.get("save_output", [])
    if save_output is None:
        save_output = []
    if not isinstance(save_output, list) or not all(isinstance(item, str) for item in save_output):
        raise ValueError("simulation_config.save_output must be a list of strings")

    out.update(
        {
            "parameters_file_path": parameters_file_path.strip(),
            "input_matrices": dict(input_matrices),
            "save_output": list(save_output),
        }
    )
    return out

def _as_csr_matrix(matrix: Any) -> sp.csr_matrix:
    if sp.issparse(matrix):
        return matrix.tocsr()
    return sp.csr_matrix(matrix)


def load_mtx(path, label=None):
    matrix_path = Path(path)
    matrix_name = label or matrix_path.name

    if not matrix_path.exists():
        raise FileNotFoundError(f"Matrix file for {matrix_name} not found: {matrix_path}")
    if matrix_path.suffix.lower() != ".mtx":
        raise ValueError(
            f"Unsupported matrix file for {matrix_name}: {matrix_path}. "
            "Only Matrix Market .mtx files are supported."
        )

    return _as_csr_matrix(mmread(matrix_path))


def resolve_matrix_input_path(
    matrices_dir: Path,
    input_matrices: dict[str, Any],
    *,
    key: str,
    label: str,
) -> Path:
    raw_value = input_matrices.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(
            f"simulation_config.input_matrices.{key} must be set to a Matrix Market .mtx file"
        )

    matrix_path = matrices_dir / raw_value
    if matrix_path.suffix.lower() != ".mtx":
        raise ValueError(
            f"simulation_config.input_matrices.{key} for matrix {label} must reference a Matrix Market .mtx file; "
            f"got {raw_value!r}"
        )
    if not matrix_path.exists():
        raise FileNotFoundError(f"Configured matrix file for {label} not found: {matrix_path}")

    return matrix_path

def write_json(path: Path, obj: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", encoding="utf-8") as f:
		json.dump(obj, f, indent=2, sort_keys=True)

def write_results_table_text(path: Path, data: dict[str, Any]) -> None:
    def _format_value(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.6g}"
        if isinstance(v, (int, np.integer)):
            return str(int(v))
        if isinstance(v, (np.floating,)):
            return f"{float(v):.6g}"
        if v is None:
            return ""
        return str(v).replace("\n", " ")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for matrix_name, matrix_metrics in data.items():
            f.write(f"Matrix {matrix_name} metrics (original x permuted)\n\n")

            structural = {}
            if isinstance(matrix_metrics, dict):
                structural = matrix_metrics.get("structural_metrics", {})

            original = structural.get("original", {}) if isinstance(structural, dict) else {}
            permuted = structural.get("permuted", {}) if isinstance(structural, dict) else {}

            keys = list(dict.fromkeys(list(original.keys()) + list(permuted.keys())))
            rows: list[tuple[str, str, str]] = []
            for k in keys:
                rows.append(
                    (
                        str(k),
                        _format_value(original.get(k, "")),
                        _format_value(permuted.get(k, "")),
                    )
                )

            w_metric = max([len("Metric")] + [len(r[0]) for r in rows])
            w_orig = max([len("Original")] + [len(r[1]) for r in rows])
            w_perm = max([len("Permuted")] + [len(r[2]) for r in rows])

            f.write(f"{'Metric'.ljust(w_metric)}  {'Original'.rjust(w_orig)}  {'Permuted'.rjust(w_perm)}\n")
            for metric, orig_v, perm_v in rows:
                f.write(
                    f"{metric.ljust(w_metric)}  {orig_v.rjust(w_orig)}  {perm_v.rjust(w_perm)}\n"
                )

            perm_check = matrix_metrics.get("permutation_check", {}) if isinstance(matrix_metrics, dict) else {}
            if isinstance(perm_check, dict) and len(perm_check) > 0:
                f.write("\nPermutation check\n")
                pc_rows = [(str(k), _format_value(v)) for k, v in perm_check.items()]
                w_k = max([len("Metric")] + [len(r[0]) for r in pc_rows])
                w_v = max([len("Value")] + [len(r[1]) for r in pc_rows])
                f.write(f"{'Metric'.ljust(w_k)}  {'Value'.rjust(w_v)}\n")
                for k, v in pc_rows:
                    f.write(f"{k.ljust(w_k)}  {v.rjust(w_v)}\n")

            f.write("\n\n")
    
def save_mtx(path: Path, matrix, *, comment: str = "") -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	mmwrite(path, matrix, comment=comment)

def save_permutation_txt(path: Path, permutation: np.ndarray) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	np.savetxt(path, np.asarray(permutation, dtype=np.int64), fmt="%d")

def matrix_to_graph(A, dof_per_node: int = 1):
    """Convert a (sparse/dense) matrix into an undirected NetworkX graph.

    Minimal behavior:
    - If dof_per_node > 1, aggregate DOF blocks to node-level adjacency
    - Uses absolute values for edge weights
    - Symmetrizes by sum (A + A^T)
    - Drops diagonal/self-loops
    - Edge weights stored under attribute 'weight'
    """
    if not sp.issparse(A):
        A = sp.csr_matrix(A)
    A = A.tocsr()

    d = int(dof_per_node)
    if d > 1:
        C = A.tocoo()
        values = np.abs(C.data)
        node_row = (C.row // d).astype(int)
        node_col = (C.col // d).astype(int)
        n = A.shape[0] // d
        A = sp.coo_matrix((values, (node_row, node_col)), shape=(n, n)).tocsr()
    else:
        C = A.tocoo()
        C.data = np.abs(C.data)
        A = C.tocsr()

    A = A + A.T
    A.setdiag(0)
    A.eliminate_zeros()

    return nx.from_scipy_sparse_array(A, create_using=nx.Graph, edge_attribute='weight')

def save_matrices_sparsity_comparison(
    A,
    B,
    name_a: str = "K",
    name_b: str = "M",
    figsize=(12, 5),
    markersize: float = 0.5,
    *,
    save_path: str | None = None,
    dpi: int = 200,
):
    fig, axes = plt.subplots(1, 2, figsize=figsize, constrained_layout=True)

    for ax, mat, title in zip(axes, [A, B], [name_a, name_b]):
        if sparse.issparse(mat):
            ax.spy(mat, markersize=markersize, color="black")
        else:
            ax.spy(mat != 0, markersize=markersize, color="black")
        ax.set_title(f"Sparsity pattern: {title}")
        ax.set_xlabel("Column index")
        ax.set_ylabel("Row index")

    fig.savefig(save_path, dpi=dpi)


def validate_and_normalize_simulation_parameters(params: dict) -> dict:
    """Validate and normalize simulation parameters.

    - Enforces presence of required keys and basic value ranges.
    - Coerces a small set of common JSON-ish types (e.g. "True" -> True).
    - Ignores unknown keys (keeps them as-is).

    Returns a normalized parameters dict with the same overall structure.
    """

    def _require_dict(obj: Any, name: str) -> dict:
        if not isinstance(obj, dict):
            raise ValueError(f"{name} must be a JSON object")
        return obj

    def _coerce_int(v: Any, name: str) -> int:
        if isinstance(v, bool):
            raise ValueError(f"{name} must be an integer")
        if isinstance(v, (int, np.integer)):
            return int(v)
        if isinstance(v, (float, np.floating)) and float(v).is_integer():
            return int(v)
        if isinstance(v, str) and v.strip() != "":
            try:
                return int(v)
            except (TypeError, ValueError, OverflowError) as e:
                raise ValueError(f"{name} must be an integer") from e
        raise ValueError(f"{name} must be an integer")

    def _coerce_float(v: Any, name: str) -> float:
        if isinstance(v, bool):
            raise ValueError(f"{name} must be a number")
        if isinstance(v, (int, np.integer, float, np.floating)):
            vf = float(v)
            if not np.isfinite(vf):
                raise ValueError(f"{name} must be a finite number")
            return vf
        if isinstance(v, str) and v.strip() != "":
            try:
                vf = float(v)
            except (TypeError, ValueError, OverflowError) as e:
                raise ValueError(f"{name} must be a number") from e
            if not np.isfinite(vf):
                raise ValueError(f"{name} must be a finite number")
            return vf
        raise ValueError(f"{name} must be a number")

    def _coerce_bool(v: Any, name: str) -> bool:
        if isinstance(v, bool):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "1", "yes", "y"):
                return True
            if s in ("false", "0", "no", "n"):
                return False
        raise ValueError(f"{name} must be a boolean")

    def _coerce_optional_str(v: Any, name: str) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                raise ValueError(f"{name} must be a non-empty string if provided")
            return s
        raise ValueError(f"{name} must be a string if provided")

    params = _require_dict(params, "simulation_parameters")

    out = dict(params)
    gp = _require_dict(out.get("general_parameters"), "general_parameters")
    cp = _require_dict(out.get("coarsening_parameters"), "coarsening_parameters")
    pp = _require_dict(out.get("partitioning_parameters"), "partitioning_parameters")
    up = _require_dict(out.get("uncoarsening_parameters"), "uncoarsening_parameters")

    # general_parameters
    dof_per_node = _coerce_int(gp.get("dof_per_node"), "general_parameters.dof_per_node")
    if dof_per_node <= 0:
        raise ValueError("general_parameters.dof_per_node must be > 0")
    seed = _coerce_int(gp.get("seed"), "general_parameters.seed")
    gp_out = dict(gp)
    gp_out.update({"dof_per_node": dof_per_node, "seed": seed})

    # coarsening_parameters
    coarsen_limit = _coerce_int(cp.get("coarsen_limit"), "coarsening_parameters.coarsen_limit")
    if coarsen_limit < 1:
        raise ValueError("coarsening_parameters.coarsen_limit must be >= 1")
    max_levels = _coerce_int(cp.get("max_levels"), "coarsening_parameters.max_levels")
    if max_levels < 1:
        raise ValueError("coarsening_parameters.max_levels must be >= 1")
    weight = cp.get("weight")
    if not isinstance(weight, str) or not weight.strip():
        raise ValueError("coarsening_parameters.weight must be a non-empty string")
    strategy = cp.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        raise ValueError("coarsening_parameters.strategy must be a non-empty string")
    strategy = strategy.strip().lower()
    if strategy not in ("random", "sorted", "modified", "light"):
        raise ValueError(
            "coarsening_parameters.strategy must be one of: random, sorted, modified, light"
        )
    coarsen_ratio = _coerce_float(cp.get("coarsen_ratio"), "coarsening_parameters.coarsen_ratio")
    if not (0.0 < coarsen_ratio <= 1.0):
        raise ValueError("coarsening_parameters.coarsen_ratio must be in (0, 1]")
    max_node_weight = cp.get("max_node_weight")
    if max_node_weight is not None:
        max_node_weight = _coerce_float(max_node_weight, "coarsening_parameters.max_node_weight")
        if max_node_weight <= 0.0:
            raise ValueError("coarsening_parameters.max_node_weight must be > 0 if provided")

    cp_out = dict(cp)
    cp_out.update(
        {
            "coarsen_limit": coarsen_limit,
            "max_levels": max_levels,
            "weight": weight.strip(),
            "strategy": strategy,
            "coarsen_ratio": coarsen_ratio,
            "max_node_weight": max_node_weight,
        }
    )

    # partitioning_parameters
    partitioning_strategy = pp.get("partitioning_strategy")
    if not isinstance(partitioning_strategy, str) or not partitioning_strategy.strip():
        raise ValueError("partitioning_parameters.partitioning_strategy must be a non-empty string")
    partitioning_strategy = partitioning_strategy.strip()
    if partitioning_strategy not in (
        "metis_partitioning",
        "quantum_annealing",
        "quantum_approximation_optimizer",
    ):
        raise ValueError(
            "partitioning_parameters.partitioning_strategy must be one of: "
            "metis_partitioning, quantum_annealing, quantum_approximation_optimizer"
        )

    common_raw = pp.get("common")
    if common_raw is None:
        common_raw = {}
    common = _require_dict(common_raw, "partitioning_parameters.common")

    # Defaults (from your tables)
    k_target = _coerce_int(
        common.get("k_target", 2), "partitioning_parameters.common.k_target"
    )
    if k_target < 1:
        raise ValueError("partitioning_parameters.common.k_target must be >= 1")
    balance_tolerance = _coerce_float(
        common.get("balance_tolerance", 0.1), "partitioning_parameters.common.balance_tolerance"
    )
    if balance_tolerance < 0.0:
        raise ValueError("partitioning_parameters.common.balance_tolerance must be >= 0")

    strategies_raw = pp.get("strategies")
    if strategies_raw is None:
        strategies_raw = {}
    strategies = _require_dict(strategies_raw, "partitioning_parameters.strategies")

    strat_raw = strategies.get(partitioning_strategy)
    if strat_raw is None:
        strat_raw = {}
    strat_params = _require_dict(
        strat_raw,
        f"partitioning_parameters.strategies.{partitioning_strategy}",
    )

    def _value_or_default(key: str, default: Any) -> Any:
        if key in strat_params and strat_params.get(key) is None:
            raise ValueError(
                f"partitioning_parameters.strategies.{partitioning_strategy}.{key} cannot be null"
            )
        return strat_params.get(key, default)

    strat_out = dict(strat_params)
    if partitioning_strategy == "quantum_annealing":
        # Defaults (from your tables)
        qa_defaults = {
            "qubo_balance_lambda": 0.1,
            "num_reads": 5,
            "num_starts": 5,
            "balance_violation_lambda": 0.1,
            "simulated": True,
        }
        strat_out["qubo_balance_lambda"] = _coerce_float(
            _value_or_default("qubo_balance_lambda", qa_defaults["qubo_balance_lambda"]),
            "partitioning_parameters.strategies.quantum_annealing.qubo_balance_lambda",
        )
        strat_out["num_starts"] = _coerce_int(
            _value_or_default("num_starts", qa_defaults["num_starts"]),
            "partitioning_parameters.strategies.quantum_annealing.num_starts",
        )
        if strat_out["num_starts"] < 1:
            raise ValueError("partitioning_parameters.strategies.quantum_annealing.num_starts must be >= 1")
        strat_out["num_reads"] = _coerce_int(
            _value_or_default("num_reads", qa_defaults["num_reads"]),
            "partitioning_parameters.strategies.quantum_annealing.num_reads",
        )
        if strat_out["num_reads"] < 1:
            raise ValueError("partitioning_parameters.strategies.quantum_annealing.num_reads must be >= 1")
        strat_out["balance_violation_lambda"] = _coerce_float(
            _value_or_default(
                "balance_violation_lambda", qa_defaults["balance_violation_lambda"]
            ),
            "partitioning_parameters.strategies.quantum_annealing.balance_violation_lambda",
        )
        if strat_out["balance_violation_lambda"] < 0.0:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_annealing.balance_violation_lambda must be >= 0"
            )
        strat_out["simulated"] = _coerce_bool(
            _value_or_default("simulated", qa_defaults["simulated"]),
            "partitioning_parameters.strategies.quantum_annealing.simulated",
        )
        strat_out["qpu_solver_name"] = _coerce_optional_str(
            strat_params.get("qpu_solver_name"),
            "partitioning_parameters.strategies.quantum_annealing.qpu_solver_name",
        )
        strat_out["qpu_region"] = _coerce_optional_str(
            strat_params.get("qpu_region"),
            "partitioning_parameters.strategies.quantum_annealing.qpu_region",
        )
        strat_out["qpu_problem_label"] = _coerce_optional_str(
            strat_params.get("qpu_problem_label"),
            "partitioning_parameters.strategies.quantum_annealing.qpu_problem_label",
        )
    elif partitioning_strategy == "quantum_approximation_optimizer":
        # Defaults (from your tables)
        qaoa_defaults = {
            "qubo_balance_lambda": 0.1,
            "num_starts": 12,
            "balance_violation_lambda": 0.1,
            "circuit_depth": 12,
            "num_steps": 12,
            "num_shots": 5,
            "simulated": True,
        }
        if "qaoa_backend" in strat_params:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qaoa_backend is no longer used. "
                "Use simulated=true for PennyLane or simulated=false with qlm_qpu_name for QLM execution."
            )
        if "qlm_remote" in strat_params:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_remote is no longer used. "
                "QAOA uses PennyLane when simulated=true and the QLM backend named by qlm_qpu_name when simulated=false."
            )
        if "qlm_require_gate_based_hardware" in strat_params:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_require_gate_based_hardware is no longer supported. "
                "The repository now keeps only backend information that is actually exposed by the QLM API."
            )
        strat_out["qubo_balance_lambda"] = _coerce_float(
            _value_or_default("qubo_balance_lambda", qaoa_defaults["qubo_balance_lambda"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.qubo_balance_lambda",
        )
        strat_out["num_starts"] = _coerce_int(
            _value_or_default("num_starts", qaoa_defaults["num_starts"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.num_starts",
        )
        if strat_out["num_starts"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.num_starts must be >= 1"
            )
        strat_out["num_steps"] = _coerce_int(
            _value_or_default("num_steps", qaoa_defaults["num_steps"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.num_steps",
        )
        if strat_out["num_steps"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.num_steps must be >= 1"
            )
        strat_out["num_shots"] = _coerce_int(
            _value_or_default("num_shots", qaoa_defaults["num_shots"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.num_shots",
        )
        if strat_out["num_shots"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.num_shots must be >= 1"
            )
        strat_out["balance_violation_lambda"] = _coerce_float(
            _value_or_default(
                "balance_violation_lambda", qaoa_defaults["balance_violation_lambda"]
            ),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.balance_violation_lambda",
        )
        if strat_out["balance_violation_lambda"] < 0.0:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.balance_violation_lambda must be >= 0"
            )
        strat_out["circuit_depth"] = _coerce_int(
            _value_or_default("circuit_depth", qaoa_defaults["circuit_depth"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.circuit_depth",
        )
        if strat_out["circuit_depth"] < 1:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.circuit_depth must be >= 1"
            )
        strat_out["simulated"] = _coerce_bool(
            _value_or_default("simulated", qaoa_defaults["simulated"]),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.simulated",
        )
        if strat_out["simulated"]:
            strat_out["adam_learning_rate"] = _coerce_float(
                _value_or_default("adam_learning_rate", 0.1),
                "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate",
            )
            if strat_out["adam_learning_rate"] <= 0.0:
                raise ValueError(
                    "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate must be > 0"
                )
        else:
            adam_learning_rate = strat_params.get("adam_learning_rate")
            if adam_learning_rate is not None:
                adam_learning_rate = _coerce_float(
                    adam_learning_rate,
                    "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate",
                )
                if adam_learning_rate <= 0.0:
                    raise ValueError(
                        "partitioning_parameters.strategies.quantum_approximation_optimizer.adam_learning_rate must be > 0"
                    )
            strat_out["adam_learning_rate"] = adam_learning_rate
        strat_out["qlm_qpu_name"] = _coerce_optional_str(
            strat_params.get("qlm_qpu_name"),
            "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_qpu_name",
        )
        if not strat_out["simulated"] and not strat_out["qlm_qpu_name"]:
            raise ValueError(
                "partitioning_parameters.strategies.quantum_approximation_optimizer.qlm_qpu_name must be set when simulated is false"
            )
    else:
        # metis_partitioning requires no extra keys
        strat_out = dict(strat_params)

    pp_out = dict(pp)
    pp_out.update(
        {
            "partitioning_strategy": partitioning_strategy,
            "common": {"k_target": k_target, "balance_tolerance": balance_tolerance, **{k: v for k, v in common.items() if k not in ("k_target", "balance_tolerance")}},
            "strategies": {**strategies, partitioning_strategy: strat_out},
        }
    )

    # uncoarsening_parameters
    refine_objective = up.get("refine_objective")
    if not isinstance(refine_objective, str) or not refine_objective.strip():
        raise ValueError("uncoarsening_parameters.refine_objective must be a non-empty string")
    refine_objective = refine_objective.strip().lower()
    if refine_objective not in ("cut", "cut_balance"):
        raise ValueError("uncoarsening_parameters.refine_objective must be 'cut' or 'cut_balance'")
    refine_balance_lambda = _coerce_float(
        up.get("refine_balance_lambda"), "uncoarsening_parameters.refine_balance_lambda"
    )
    if refine_balance_lambda < 0.0:
        raise ValueError("uncoarsening_parameters.refine_balance_lambda must be >= 0")
    refine_max_passes_per_level = _coerce_int(
        up.get("refine_max_passes_per_level"), "uncoarsening_parameters.refine_max_passes_per_level"
    )
    if refine_max_passes_per_level < 0:
        raise ValueError("uncoarsening_parameters.refine_max_passes_per_level must be >= 0")
    refine_max_moves_per_pass = up.get("refine_max_moves_per_pass")
    if refine_max_moves_per_pass is not None:
        refine_max_moves_per_pass = _coerce_int(
            refine_max_moves_per_pass, "uncoarsening_parameters.refine_max_moves_per_pass"
        )
        if refine_max_moves_per_pass < 1:
            raise ValueError("uncoarsening_parameters.refine_max_moves_per_pass must be >= 1 if provided")

    validate_node_weights = up.get("validate_node_weights")
    if validate_node_weights is not None:
        validate_node_weights = _coerce_bool(
            validate_node_weights, "uncoarsening_parameters.validate_node_weights"
        )

    up_out = dict(up)
    up_out.update(
        {
            "refine_objective": refine_objective,
            "refine_balance_lambda": refine_balance_lambda,
            "refine_max_passes_per_level": refine_max_passes_per_level,
            "refine_max_moves_per_pass": refine_max_moves_per_pass,
            "validate_node_weights": validate_node_weights,
        }
    )

    out.update(
        {
            "general_parameters": gp_out,
            "coarsening_parameters": cp_out,
            "partitioning_parameters": pp_out,
            "uncoarsening_parameters": up_out,
        }
    )
    return out