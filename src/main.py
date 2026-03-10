from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")

from libs.domain_decomposition import decompose_matrices_m_k
from libs.utils import load_mtx, write_results_table_text

from libs.utils import save_mtx, save_permutation_txt, write_json, save_matrices_sparsity_comparison
from libs.log import (
	close_log_file,
	finished,
	info,
	progress,
	set_log_file,
	simulation_finished,
	simulation_started,
	start_timer,
)

from libs.matrix_metrics import collect_metrics

def run_simulation(
	simulation_name: str,
) -> Path:
	"""Run the simulation for specified name (e.g. simulation_01) as defined by ./simulations/<name>/simulation_parameters.json.

	Saves the result at the created results directory.
	"""

	# Defining paths
	repo_root = Path(__file__).resolve().parent.parent
	sim_dir = repo_root / "simulations" / simulation_name
	data_dir = sim_dir / "data"

	# Defining results directory paths (create early so we can log to file)
	results_dir = sim_dir / "results"
	results_dir.mkdir(parents=True, exist_ok=True)
	run_number = len(list(results_dir.glob("run_*")))
	result_run__name = f"run_{run_number}_{datetime.now().strftime('%d.%m.%Y_%H:%M:%S')}"
	result_run_dir = results_dir / result_run__name
	result_run_dir.mkdir(parents=True, exist_ok=True)
	set_log_file(result_run_dir / "run_log")

	simulation_started(f"Running simulation {simulation_name}")

	# Load simulation configuration
	simulation_config_file_path = data_dir / "simulation_config.json"
	with simulation_config_file_path.open("r", encoding="utf-8") as f:
		simulation_config = json.load(f)

	# Load simulation parameters
	simulation_parameters_path = data_dir / simulation_config.get("PARAMETERS_FILE_NAME", "simulation_parameters.json")
	with simulation_parameters_path.open("r", encoding="utf-8") as f:
		simulation_parameters = json.load(f)
	
	# Defining matrices paths
	matrices_dir = data_dir / "matrices"
	input_matrices = simulation_config.get("input_matrices", {})
	matrix_k_path = matrices_dir / str(input_matrices.get("MATRIX_K_NAME", "matrix_k.mtx"))
	matrix_m_path = matrices_dir / str(input_matrices.get("MATRIX_M_NAME", "matrix_m.mtx"))

	# General parameters
	general_parameters = simulation_parameters.get("general_parameters", {})
	dof_per_node = int(general_parameters.get("DOF_PER_NODE", 1))
	seed = int(general_parameters.get("SEED", 42))

	# Parameters
	coarsening_parameters = simulation_parameters.get("coarsening_parameters", {})
	partitioning_parameters = simulation_parameters.get("partitioning_parameters", {})
	uncoarsening_parameters = simulation_parameters.get("uncoarsening_parameters", {})

	# Which outputs to save
	save_output = set(simulation_config.get("save_output", []))

	# Coarsening parameters
	coarsen_limit = int(coarsening_parameters.get("COARSEN_LIMIT", 300))
	max_levels = int(coarsening_parameters.get("MAX_LEVELS", 10))
	weight = str(coarsening_parameters.get("WEIGHT", "weight"))
	strategy = str(coarsening_parameters.get("STRATEGY", "sorted"))
	coarsen_ratio = float(coarsening_parameters.get("COARSEN_RATIO", 0.85))
	max_node_weight = coarsening_parameters.get("MAX_NODE_WEIGHT", None)
	if max_node_weight is not None:
		max_node_weight = float(max_node_weight)

	# Partitioning parameters
	k_target = int(partitioning_parameters.get("K_TARGET", 2))
	balance_lambda = float(partitioning_parameters.get("BALANCE_LAMBDA", 2.0))
	num_reads = int(partitioning_parameters.get("NUM_READS", 1000))
	balance_tolerance = float(partitioning_parameters.get("BALANCE_TOLERANCE", 2.0))
	partitioning_strategy = str(partitioning_parameters.get("PARTITIONING_STRATEGY", "qa_partitioning")).strip().lower()
	qa_num_starts = int(partitioning_parameters.get("QA_NUM_STARTS", 1))
	qa_select_balance_lambda = float(partitioning_parameters.get("QA_SELECT_BALANCE_LAMBDA", 1.0e6))

	# Uncoarsening parameters
	refine_method = str(uncoarsening_parameters.get("REFINE_METHOD", "greedy"))
	refine_objective = str(uncoarsening_parameters.get("REFINE_OBJECTIVE", "cut"))
	refine_balance_lambda = float(uncoarsening_parameters.get("REFINE_BALANCE_LAMBDA", 1.0))
	refine_max_passes_per_level = int(uncoarsening_parameters.get("REFINE_MAX_PASSES_PER_LEVEL", 5))
	refine_max_moves_per_pass = uncoarsening_parameters.get("REFINE_MAX_MOVES_PER_PASS", None)
	if refine_max_moves_per_pass is not None:
		refine_max_moves_per_pass = int(refine_max_moves_per_pass)
	validate_node_weights = uncoarsening_parameters.get("VALIDATE_NODE_WEIGHTS", True)

	# Load matrices
	matrix_k = load_mtx(str(matrix_k_path), "K")
	matrix_m = load_mtx(str(matrix_m_path), "M")

	# Run decomposition and permutation
	start = start_timer()
	perm_matrix_m, perm_matrix_k, permutation = decompose_matrices_m_k(
		matrix_m=matrix_m,
		matrix_k=matrix_k,
		dof_per_node=dof_per_node,
		coarsen_limit=coarsen_limit,
		max_levels=max_levels,
		weight=weight,
		strategy=strategy,
		coarsen_ratio=coarsen_ratio,
		max_node_weight=max_node_weight,
		k_target=k_target,
		balance_lambda=balance_lambda,
		num_reads=num_reads,
		balance_tolerance=balance_tolerance,
		partitioning_strategy=partitioning_strategy,
		qa_num_starts=qa_num_starts,
		qa_select_balance_lambda=qa_select_balance_lambda,
		refine_method=refine_method,
		refine_objective=refine_objective,
		refine_balance_lambda=refine_balance_lambda,
		refine_max_passes_per_level=refine_max_passes_per_level,
		refine_max_moves_per_pass=refine_max_moves_per_pass,
		seed=seed,
	)

	# Save results
	if "matrix_k_permuted" in save_output or "matrix_m_permuted" in save_output or "permutation" in save_output:
		start = start_timer()
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
		start = start_timer()
		save_matrices_sparsity_comparison(
			matrix_k,
			perm_matrix_k,
			name_a="K (original)",
			name_b=f"K (permuted_{partitioning_strategy})",
			markersize=0.5,
			save_path=str(result_run_dir / "matrix_sparsity_comparison.png")
		)

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
		write_results_table_text(result_run_dir / "run_metrics.txt", metrics)
		write_json(result_run_dir / "run_metrics.json", metrics)
		if metrics["K"]["permutation_check"]["mismatches"] > 0:
			info(f"Permutation check found {metrics['K']['permutation_check']['mismatches']} mismatches with max abs error {metrics['K']['permutation_check']['max_abs_err']}")
		else:
			info(f"Permutation check passed with no mismatches")

	if "run_simulation_parameters" in save_output:
		write_json(result_run_dir / "run_simulation_parameters.json", simulation_parameters)

	return result_run_dir

def cli_main(argv: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(
		description=(
			"Reads ./simulations/<name>/data/simulation_config.json and the referenced parameters JSON. "
			"Runs the strategy from partitioning_parameters.PARTITIONING_STRATEGY. "
			"Only writes outputs listed in simulation_config.save_output into ./simulations/<name>/results/<timestamp>/."
		)
	)
	parser.add_argument(
		"simulation",
		help="Simulation name, e.g. simulation_01 (under ./simulations)",
	)

	args = parser.parse_args(argv)

	total_simulation_time = start_timer()
	out_dir: Path | None = None
	try:
		out_dir = run_simulation(args.simulation)
		simulation_finished("Simulation Completed Successfully", total_simulation_time)
		info(f"Results saved in {out_dir}")
	finally:
		close_log_file()

if __name__ == "__main__":
	cli_main()
