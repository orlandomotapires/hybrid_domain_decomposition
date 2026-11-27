import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from libs.runtime.utils import AVAILABLE_SAVE_OUTPUTS, validate_and_normalize_simulation_config
from libs.runtime.runtime import _write_partition_artifacts
from libs.runtime.runtime import run_simulation


class RuntimeUtilsTest(unittest.TestCase):
    def test_omitted_partitioning_keys_take_the_studio_defaults(self) -> None:
        from libs.runtime.defaults import default_parameters, strategy_defaults
        from libs.runtime.utils import validate_and_normalize_simulation_parameters

        for strategy in ("quantum_annealing", "quantum_approximation_optimizer"):
            params = default_parameters()
            params["partitioning_parameters"] = {"partitioning_strategy": strategy}
            out = validate_and_normalize_simulation_parameters(params)["partitioning_parameters"]
            self.assertEqual({"k_target": 4, "balance_tolerance": 2.0}, out["common"])
            block = out["strategies"][strategy]
            for key, value in strategy_defaults(strategy).items():
                self.assertEqual(value, block[key], f"{strategy}.{key}")

    def test_available_save_outputs_include_no_png_outputs(self) -> None:
        png_outputs = {entry for entry in AVAILABLE_SAVE_OUTPUTS if entry.endswith(".png")}

        self.assertEqual(set(), png_outputs)

    def test_validate_config_rejects_removed_plot_outputs(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_normalize_simulation_config(
                {
                    "parameters_file_path": "simulation_parameters.json",
                    "input_matrix": "blade",
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
                "common": {"k_target": 2, "balance_tolerance": 10.0},
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
                        "input_matrix": "blade",
                        "save_output": [],
                    }
                ),
                encoding="utf-8",
            )

            with patch("libs.runtime.runtime.resolve_parameters_file_path", side_effect=AssertionError("parameter file lookup should not be used")), \
                patch("libs.runtime.runtime.resolve_simulation_matrix", return_value=Path("dummy.mtx")), \
                patch("libs.runtime.runtime.load_mtx", side_effect=["matrix"]), \
                patch("libs.runtime.runtime.decompose_matrix", return_value=("perm", {0: 1}, {"coarse_partition": {0: 0}, "final_partition": {0: 1}})), \
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

    def test_simulation_config_takes_one_library_matrix(self) -> None:
        config = validate_and_normalize_simulation_config(
            {
                "parameters_file_path": "simulation_parameters.json",
                "input_matrix": " blade_h60 ",
                "save_output": ["matrix_permuted"],
            }
        )
        self.assertEqual("blade_h60", config["input_matrix"])

    def test_simulation_config_requires_a_matrix(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_normalize_simulation_config(
                {"parameters_file_path": "simulation_parameters.json", "save_output": []}
            )

    def test_old_k_m_keys_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_and_normalize_simulation_config(
                {
                    "parameters_file_path": "simulation_parameters.json",
                    "input_matrix": "blade",
                    "save_output": ["matrix_k_permuted"],
                }
            )


if __name__ == "__main__":
    unittest.main()