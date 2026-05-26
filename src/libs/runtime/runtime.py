from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
import matplotlib

matplotlib.use("Agg")

from libs.domain_decomposition import decompose_matrices_m_k
from libs.runtime.log import log, set_log_file
from libs.profiling.matrix_metrics import collect_metrics
from libs.runtime.utils import (
	load_mtx,
	resolve_parameters_file_path,
	resolve_matrix_input_path,
	save_coarse_graph_outputs,
	save_mtx,
	save_permutation_txt,
	validate_and_normalize_simulation_config,
	validate_and_normalize_simulation_parameters,
	write_json,
	write_results_table_text,
)


def _create_result_run_dir(results_dir: Path) -> Path:
	base_name = datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
	result_run_dir = results_dir / base_name
	if result_run_dir.exists():
		suffix = 1
		while True:
			candidate = results_dir / f"{base_name}_{suffix:02d}"
			if not candidate.exists():
				result_run_dir = candidate
				break
			suffix += 1
	result_run_dir.mkdir(parents=True, exist_ok=False)
	return result_run_dir


def _write_partition_artifacts(result_run_dir: Path, decomposition_artifacts: dict) -> Path:
	coarse_partition = decomposition_artifacts.get("coarse_partition")
	final_partition = decomposition_artifacts.get("final_partition")
	if coarse_partition is None or final_partition is None:
		raise ValueError("Decomposition did not return partition artifacts for export")

	partition_artifacts = {
		"coarse_partition": {str(node): int(partition_id) for node, partition_id in dict(coarse_partition).items()},
		"final_partition": {str(node): int(partition_id) for node, partition_id in dict(final_partition).items()},
	}
	partition_artifacts_path = result_run_dir / "partition_artifacts.json"
	write_json(partition_artifacts_path, partition_artifacts)
	return partition_artifacts_path


def run_simulation(
	demonstrator_dir: str,
	parameters_file_override: str | None = None,
	simulation_parameters_override: dict[str, Any] | None = None,
) -> Path:
	"""Run the simulation for specified name (e.g. demonstrator_01) as defined by ./demonstrators/<demonstrator>/simulation_parameters.json.

	Saves the result at the created results directory.
	"""

	# Defining paths
	project_root = Path(__file__).resolve().parents[3]
	demonstrators_dir = project_root / demonstrator_dir
	data_dir = demonstrators_dir / "data"

	# Defining results directory paths (create early so we can log to file)
	results_dir = demonstrators_dir / "results"
	results_dir.mkdir(parents=True, exist_ok=True)
	result_run_dir = _create_result_run_dir(results_dir)
	set_log_file(result_run_dir / "run_log")

	sim_name = demonstrator_dir.split("/")[-2] if demonstrator_dir.endswith("/") else demonstrator_dir.split("/")[-1]
	log("INFO", f"Running {sim_name}")

	# Load simulation configuration
	simulation_config_file_path = data_dir / "simulation_config.json"
	with simulation_config_file_path.open("r", encoding="utf-8") as f:
		simulation_config = validate_and_normalize_simulation_config(json.load(f))

	# Load simulation parameters
	if simulation_parameters_override is not None:
		simulation_parameters = validate_and_normalize_simulation_parameters(simulation_parameters_override)
	else:
		parameters_file_reference = parameters_file_override or simulation_config.get("parameters_file_path")
		simulation_parameters_path = resolve_parameters_file_path(
			data_dir,
			parameters_file_reference,
		)
		with simulation_parameters_path.open("r", encoding="utf-8") as f:
			simulation_parameters = validate_and_normalize_simulation_parameters(json.load(f))

	# Defining matrices paths
	matrices_dir = data_dir / "matrices"
	input_matrices = simulation_config.get("input_matrices", {})
	matrix_k_path = resolve_matrix_input_path(
		matrices_dir,
		input_matrices,
		key="matrix_k_file_path",
		label="K",
	)
	matrix_m_path = resolve_matrix_input_path(
		matrices_dir,
		input_matrices,
		key="matrix_m_file_path",
		label="M",
	)

	# Which outputs to save
	save_output = set(simulation_config.get("save_output", []))

	# Load matrices
	matrix_k = load_mtx(str(matrix_k_path), "K")
	matrix_m = load_mtx(str(matrix_m_path), "M")

	general_parameters = simulation_parameters["general_parameters"]
	coarsening_parameters = simulation_parameters["coarsening_parameters"]
	partitioning_parameters = simulation_parameters["partitioning_parameters"]
	uncoarsening_parameters = simulation_parameters["uncoarsening_parameters"]

	# Run decomposition and permutation
	perm_matrix_m, perm_matrix_k, permutation, decomposition_artifacts = decompose_matrices_m_k(
		matrix_m=matrix_m,
		matrix_k=matrix_k,
		general_parameters=general_parameters,
		coarsening_parameters=coarsening_parameters,
		partitioning_parameters=partitioning_parameters,
		uncoarsening_parameters=uncoarsening_parameters,
	)

	partitioning_strategy = partitioning_parameters["partitioning_strategy"]
	_write_partition_artifacts(result_run_dir, decomposition_artifacts)

	# Save results
	if "coarsened_graph" in save_output:
		coarse_graph = decomposition_artifacts.get("coarse_graph")
		if coarse_graph is None:
			raise ValueError("Decomposition did not return the final coarse graph for export")

		save_coarse_graph_outputs(
			result_run_dir,
			coarse_graph,
			weight_attr=coarsening_parameters["weight"],
		)

	if "matrix_k_permuted" in save_output or "matrix_m_permuted" in save_output or "permutation" in save_output:
		if "matrix_k_permuted" in save_output:
			save_mtx(
				result_run_dir / "matrix_k_permuted.mtx",
				perm_matrix_k,
				comment=f"Permuted K ({partitioning_strategy})",
			)
		if "matrix_m_permuted" in save_output:
			save_mtx(
				result_run_dir / "matrix_m_permuted.mtx",
				perm_matrix_m,
				comment=f"Permuted M ({partitioning_strategy})",
			)
		if "permutation" in save_output:
			save_permutation_txt(result_run_dir / "permutation.txt", permutation)

	metrics = None
	if "run_metrics" in save_output:
		metrics = {
			"K": collect_metrics(
				matrix_name="K",
				method_name=partitioning_strategy,
				original=matrix_k,
				permuted=perm_matrix_k,
				permutation=permutation,
				perm_check_samples=20000,
				perm_check_seed=0,
				perm_check_tol=0.0,
			),
			"M": collect_metrics(
				matrix_name="M",
				method_name=partitioning_strategy,
				original=matrix_m,
				permuted=perm_matrix_m,
				permutation=permutation,
				perm_check_samples=5000,
				perm_check_seed=0,
				perm_check_tol=0.0,
			),
		}

	if "run_metrics" in save_output and metrics is not None:
		write_results_table_text(result_run_dir / "run_metrics.txt", metrics)
		write_json(result_run_dir / "run_metrics.json", metrics)
		if metrics["K"]["permutation_check"]["mismatches"] > 0:
			log("VERBOSE", f"Permutation check found {metrics['K']['permutation_check']['mismatches']} mismatches with max abs error {metrics['K']['permutation_check']['max_abs_err']}")
		else:
			log("VERBOSE", f"Permutation check passed with no mismatches")

	if "run_simulation_parameters" in save_output:
		write_json(result_run_dir / "run_simulation_parameters.json", simulation_parameters)

	return result_run_dir