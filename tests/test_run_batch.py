import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import libs.batch.run_batch as run_batch
from libs.runtime import workspace

REPO_ROOT = Path(__file__).resolve().parents[1]


class BatchLifecycleTest(unittest.TestCase):
    """A real batch on a temporary workspace: failures, interruption and the summary."""

    def setUp(self) -> None:
        import json

        from tests.test_tuning import _params
        from tests.test_workspace import make_workspace

        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_workspace(Path(self.tmp.name).resolve())
        env = patch.dict(os.environ, {workspace.ENV_VAR: str(self.root), "HDD_DISABLE_HISTORY": "1"})
        env.start()
        self.addCleanup(env.stop)
        (self.root / "batch" / "batch_configuration.json").write_text(json.dumps({
            "matrices": [{"key": "grid"}, {"key": "missing"}],
            "algorithm_presets": [{"key": "metis", "partitioning_strategy": "metis_partitioning",
                                   "allowed_sizes": ["small"], "strategy_parameters": {}}],
            "coarsening_presets": [{"key": "small", "coarsen_inferior_limit": 40, "coarsen_superior_limit": 120}],
            "common_defaults": {}, "base_parameters": _params(), "save_output": ["run_metrics"],
        }))
        run_batch.batch_configuration(reload=True)

    def _manifest(self) -> dict:
        import json

        (batch_dir,) = workspace.batch_runs_dir().iterdir()
        return json.loads((batch_dir / "batch_manifest.json").read_text()), batch_dir

    def test_each_case_succeeds_or_fails_on_its_own(self) -> None:
        with patch("libs.runtime.runtime.log"), patch("libs.runtime.runtime.set_log_file"):
            code = run_batch.main([])
        manifest, batch_dir = self._manifest()
        self.assertEqual(1, code)  # one case failed
        self.assertEqual(["completed", "failed"], [c["status"] for c in manifest["cases"]])
        self.assertTrue((batch_dir / "batch_summary.json").exists())

    def test_an_interrupted_batch_marks_its_unfinished_cases(self) -> None:
        with patch.object(run_batch, "_run_one_case", side_effect=SystemExit(143)):
            with self.assertRaises(SystemExit):
                run_batch.main([])
        manifest, batch_dir = self._manifest()
        self.assertEqual("cancelled", manifest["interrupted"])
        self.assertEqual("cancelled", manifest["cases"][0]["status"])
        self.assertTrue((batch_dir / "batch_summary.json").exists())

    def test_an_unreadable_metrics_file_does_not_cost_the_summary(self) -> None:
        bad = self.root / "simulations" / "x" / "run_1"
        bad.mkdir(parents=True)
        (bad / "run_metrics.json").write_text("{truncated")
        rows = run_batch._build_batch_summary({"cases": [{"case_key": "a", "status": "completed",
                                                          "result_dir": "simulations/x/run_1"}]})
        self.assertIn("Unreadable", rows[0]["error_message"])


