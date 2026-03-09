from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

# Important: set a non-interactive backend before importing pyplot anywhere.
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from libs.domain_decomposition import decompose_matrices_m_k
from libs.utils import load_mtx, writte_results_table_text
from libs.vizualization import plot_sparsity_panel

from libs.utils import save_mtx, save_permutation_txt, write_json
from libs.log import start_sim, progress, finished, start_timer

from libs.matrix_metrics import collect_metrics

def run_simulation(
	simulation_name: str,
) -> Path:
	"""Run the simulation for specified name (e.g. simulation_01) as defined by ./simulations/<name>/simulation_parameters.json.

	Saves the result at the created results directory.
	"""

	start_sim(f"Running simulation {simulation_name}")

	# Defining paths
	repo_root = Path(__file__).resolve().parent.parent
	sim_dir = repo_root / simulation_name
	data_dir = sim_dir / "data"
	params_path = data_dir / "simulation_parameters.json"

	with params_path.open("r", encoding="utf-8") as f:
		params = json.load(f)

	matrices_dir = data_dir / "matrices"
	matrix_k_path = matrices_dir / str(params.get("MATRIX_K_NAME", "matrix_k.mtx"))
	matrix_m_path = matrices_dir / str(params.get("MATRIX_M_NAME", "matrix_m.mtx"))

	results_dir = sim_dir / "results"
	results_dir.mkdir(parents=True, exist_ok=True)
	results_run_dir = results_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
	results_run_dir.mkdir(parents=True, exist_ok=True)

	# General parameters
	dof_per_node = int(params.get("DOF_PER_NODE", 1))
	seed = int(params.get("SEED", 42))

	# Coarsening parameters
	coarsen_limit = int(params.get("COARSEN_LIMIT", 300))
	max_levels = int(params.get("MAX_LEVELS", 10))
	weight = str(params.get("WEIGHT", "weight"))
	strategy = str(params.get("STRATEGY", "sorted"))
	coarsen_ratio = float(params.get("COARSEN_RATIO", 0.85))
	max_node_weight = params.get("MAX_NODE_WEIGHT", None)
	if max_node_weight is not None:
		max_node_weight = float(max_node_weight)

	# Partitioning parameters
	k_target = int(params.get("K_TARGET", 2))
	balance_lambda = float(params.get("BALANCE_LAMBDA", 2.0))
	num_reads = int(params.get("NUM_READS", 1000))
	balance_tolerance = float(params.get("BALANCE_TOLERANCE", 2.0))
	partitioning_strategy = str(params.get("PARTITIONING_STRATEGY", "qa_partitioning")).strip().lower()
	qa_num_starts = int(params.get("QA_NUM_STARTS", 1))
	qa_select_balance_lambda = float(params.get("QA_SELECT_BALANCE_LAMBDA", 1.0e6))

	# Uncoarsening parameters
	refine_method = str(params.get("REFINE_METHOD", "greedy"))
	refine_objective = str(params.get("REFINE_OBJECTIVE", "cut"))
	refine_balance_lambda = float(params.get("REFINE_BALANCE_LAMBDA", 1.0))
	refine_max_passes_per_level = int(params.get("REFINE_MAX_PASSES_PER_LEVEL", 5))
	refine_max_moves_per_pass = params.get("REFINE_MAX_MOVES_PER_PASS", None)
	if refine_max_moves_per_pass is not None:
		refine_max_moves_per_pass = int(refine_max_moves_per_pass)
	validate_node_weights = params.get("VALIDATE_NODE_WEIGHTS", True)

	# Load matrices
	start = start_timer()
	progress("Loading Matrices")
	matrix_k = load_mtx(str(matrix_k_path), "K")
	matrix_m = load_mtx(str(matrix_m_path), "M")
	finished("Loading Matrices", start)

	# Run decomposition and permutation
	start = start_timer()
	m_perm, k_perm, permutation = decompose_matrices_m_k(
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
		validate_node_weights=validate_node_weights,
		seed=seed,
	)

	# Save results
	start = start_timer()
	progress("Writing permuted outputs")
	save_mtx(results_run_dir / "matrix_k_permuted.mtx", k_perm, comment=f"Permuted K ({partitioning_strategy})")
	save_mtx(results_run_dir / "matrix_m_permuted.mtx", m_perm, comment=f"Permuted M ({partitioning_strategy})")
	save_permutation_txt(results_run_dir / "permutation.txt", permutation)
	finished("Written permuted outputs", start)

	start = start_timer()
	progress("Plotting sparsity image")
	fig, _ = plot_sparsity_panel(
		matrix_k,
		k_perm,
		name_a="K (original)",
		name_b=f"K (permuted_{partitioning_strategy})",
		markersize=0.5,
		show=False,
		save_path=str(results_run_dir / f"sparsity_k_original_vs_k_permuted.png"),
		dpi=200,
	)
	plt.close(fig)
	finished("Plotted sparsity image", start)

	start = start_timer()
	progress("Computing metrics")
	metrics = {
		"K": collect_metrics(
			matrix_name="K",
			method_name=partitioning_strategy,
			original=matrix_k,
			permuted=k_perm,
			permutation=permutation,
			perm_check_samples=20000,
			perm_check_seed=0,
			perm_check_tol=0.0,
		),
		"M": collect_metrics(
			matrix_name="M",
			method_name=partitioning_strategy,
			original=matrix_m,
			permuted=m_perm,
			permutation=permutation,
			perm_check_samples=5000,
			perm_check_seed=0,
			perm_check_tol=0.0,
		),
	}
	writte_results_table_text(results_run_dir / "run_metrics.txt", metrics)
	write_json(results_run_dir / "run_metrics.json", metrics)
	write_json(results_run_dir / "run_simulation_parameters.json", params)
	finished("Computed metrics", start)

	return results_run_dir


def cli_main(argv: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(
		description=(
			"Run the permutation strategy from partitioning_STRATEGY in ./simulations/<name>/simulation_parameters.json. "
			"Writes results to ./simulations/<name>/results/<timestamp>/ with the following files: \n"
			"  - matrix_k_permuted.mtx\n"
			"  - matrix_m_permuted.mtx\n"
			"  - permutation.txt\n"
			"  - run_metrics.json\n"
			"  - run_simulation_parameters.json\n"
			"  - sparsity_k_original_vs_<strategy>.png\n"
		)
	)
	parser.add_argument(
		"simulation",
		help="Simulation folder name, e.g. ./simulations/simulation_01 (under ./simulations)",
	)

	args = parser.parse_args(argv)
	out_dir = run_simulation(args.simulation)
	print(f"\nDone. Results written to: {out_dir}")

if __name__ == "__main__":
	cli_main()
