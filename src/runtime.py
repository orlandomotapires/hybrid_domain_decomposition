from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")

from libs.domain_decomposition import decompose_matrices_m_k
from libs.log import log, set_log_file
from libs.matrix_metrics import collect_metrics, save_frac_within_band_plot
from libs.utils import (
	load_mtx,
	resolve_matrix_input_path,
	save_matrices_sparsity_comparison,
	save_mtx,
	save_permutation_txt,
	validate_and_normalize_simulation_config,
	validate_and_normalize_simulation_parameters,
	write_json,
	write_results_table_text,
)


def run_simulation(
	sim_dir: str,
) -> Path:
	"""Run the simulation for specified name (e.g. simulation_01) as defined by ./simulations/<name>/simulation_parameters.json.

	Saves the result at the created results directory.
	"""

	# Defining paths
	project_root = Path(__file__).resolve().parent.parent
	simulations_dir = project_root / sim_dir
	data_dir = simulations_dir / "data"

	# Defining results directory paths (create early so we can log to file)
	results_dir = simulations_dir / "results"
	results_dir.mkdir(parents=True, exist_ok=True)
	run_number = len(list(results_dir.glob("run_*")))
	result_run__name = f"run_{run_number}_{datetime.now().strftime('%d.%m.%Y_%H:%M:%S')}"
	result_run_dir = results_dir / result_run__name
	result_run_dir.mkdir(parents=True, exist_ok=True)
	set_log_file(result_run_dir / "run_log")

	sim_name = sim_dir.split("/")[-2] if sim_dir.endswith("/") else sim_dir.split("/")[-1]
	log("INFO", f"Running {sim_name}")

	# Load simulation configuration
	simulation_config_file_path = data_dir / "simulation_config.json"
	with simulation_config_file_path.open("r", encoding="utf-8") as f:
		simulation_config = validate_and_normalize_simulation_config(json.load(f))

	# Load simulation parameters
	simulation_parameters_path = data_dir / simulation_config.get("parameters_file_path")
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
	perm_matrix_m, perm_matrix_k, permutation = decompose_matrices_m_k(
		matrix_m=matrix_m,
		matrix_k=matrix_k,
		general_parameters=general_parameters,
		coarsening_parameters=coarsening_parameters,
		partitioning_parameters=partitioning_parameters,
		uncoarsening_parameters=uncoarsening_parameters,
	)

	partitioning_strategy = partitioning_parameters["partitioning_strategy"]

	# Save results
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

	if "matrix_sparsity_comparison" in save_output:
		save_matrices_sparsity_comparison(
			matrix_k,
			perm_matrix_k,
			name_a="K (original)",
			name_b=f"K (permuted_{partitioning_strategy})",
			markersize=0.5,
			save_path=str(result_run_dir / "matrix_sparsity_comparison.png")
		)

	metrics = None
	if "run_metrics" in save_output or "frac_within_band_plot" in save_output:
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

	if "frac_within_band_plot" in save_output and metrics is not None:
		save_frac_within_band_plot(
			metrics,
			result_run_dir / "frac_within_band_plot.png",
		)

	if "run_simulation_parameters" in save_output:
		write_json(result_run_dir / "run_simulation_parameters.json", simulation_parameters)

	return result_run_dir