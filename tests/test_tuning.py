import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import scipy.io
import scipy.sparse as sp

from libs.domain_decomposition import decompose_matrix
from libs.runtime.utils import validate_and_normalize_simulation_parameters
from libs.tuning.feasibility import backend_capacity, check_feasibility, qlm_qubit_limit
from libs.tuning.features import build_pipeline_graph
from libs.tuning.objectives import objective_values, validate_objectives, weighted_score
from libs.tuning.search_space import (
    apply_coarse_virtuals,
    default_search_space,
    normalize_search_space,
    parameters_to_trial_values,
    suggest_parameters,
)


def _grid_laplacian(nx_: int = 20, ny: int = 30) -> sp.csr_matrix:
    """2D 5-point Laplacian: a connected, symmetric, diagonally dominant test matrix."""
    def lap1(n):
        return sp.diags([-np.ones(n - 1), 2 * np.ones(n), -np.ones(n - 1)], [-1, 0, 1])
    A = sp.kron(sp.identity(ny), lap1(nx_)) + sp.kron(lap1(ny), sp.identity(nx_))
    return (A + 0.1 * sp.identity(nx_ * ny)).tocsr()


def _params(**coarsening) -> dict:
    cp = {"coarsen_inferior_limit": 40, "coarsen_superior_limit": 120, "max_levels": 20,
          "strategy": "sorted", "coarsen_ratio": 0.9, "max_node_weight": None, "weight": "weight"}
    cp.update(coarsening)
    return validate_and_normalize_simulation_parameters({
        "general_parameters": {"dof_per_node": 1, "seed": 0},
        "coarsening_parameters": cp,
        "partitioning_parameters": {"partitioning_strategy": "metis_partitioning",
                                    "common": {"k_target": 4, "balance_tolerance": 0.1},
                                    "strategies": {"metis_partitioning": {}}},
        "uncoarsening_parameters": {"refine_objective": "cut_balance", "refine_balance_lambda": 1.0,
                                    "refine_max_passes_per_level": 5, "refine_max_moves_per_pass": None,
                                    "validate_node_weights": False},
    })


class FeasibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.G = build_pipeline_graph(_grid_laplacian(), 1)

    def test_unreachable_coarsening_range_is_rejected(self) -> None:
        # 600-node graph cannot be coarsened into [1500, 2500] (the original simulation_01 failure).
        check = check_feasibility(self.G, _params(coarsen_inferior_limit=1500, coarsen_superior_limit=2500))
        self.assertFalse(check["feasible"])
        self.assertIn("Unable to coarsen", check["reasons"][0])

    def test_reachable_range_is_accepted(self) -> None:
        check = check_feasibility(self.G, _params())
        self.assertTrue(check["feasible"], check["reasons"])
        self.assertLessEqual(check["dry_run"]["coarse_nodes"], 120)

    def test_quantum_capacity(self) -> None:
        self.assertEqual(18, backend_capacity({"partitioning_strategy": "quantum_approximation_optimizer",
                                               "strategies": {"quantum_approximation_optimizer": {"simulated": True}}})[0])
        self.assertEqual((None, None), backend_capacity({"partitioning_strategy": "metis_partitioning"}))
        self.assertEqual(10, qlm_qubit_limit("qat.qpus:QSolidQPU10"))
        self.assertEqual(5, qlm_qubit_limit("qat.qpus:Jiqcer5QPU"))


class ObjectivesAndMetricsTest(unittest.TestCase):
    def test_decompose_reports_partition_quality_and_timing(self) -> None:
        p = _params()
        _, _, artifacts = decompose_matrix(_grid_laplacian(), p["general_parameters"], p["coarsening_parameters"],
                                           p["partitioning_parameters"], p["uncoarsening_parameters"])
        m = artifacts["decomposition_metrics"]
        self.assertEqual(4, m["effective_k"])
        self.assertGreater(m["edge_cut"], 0)
        self.assertTrue(0 < m["edge_cut_fraction"] < 1)
        self.assertGreaterEqual(m["imbalance"], 0)
        self.assertEqual(600, sum(m["part_sizes"]))
        self.assertIn("coarsening", m["timing"]["stage_durations_sec"])

    def test_objective_values_and_weighted_score(self) -> None:
        metrics = {
            "decomposition": {"edge_cut_fraction": 0.2, "imbalance": 0.05, "timing": {"total_sec": 2.0}},
            "structural": {"permuted": {"n": 100, "bandwidth": 25, "frac_within_|i-j|<=1.0%_of_n": 0.4}},
        }
        v = objective_values(metrics, ["edge_cut", "imbalance", "time", "bandwidth", "band_quality"])
        self.assertAlmostEqual(0.25, v["bandwidth"])
        self.assertAlmostEqual(0.6, v["band_quality"])
        self.assertAlmostEqual(2.0, weighted_score({"edge_cut": 0.2, "time": 2.0}, {}, {"edge_cut": 0.2, "time": 2.0}))
        with self.assertRaises(ValueError):
            validate_objectives([])
        with self.assertRaises(ValueError):
            validate_objectives(["residual"])


