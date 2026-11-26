"""The simulations service: create, edit, presets, validation, estimates, rename/delete and coarsening preview.

Ported from the web routes' contract tests when the web Studio was removed; the
HTTP status codes became the matching ``ServiceError`` subclasses.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hdd.services import matrices, simulations
from hdd.services.errors import Conflict, InvalidInput, NotFound
from libs.runtime import workspace

SIMULATION_KEYS = {
    "id", "demonstrator_dir", "simulation_config", "simulation_parameters", "active_parameters_file",
    "preset_files", "matrix", "runs_count", "latest_run", "estimates", "available_save_outputs",
}


class SimulationsServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = workspace.init(cls.tmp.name)
        cls.env = patch.dict(os.environ, {workspace.ENV_VAR: str(cls.root), "HDD_HISTORY_PATH": str(cls.root / "history.jsonl")})
        cls.env.start()
        cls.addClassCleanup(cls.env.stop)
        cls.matrix_id = matrices.generate_demo_matrix("demo")["id"]

    def new_simulation(self, name: str, **kwargs) -> dict:
        return simulations.create_simulation(name=name, matrix=kwargs.pop("matrix", self.matrix_id), **kwargs)

    # ------------------------------------------------------------ matrix library
    def test_library_lists_generated_matrix_with_header_info(self) -> None:
        entry = next(m for m in matrices.list_matrices()["matrices"] if m["id"] == self.matrix_id)
        self.assertTrue({"id", "name", "info", "used_by"} <= set(entry))
        self.assertEqual(entry["info"]["rows"], entry["info"]["cols"])
        self.assertTrue((self.root / "matrices" / self.matrix_id / "matrix.json").is_file())
        with self.assertRaises(NotFound):
            matrices.get_matrix("nope")

    def test_matrix_in_use_cannot_be_deleted(self) -> None:
        matrices.generate_demo_matrix("busy")
        self.new_simulation("uses_busy", matrix="busy")
        with self.assertRaises(Conflict):
            matrices.delete_matrix("busy")
        matrices.generate_demo_matrix("idle")
        matrices.delete_matrix("idle")
        self.assertFalse((self.root / "matrices" / "idle").exists())

    # --------------------------------------------------------------- simulations
    def test_create_get_and_list(self) -> None:
        created = self.new_simulation("alpha")
        self.assertEqual(SIMULATION_KEYS, set(created))
        self.assertEqual("simulations/alpha", created["demonstrator_dir"])
        self.assertEqual(self.matrix_id, created["simulation_config"]["input_matrix"])
        self.assertEqual("simulation_parameters.json", created["active_parameters_file"])
        self.assertEqual(created, simulations.get_simulation("alpha"))
        self.assertIn("alpha", [item["id"] for item in simulations.list_simulations()["demonstrators"]])

    def test_duplicate_is_a_conflict_and_unknown_is_not_found(self) -> None:
        self.new_simulation("dup")
        with self.assertRaises(Conflict):
            simulations.create_simulation(name="dup")
        with self.assertRaises(NotFound):
            simulations.get_simulation("missing")
        with self.assertRaises(NotFound):
            simulations.save_parameters("missing", {})

    def test_unnamed_simulation_gets_next_free_id(self) -> None:
        self.assertRegex(simulations.create_simulation(matrix=self.matrix_id)["id"], r"^simulation_\d\d$")

    def test_new_simulation_defaults_are_runnable_on_its_matrix(self) -> None:
        created = self.new_simulation("runnable")
        preview = simulations.preview_coarsening("runnable", created["simulation_parameters"])
        self.assertTrue(preview["reachable"], preview["stop_reason"])

    def test_clone_copies_parameters_and_presets(self) -> None:
        params = self.new_simulation("origin")["simulation_parameters"]
        params["partitioning_parameters"]["common"]["k_target"] = 3
        simulations.save_preset("origin", "k3", params, True)
        clone = simulations.create_simulation(name="copy", clone_from="origin")
        self.assertEqual("k3.json", clone["active_parameters_file"])
        self.assertEqual(3, clone["simulation_parameters"]["partitioning_parameters"]["common"]["k_target"])

    def test_update_parameters_validates_and_keeps_other_strategies(self) -> None:
        params = self.new_simulation("edit")["simulation_parameters"]
        params["partitioning_parameters"]["common"]["k_target"] = 6
        updated = simulations.save_parameters("edit", params)
        strategies = updated["simulation_parameters"]["partitioning_parameters"]["strategies"]
        self.assertTrue({"metis_partitioning", "quantum_annealing", "quantum_approximation_optimizer"} <= set(strategies))
        with self.assertRaises(InvalidInput):
            simulations.save_parameters("edit", {"general_parameters": "nope"})

    def test_update_config_rejects_unknown_parameters_file(self) -> None:
        config = self.new_simulation("cfg")["simulation_config"]
        simulations.save_config("cfg", config)
        with self.assertRaises(InvalidInput):
            simulations.save_config("cfg", {**config, "parameters_file_path": "does_not_exist.json"})

    def test_disk_errors_are_not_reported_as_invalid_input(self) -> None:
        params = self.new_simulation("disk")["simulation_parameters"]
        with patch("hdd.services.simulations.write_json", side_effect=PermissionError("read-only")):
            with self.assertRaises(PermissionError):
                simulations.save_parameters("disk", params)

    def test_saving_over_an_unreadable_parameters_file_keeps_a_copy(self) -> None:
        params = self.new_simulation("broken")["simulation_parameters"]
        data = workspace.simulations_dir() / "broken" / "data"
        (data / "simulation_parameters.json").write_text("{not json")
        simulations.save_parameters("broken", params)
        self.assertEqual("{not json", (data / "simulation_parameters.json.unreadable").read_text())

    def test_preset_lifecycle(self) -> None:
        params = self.new_simulation("presets")["simulation_parameters"]
        saved = simulations.save_preset("presets", "my preset", params, False)
        self.assertIn("my_preset.json", saved["preset_files"])
        self.assertEqual("simulation_parameters.json", saved["active_parameters_file"])
        self.assertEqual({"filename", "parameters", "estimates"}, set(simulations.load_preset("presets", "my_preset.json")))
        with self.assertRaises(InvalidInput):
            simulations.save_preset("presets", "simulation_config", params)
        with self.assertRaises(InvalidInput):
            simulations.delete_preset("presets", "simulation_parameters.json")
        self.assertNotIn("my_preset.json", simulations.delete_preset("presets", "my_preset.json")["preset_files"])

    def test_deleting_the_active_preset_falls_back_to_the_default(self) -> None:
        params = self.new_simulation("active")["simulation_parameters"]
        simulations.save_preset("active", "tmp", params, True)
        self.assertEqual("simulation_parameters.json", simulations.delete_preset("active", "tmp.json")["active_parameters_file"])

    def test_validate_parameters_reports_instead_of_failing(self) -> None:
        params = self.new_simulation("val")["simulation_parameters"]
        ok = simulations.validate_parameters(params)
        self.assertEqual({"valid", "normalized_parameters", "estimates", "unknown_keys"}, set(ok))
        self.assertTrue(ok["valid"])
        self.assertEqual([], ok["unknown_keys"])
        self.assertEqual({"valid", "error"}, set(simulations.validate_parameters({})))

    def test_typos_in_parameter_names_are_reported(self) -> None:
        params = self.new_simulation("typo")["simulation_parameters"]
        params["coarsening_parameters"]["coarsen_ratoi"] = 0.5
        params["partitioning_parameters"]["strategies"]["quantum_annealing"]["num_read"] = 3
        self.assertEqual(
            ["coarsening_parameters.coarsen_ratoi", "partitioning_parameters.strategies.quantum_annealing.num_read"],
            simulations.validate_parameters(params)["unknown_keys"],
        )

    def test_negative_seed_and_lambda_are_rejected(self) -> None:
        params = self.new_simulation("bounds")["simulation_parameters"]
        params["general_parameters"]["seed"] = -1
        self.assertFalse(simulations.validate_parameters(params)["valid"])
        params["general_parameters"]["seed"] = 1
        params["partitioning_parameters"]["partitioning_strategy"] = "quantum_annealing"
        params["partitioning_parameters"]["strategies"]["quantum_annealing"]["qubo_balance_lambda"] = -2.0
        self.assertIn("qubo_balance_lambda", simulations.validate_parameters(params)["error"])

    def test_quantum_estimates_follow_the_strategy(self) -> None:
        params = self.new_simulation("est")["simulation_parameters"]
        pp = params["partitioning_parameters"]
        pp["partitioning_strategy"] = "quantum_annealing"
        pp["common"]["k_target"] = 4
        pp["strategies"]["quantum_annealing"].update(num_starts=2, num_reads=10)
        estimates = simulations.validate_parameters(params)["estimates"]
        self.assertEqual(3, estimates["bipartitions_per_start"])
        self.assertEqual(6, estimates["expected_qpu_submissions"])
        self.assertEqual(60, estimates["expected_qpu_reads"])

    def test_rename_and_delete(self) -> None:
        self.new_simulation("old_name")
        self.new_simulation("taken")
        self.assertEqual("new_name", simulations.rename_simulation("old_name", "new name")["id"])
        with self.assertRaises(Conflict):
            simulations.rename_simulation("new_name", "taken")
        with self.assertRaises(NotFound):
            simulations.rename_simulation("old_name", "x")
        deleted = simulations.delete_simulation("new_name")
        self.assertEqual("new_name", deleted["deleted"])
        self.assertNotIn("new_name", deleted["remaining_demonstrators"])
        with self.assertRaises(NotFound):
            simulations.delete_simulation("new_name")

    def test_preview_coarsening_shape(self) -> None:
        params = self.new_simulation("prev")["simulation_parameters"]
        body = simulations.preview_coarsening("prev", params)
        self.assertEqual(
            {"reachable", "final_coarse_nodes", "final_coarse_edges", "accepted_levels_count", "stop_reason", "elapsed_ms", "levels"},
            set(body),
        )
        self.assertEqual(0, body["levels"][0]["level"])
        self.assertEqual(
            {"level", "nodes", "edges", "reduction_ratio", "min_vweight", "max_vweight", "in_target_range", "accepted"},
            set(body["levels"][0]),
        )
        with self.assertRaises(InvalidInput):
            simulations.preview_coarsening("prev", {})
        with self.assertRaises(NotFound):
            simulations.preview_coarsening("missing", params)


class LastSimulationTest(unittest.TestCase):
    def test_last_simulation_cannot_be_deleted(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {workspace.ENV_VAR: tmp}):
            simulations.create_simulation(name="only")
            with self.assertRaises(InvalidInput):
                simulations.delete_simulation("only")
            self.assertTrue((Path(tmp) / "simulations" / "only").is_dir())


if __name__ == "__main__":
    unittest.main()
