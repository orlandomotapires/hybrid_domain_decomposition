import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from libs.runtime.utils import AVAILABLE_SAVE_OUTPUTS, validate_and_normalize_simulation_config
from libs.runtime.runtime import _write_partition_artifacts
from libs.runtime.runtime import run_simulation


class RuntimeUtilsTest(unittest.TestCase):
    def test_available_save_outputs_include_no_png_outputs(self) -> None:
        png_outputs = {entry for entry in AVAILABLE_SAVE_OUTPUTS if entry.endswith(".png")}

        self.assertEqual(set(), png_outputs)

    def test_validate_config_rejects_removed_plot_outputs(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_normalize_simulation_config(
                {
                    "parameters_file_path": "simulation_parameters.json",
                    "input_matrices": {
                        "matrix_k_file_path": "k.mtx",
                        "matrix_m_file_path": "m.mtx",
                    },
                    "save_output": [
                        "matrix_sparsity_comparison",
                        "frac_within_band_plot",
                        "matrix_k_original_vs_permuted_colored.png",
                        "matrix_m_original_vs_permuted_colored.png",
                    ],
                }
            )

    def test_write_partition_artifacts_writes_json(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            result_dir = Path(tmp_dir)
            partition_artifacts_path = _write_partition_artifacts(
                result_dir,
                {
                    "coarse_partition": {0: 2, 1: 1},
                    "final_partition": {0: 3, 1: 4},
                },
            )

            self.assertEqual(result_dir / "partition_artifacts.json", partition_artifacts_path)
            self.assertTrue(partition_artifacts_path.exists())
            self.assertEqual(
                {
                    "coarse_partition": {"0": 2, "1": 1},
                    "final_partition": {"0": 3, "1": 4},
                },
                json.loads(partition_artifacts_path.read_text()),
            )

    def test_run_simulation_uses_in_memory_parameter_override(self) -> None:
        simulation_parameters = {
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
                "strategies": {"metis_partitioning": {}},
            },
            "uncoarsening_parameters": {
                "refine_objective": "cut",
                "refine_balance_lambda": 0.0,
                "refine_max_passes_per_level": 0,
                "refine_max_moves_per_pass": None,
                "validate_node_weights": None,
            },
        }

        with TemporaryDirectory() as tmp_dir:
            demonstrator_dir = Path(tmp_dir)
            data_dir = demonstrator_dir / "data"
            data_dir.mkdir(parents=True)
            (data_dir / "simulation_config.json").write_text(
                json.dumps(
                    {
                        "parameters_file_path": "unused_parameters.json",
                        "input_matrices": {
                            "matrix_k_file_path": "K.mtx",
                            "matrix_m_file_path": "M.mtx",
                        },
                        "save_output": [],
                    }
                ),
                encoding="utf-8",
            )

            with patch("libs.runtime.runtime.resolve_parameters_file_path", side_effect=AssertionError("parameter file lookup should not be used")), \
                patch("libs.runtime.runtime.resolve_matrix_input_path", side_effect=lambda *args, **kwargs: Path("dummy.mtx")), \
                patch("libs.runtime.runtime.load_mtx", side_effect=["matrix_k", "matrix_m"]), \
                patch("libs.runtime.runtime.decompose_matrices_m_k", return_value=("perm_m", "perm_k", {0: 1}, {"coarse_partition": {0: 0}, "final_partition": {0: 1}})), \
                patch("libs.runtime.runtime.set_log_file"), \
                patch("libs.runtime.runtime.log"), \
                patch("libs.runtime.runtime.write_json"), \
                patch("libs.runtime.runtime.save_coarse_graph_outputs"), \
                patch("libs.runtime.runtime.save_mtx"), \
                patch("libs.runtime.runtime.save_permutation_txt"), \
                patch("libs.runtime.runtime.write_results_table_text"):
                result_dir = run_simulation(
                    str(demonstrator_dir),
                    simulation_parameters_override=simulation_parameters,
                )

            self.assertEqual(demonstrator_dir / "results", result_dir.parent)
            self.assertTrue(result_dir.name.startswith("run_"))


if __name__ == "__main__":
    unittest.main()