class SearchSpaceTest(unittest.TestCase):
    def test_fixed_k_and_strategy_by_default(self) -> None:
        space = default_search_space(_params())
        self.assertFalse(space["k_target"]["free"])
        self.assertFalse(space["partitioning_strategy"]["free"])

    def test_suggest_respects_fixed_and_free(self) -> None:
        import optuna

        base = _params()
        space = normalize_search_space({"k_target": {"free": True, "low": 2, "high": 6}}, base)
        study = optuna.create_study(sampler=optuna.samplers.RandomSampler(seed=1))
        for _ in range(10):
            trial = study.ask()
            p = suggest_parameters(trial, space, base)
            validate_and_normalize_simulation_parameters(p)
            self.assertEqual("metis_partitioning", p["partitioning_parameters"]["partitioning_strategy"])
            self.assertTrue(2 <= p["partitioning_parameters"]["common"]["k_target"] <= 6)
            cp = p["coarsening_parameters"]
            self.assertLessEqual(cp["coarsen_inferior_limit"], cp["coarsen_superior_limit"])
            study.tell(trial, 0.0)

    def test_quantum_strategy_caps_coarse_target(self) -> None:
        import optuna

        base = _params()
        space = normalize_search_space({"partitioning_strategy": {"free": True, "choices": ["quantum_approximation_optimizer"]},
                                        "coarse_target": {"free": True, "low": 10, "high": 300}}, base)
        trial = optuna.create_study().ask()
        p = suggest_parameters(trial, space, base)
        self.assertLessEqual(p["coarsening_parameters"]["coarsen_superior_limit"], 18)

    def test_trial_values_round_trip(self) -> None:
        base = _params()
        space = normalize_search_space({}, base)
        values = parameters_to_trial_values(base, space)
        self.assertEqual(120, values["coarse_target"])
        self.assertEqual("sorted", values["coarsening_strategy"])

    def test_coarse_virtuals_keep_inferior_at_least_k(self) -> None:
        p = _params()
        apply_coarse_virtuals(p, 10, 0.9)
        self.assertEqual(4, p["coarsening_parameters"]["coarsen_inferior_limit"])
        self.assertEqual(10, p["coarsening_parameters"]["coarsen_superior_limit"])


class EndToEndTuningTest(unittest.TestCase):
    """Auto-select and a short study on a temporary matrix library."""

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        lib = root / "matrices" / "grid"
        lib.mkdir(parents=True)
        scipy.io.mmwrite(str(lib / "grid.mtx"), _grid_laplacian())
        (lib / "matrix.json").write_text(json.dumps({"name": "grid", "file": "grid.mtx"}))
        self.root = root
        self.patches = [
            patch("libs.runtime.matrix_library.MATRIX_LIBRARY_DIR", root / "matrices"),
            patch.dict(os.environ, {"HDD_HISTORY_PATH": str(root / "history.jsonl")}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_auto_select_fixes_infeasible_range(self) -> None:
        from libs.tuning.auto_select import auto_select_parameters

        result = auto_select_parameters("grid", _params(coarsen_inferior_limit=1500, coarsen_superior_limit=2500))
        self.assertTrue(result["feasible"], result["reasons"])
        validate_and_normalize_simulation_parameters(result["parameters"])
        self.assertTrue((self.root / "matrices" / "grid" / "features.json").exists())

    def test_short_study_runs_and_records_history(self) -> None:
        from libs.tuning import tuner
        from libs.tuning.history import load_history

        with patch("libs.runtime.runtime.log"), patch("libs.runtime.runtime.set_log_file"):
            config = tuner.normalize_study_config({
                "matrix_id": "grid", "base_parameters": _params(), "objectives": ["edge_cut", "imbalance"],
                "aggregation": "pareto", "n_trials": 4, "seed": 0,
                "warm_start": {"base": True, "auto": False, "history": False},
            })
            self.assertEqual("nsga2", config["sampler"])
            study_dir = tuner.create_study_dir(config, parent=self.root / "studies")
            summary = tuner.run_study(study_dir)
        self.assertEqual(4, summary["trials_done"])
        self.assertGreaterEqual(summary["trials_ok"], 1)
        self.assertTrue(summary["pareto_front"])
        self.assertTrue((study_dir / "best_parameters.json").exists())
        self.assertEqual(summary["trials_ok"], len(load_history("grid")))


if __name__ == "__main__":
    unittest.main()