class RunBatchTest(unittest.TestCase):
    """Checks the repository's own batch configuration, so the workspace is the repository."""

    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {workspace.ENV_VAR: str(REPO_ROOT)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _scratch_dir(self) -> TemporaryDirectory:
        # Inside the workspace (paths are written relative to it) but under the ignored batch/runs/.
        runs = workspace.batch_runs_dir()
        runs.mkdir(parents=True, exist_ok=True)
        return TemporaryDirectory(dir=runs)

    def test_default_batch_uses_library_matrices(self) -> None:
        self.assertTrue(run_batch.GEOMETRIES)
        for geometry in run_batch.GEOMETRIES:
            self.assertTrue(
                (workspace.root() / "matrices" / geometry.key / "matrix.json").exists(),
                f"{geometry.key} is not a matrix in the library",
            )

    def test_case_results_go_to_the_batch_cases_folder(self) -> None:
        case = run_batch.build_cases()[0]
        batch_dir = workspace.batch_runs_dir() / "batch_test"
        kwargs = run_batch._case_run_kwargs(case, batch_dir)
        self.assertEqual(f"batch/runs/batch_test/cases/{case.case_key}", kwargs["results_dir_override"])
        self.assertEqual(case.geometry.key, kwargs["simulation_config_override"]["input_matrix"])

    def test_extract_summary_metrics_exports_percentage_band_columns(self) -> None:
        run_metrics = {
            "matrix": {
                "structural_metrics": {
                    "original": {
                        "bandwidth": 10,
                        "avg_bandwidth": 2.5,
                        "nnz": 20,
                        "frac_within_|i-j|<=0.1%_of_n": 0.1,
                        "frac_within_|i-j|<=0.4%_of_n": 0.2,
                        "frac_within_|i-j|<=0.7%_of_n": 0.3,
                        "frac_within_|i-j|<=1.0%_of_n": 0.4,
                    },
                    "permuted": {
                        "bandwidth": 8,
                        "avg_bandwidth": 2.0,
                        "nnz": 20,
                        "frac_within_|i-j|<=0.1%_of_n": 0.5,
                        "frac_within_|i-j|<=0.4%_of_n": 0.6,
                        "frac_within_|i-j|<=0.7%_of_n": 0.7,
                        "frac_within_|i-j|<=1.0%_of_n": 0.8,
                    },
                },
                "permutation_check": {
                    "mismatches": 0,
                    "max_abs_err": 0.0,
                },
            }
        }

        summary = run_batch._extract_summary_metrics(run_metrics)

        self.assertEqual(0.1, summary["frac_0_1pct_original"])
        self.assertEqual(0.8, summary["frac_1_0pct_permuted"])
        self.assertNotIn("frac_within_200_original", summary)

    def test_finalize_batch_writes_only_json_summary(self) -> None:
        manifest = {
            "cases": [],
        }

        with self._scratch_dir() as tmp_dir:
            batch_dir = Path(tmp_dir)
            manifest_path = batch_dir / "batch_manifest.json"

            run_batch._finalize_batch(batch_dir, manifest_path, manifest)

            written_manifest = run_batch._load_json(manifest_path)
            self.assertEqual("batch_summary.json", Path(written_manifest["summary_json"]).name)
            self.assertNotIn("summary_csv", written_manifest)
            self.assertTrue((batch_dir / "batch_summary.json").exists())
            self.assertFalse((batch_dir / "batch_summary.csv").exists())

    def test_write_batch_configuration_snapshot_copies_json_into_batch_dir(self) -> None:
        with self._scratch_dir() as tmp_dir:
            batch_dir = Path(tmp_dir)

            snapshot_path = run_batch._write_batch_configuration_snapshot(batch_dir)

            self.assertEqual(batch_dir / "batch_configuration.json", snapshot_path)
            self.assertTrue(snapshot_path.exists())
            self.assertEqual(run_batch._load_json(workspace.batch_config_path()), run_batch._load_json(snapshot_path))

    def test_build_case_parameters_stays_in_memory(self) -> None:
        case = run_batch.build_cases()[0]
        # Keep this test independent from repository data files present on CI.
        # We only need a valid in-memory parameters payload to verify that
        # _build_case_parameters does not write to disk.
        base_parameters = {
            "general_parameters": {"dof_per_node": 1, "seed": 0},
            "coarsening_parameters": {
                "coarsen_inferior_limit": 1,
                "coarsen_superior_limit": 2,
                "max_levels": 1,
                "weight": "weight",
                "strategy": "random",
                "coarsen_ratio": 0.5,
                "max_node_weight": None,
            },
            "partitioning_parameters": {
                "partitioning_strategy": "metis_partitioning",
                "common": {"k_target": 2, "balance_tolerance": 10.0},
                "strategies": {
                    "metis_partitioning": {},
                    "quantum_annealing": {
                        "qubo_balance_lambda": 1.0,
                        "num_reads": 10,
                        "num_starts": 1,
                        "balance_violation_lambda": 0.0,
                        "simulated": True,
                    },
                    "quantum_approximation_optimizer": {
                        "qubo_balance_lambda": 1.0,
                        "num_starts": 1,
                        "balance_violation_lambda": 0.0,
                        "circuit_depth": 1,
                        "num_steps": 1,
                        "adam_learning_rate": 0.01,
                        "num_shots": 16,
                        "simulated": True,
                    },
                },
            },
            "uncoarsening_parameters": {
                "refine_objective": "cut",
                "refine_balance_lambda": 0.0,
                "refine_max_passes_per_level": 0,
                "refine_max_moves_per_pass": None,
                "validate_node_weights": None,
            },
        }

        with patch.object(run_batch, "write_json") as write_json_mock:
            simulation_parameters = run_batch._build_case_parameters(case, base_parameters)

        write_json_mock.assert_not_called()
        self.assertIsInstance(simulation_parameters, dict)
        self.assertEqual(
            case.algorithm.partitioning_strategy,
            simulation_parameters["partitioning_parameters"]["partitioning_strategy"],
        )


if __name__ == "__main__":
    unittest.main()