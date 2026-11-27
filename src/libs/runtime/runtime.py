from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from libs.domain_decomposition import decompose_matrix
from libs.runtime import workspace
from libs.runtime.defaults import unknown_parameter_keys
from libs.runtime.log import log, set_log_file
from libs.profiling.matrix_metrics import collect_metrics
from libs.runtime.utils import (
	load_mtx,
	resolve_parameters_file_path,
	resolve_simulation_matrix,
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
	demonstrator_dir: str | None,
	parameters_file_override: str | None = None,
	simulation_parameters_override: dict[str, Any] | None = None,
	*,
	simulation_config_override: dict[str, Any] | None = None,
	results_dir_override: str | Path | None = None,
	run_label: str | None = None,
	history_source: str | None = None,
) -> Path:
	"""Run one simulation and return its result directory.

	Normally ``demonstrator_dir`` is a simulation folder (e.g. ``simulations/simulation_01``) whose
	``data/simulation_config.json`` names the matrix pair and parameters file; results go to its
	``results/`` folder. Batch studies pass ``demonstrator_dir=None`` with in-memory
	``simulation_config_override`` / ``simulation_parameters_override`` and a ``results_dir_override``.
	"""

	# Defining paths
	project_root = workspace.root()
	sim_dir = project_root / demonstrator_dir if demonstrator_dir else None
	data_dir = sim_dir / "data" if sim_dir is not None else project_root

	if results_dir_override is not None:
		results_dir = Path(results_dir_override)
		if not results_dir.is_absolute():
			results_dir = project_root / results_dir
	elif sim_dir is not None:
		results_dir = sim_dir / "results"
	else:
		raise ValueError("run_simulation needs a simulation directory or results_dir_override")

	# Load simulation configuration (validated before creating any output folder)
	if simulation_config_override is not None:
		simulation_config = validate_and_normalize_simulation_config(simulation_config_override)
	elif sim_dir is not None:
		simulation_config_file_path = data_dir / "simulation_config.json"
		with simulation_config_file_path.open("r", encoding="utf-8") as f:
			simulation_config = validate_and_normalize_simulation_config(json.load(f))
	else:
		raise ValueError("run_simulation needs a simulation directory or simulation_config_override")

	# Create the run folder early so we can log to file
	results_dir.mkdir(parents=True, exist_ok=True)
	result_run_dir = _create_result_run_dir(results_dir)
	set_log_file(result_run_dir / "run_log")

	sim_name = run_label or (sim_dir.name if sim_dir is not None else "batch case")
	matrix_id = simulation_config["input_matrix"]
	log("INFO", f"Running {sim_name} on matrix {matrix_id}")

	# Load simulation parameters
	if simulation_parameters_override is not None:
		simulation_parameters = validate_and_normalize_simulation_parameters(simulation_parameters_override)
	else:
		if sim_dir is None:
			raise ValueError("run_simulation needs simulation_parameters_override when no simulation directory is given")
		parameters_file_reference = parameters_file_override or simulation_config.get("parameters_file_path")
		simulation_parameters_path = resolve_parameters_file_path(
			data_dir,
			parameters_file_reference,
		)
		with simulation_parameters_path.open("r", encoding="utf-8") as f:
			simulation_parameters = validate_and_normalize_simulation_parameters(json.load(f))
	unknown = unknown_parameter_keys(simulation_parameters)
	if unknown:
		log("WARNING", f"Ignoring unknown parameters (check for typos): {', '.join(unknown)}")

	# The library matrix to partition and permute
	matrix_path = resolve_simulation_matrix(simulation_config)

	def _rel(path: Path) -> str:
		try:
			return str(path.resolve().relative_to(project_root))
		except ValueError:
			return str(path)

	# Record exactly which matrix this run used (batch runs have no simulation folder to look up).
	write_json(
		result_run_dir / "run_inputs.json",
		{
			"simulation": sim_dir.name if sim_dir is not None else None,
			"matrix": matrix_id,
			"matrix_path": _rel(matrix_path),
		},
	)

	# Which outputs to save
	save_output = set(simulation_config.get("save_output", []))

	# Load the matrix
	matrix = load_mtx(str(matrix_path), matrix_id)

	general_parameters = simulation_parameters["general_parameters"]
	coarsening_parameters = simulation_parameters["coarsening_parameters"]
	partitioning_parameters = simulation_parameters["partitioning_parameters"]
	uncoarsening_parameters = simulation_parameters["uncoarsening_parameters"]

	# Run decomposition and permutation
	matrix_permuted, permutation, decomposition_artifacts = decompose_matrix(
		matrix=matrix,
		general_parameters=general_parameters,
		coarsening_parameters=coarsening_parameters,
		partitioning_parameters=partitioning_parameters,
		uncoarsening_parameters=uncoarsening_parameters,
	)

	partitioning_strategy = partitioning_parameters["partitioning_strategy"]
	_write_partition_artifacts(result_run_dir, decomposition_artifacts)
	decomposition_metrics = decomposition_artifacts.get("decomposition_metrics") or {}
	if decomposition_metrics:
		# Always written (small): partition quality + timing, read by the parameter tuner.
		write_json(result_run_dir / "decomposition_metrics.json", decomposition_metrics)
		log(
			"VERBOSE",
			"Partition quality: "
			f"edge_cut={decomposition_metrics.get('edge_cut'):.6g} "
			f"imbalance={decomposition_metrics.get('imbalance'):.4f} "
			f"levels={decomposition_metrics.get('levels')}",
		)

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

	if "matrix_permuted" in save_output:
		save_mtx(
			result_run_dir / "matrix_permuted.mtx",
			matrix_permuted,
			comment=f"Permuted {matrix_id} ({partitioning_strategy})",
		)
	if "permutation" in save_output:
		save_permutation_txt(result_run_dir / "permutation.txt", permutation)

	if "run_metrics" in save_output:
		# One entry keyed "matrix"; run_metrics.txt prints a table per entry.
		metrics = {
			"matrix": collect_metrics(
				matrix_name=matrix_id,
				method_name=partitioning_strategy,
				original=matrix,
				permuted=matrix_permuted,
				permutation=permutation,
				perm_check_samples=20000,
				perm_check_seed=0,
				perm_check_tol=0.0,
			),
		}
		if decomposition_metrics:
			metrics["matrix"]["decomposition_metrics"] = decomposition_metrics
		write_results_table_text(result_run_dir / "run_metrics.txt", metrics)
		write_json(result_run_dir / "run_metrics.json", metrics)
		struct = metrics["matrix"].get("structural_metrics", {})
		bw_orig = struct.get("original", {}).get("bandwidth")
		bw_perm = struct.get("permuted", {}).get("bandwidth")
		if bw_orig is not None and bw_perm is not None:
			log("VERBOSE", f"Matrix bandwidth: {bw_orig} -> {bw_perm}")
			if bw_perm > bw_orig:
				log("WARNING", f"Permuted matrix bandwidth ({bw_perm}) exceeded original bandwidth ({bw_orig})")
		check = metrics["matrix"]["permutation_check"]
		if check["mismatches"] > 0:
			log("WARNING", f"Permutation check found {check['mismatches']} mismatches with max abs error {check['max_abs_err']}")
		else:
			log("VERBOSE", "Permutation check passed with no mismatches")

	if "run_simulation_parameters" in save_output:
		write_json(result_run_dir / "run_simulation_parameters.json", simulation_parameters)

	# Feed the parameter-selection history; never fail a finished run because of it.
	try:
		from libs.tuning.history import record_run

		record_run(
			result_run_dir,
			matrix_id=matrix_id,
			parameters=simulation_parameters,
			simulation=sim_dir.name if sim_dir is not None else None,
			source=history_source or ("single" if sim_dir is not None else "batch"),
		)
	except Exception as exc:  # pragma: no cover - defensive
		log("WARNING", f"Could not record run in tuning history: {exc}")

	return result_run_dir