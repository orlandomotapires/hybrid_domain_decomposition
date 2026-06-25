import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import batch.run_batch as run_batch


class RunBatchTest(unittest.TestCase):
    def test_default_batch_covers_both_thesis_demonstrators(self) -> None:
        geometry_keys = {geometry.key for geometry in run_batch.GEOMETRIES}
        self.assertEqual({"demonstrator_01", "demonstrator_02"}, geometry_keys)

    def test_extract_summary_metrics_exports_percentage_band_columns(self) -> None:
        run_metrics = {
            "K": {
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

        summary = run_batch._extract_summary_metrics(run_metrics, "K")

        self.assertEqual(0.1, summary["K_frac_0_1pct_original"])
        self.assertEqual(0.8, summary["K_frac_1_0pct_permuted"])
        self.assertNotIn("K_frac_within_200_original", summary)

    def test_finalize_batch_writes_only_json_summary(self) -> None:
        manifest = {
            "cases": [],
        }

        with TemporaryDirectory(dir=run_batch.ROOT_DIR) as tmp_dir:
            batch_dir = Path(tmp_dir)
            manifest_path = batch_dir / "batch_manifest.json"

            run_batch._finalize_batch(batch_dir, manifest_path, manifest)

            written_manifest = run_batch._load_json(manifest_path)
            self.assertEqual("batch_summary.json", Path(written_manifest["summary_json"]).name)
            self.assertNotIn("summary_csv", written_manifest)
            self.assertTrue((batch_dir / "batch_summary.json").exists())
            self.assertFalse((batch_dir / "batch_summary.csv").exists())

    def test_write_batch_configuration_snapshot_copies_json_into_batch_dir(self) -> None:
        with TemporaryDirectory(dir=run_batch.ROOT_DIR) as tmp_dir:
            batch_dir = Path(tmp_dir)

            snapshot_path = run_batch._write_batch_configuration_snapshot(batch_dir)

            self.assertEqual(batch_dir / "batch_configuration.json", snapshot_path)
            self.assertTrue(snapshot_path.exists())
            self.assertEqual(run_batch._load_json(run_batch.BATCH_CONFIGURATION_PATH), run_batch._load_json(snapshot_path))

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
                "common": {"k_target": 2, "balance_tolerance": 0.1},
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