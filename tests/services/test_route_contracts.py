"""Contract of the web API for simulations and the matrix library.

These tests pin status codes and response shapes while the logic behind the routes
moves into ``hdd.services``. They run against a temporary workspace.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from libs.runtime import workspace

SIMULATION_KEYS = {
    "id", "demonstrator_dir", "simulation_config", "simulation_parameters", "active_parameters_file",
    "preset_files", "matrix", "runs_count", "latest_run", "estimates", "available_save_outputs",
}


class RouteContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = workspace.init(cls.tmp.name)
        cls.env = patch.dict(os.environ, {workspace.ENV_VAR: str(cls.root), "HDD_HISTORY_PATH": str(cls.root / "history.jsonl")})
        cls.env.start()
        cls.addClassCleanup(cls.env.stop)
        from fastapi.testclient import TestClient

        from backend.app import app

        cls.client = TestClient(app)
        created = cls.client.post("/api/matrix-library/generate-demo", json={"name": "demo"})
        assert created.status_code == 200, created.text
        cls.matrix_id = created.json()["id"]

    def new_simulation(self, name: str, **body) -> dict:
        response = self.client.post("/api/demonstrators", json={"name": name, "matrix": self.matrix_id, **body})
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    # ------------------------------------------------------------ matrix library
    def test_library_lists_generated_matrix_with_header_info(self) -> None:
        body = self.client.get("/api/matrix-library").json()
        entry = next(m for m in body["matrices"] if m["id"] == self.matrix_id)
        self.assertTrue({"id", "name", "info", "used_by"} <= set(entry))
        self.assertEqual(entry["info"]["rows"], entry["info"]["cols"])
        self.assertTrue((self.root / "matrices" / self.matrix_id / "matrix.json").is_file())

    def test_library_get_unknown_is_404(self) -> None:
        self.assertEqual(404, self.client.get("/api/matrix-library/nope").status_code)

    def test_matrix_in_use_cannot_be_deleted(self) -> None:
        self.client.post("/api/matrix-library/generate-demo", json={"name": "busy"})
        self.new_simulation("uses_busy", matrix="busy")
        response = self.client.delete("/api/matrix-library/busy")
        self.assertEqual(409, response.status_code)
        self.assertIn("detail", response.json())
        self.client.post("/api/matrix-library/generate-demo", json={"name": "idle"})
        self.assertEqual(200, self.client.delete("/api/matrix-library/idle").status_code)
        self.assertFalse((self.root / "matrices" / "idle").exists())

    def test_upload_accepts_mtx_and_rejects_everything_else(self) -> None:
        source = next((self.root / "matrices" / self.matrix_id).glob("*.mtx")).read_bytes()
        ok = self.client.post("/api/matrix-library/upload", data={"name": "Uploaded one"}, files={"file": ("my file.mtx", source)})
        self.assertEqual(200, ok.status_code, ok.text)
        self.assertEqual("Uploaded_one", ok.json()["id"])
        self.assertTrue((self.root / "matrices" / "Uploaded_one" / "my_file.mtx").is_file())
        again = self.client.post("/api/matrix-library/upload", data={"name": "Uploaded one"}, files={"file": ("a.mtx", source)})
        self.assertEqual(409, again.status_code)
        wrong_type = self.client.post("/api/matrix-library/upload", data={"name": "txt"}, files={"file": ("a.txt", b"x")})
        self.assertEqual(400, wrong_type.status_code)
        garbage = self.client.post("/api/matrix-library/upload", data={"name": "garbage"}, files={"file": ("a.mtx", b"not a matrix")})
        self.assertEqual(400, garbage.status_code)
        self.assertFalse((self.root / "matrices" / "garbage").exists())

    # --------------------------------------------------------------- simulations
    def test_create_get_and_list(self) -> None:
        created = self.new_simulation("alpha")
        self.assertEqual(SIMULATION_KEYS, set(created))
        self.assertEqual("simulations/alpha", created["demonstrator_dir"])
        self.assertEqual(self.matrix_id, created["simulation_config"]["input_matrix"])
        self.assertEqual("simulation_parameters.json", created["active_parameters_file"])
        self.assertEqual(created, self.client.get("/api/demonstrators/alpha").json())
        listed = self.client.get("/api/demonstrators").json()["demonstrators"]
        self.assertIn("alpha", [item["id"] for item in listed])

    def test_create_duplicate_is_409_and_unknown_is_404(self) -> None:
        self.new_simulation("dup")
        self.assertEqual(409, self.client.post("/api/demonstrators", json={"name": "dup"}).status_code)
        self.assertEqual(404, self.client.get("/api/demonstrators/missing").status_code)
        self.assertEqual(404, self.client.put("/api/demonstrators/missing/parameters", json={}).status_code)

    def test_unnamed_simulation_gets_next_free_id(self) -> None:
        response = self.client.post("/api/demonstrators", json={"matrix": self.matrix_id})
        self.assertRegex(response.json()["id"], r"^simulation_\d\d$")

    def test_new_simulation_defaults_are_runnable_on_its_matrix(self) -> None:
        created = self.new_simulation("runnable")
        preview = self.client.post("/api/demonstrators/runnable/preview-coarsening", json=created["simulation_parameters"])
        self.assertEqual(200, preview.status_code, preview.text)
        self.assertTrue(preview.json()["reachable"], preview.json()["stop_reason"])

    def test_clone_copies_parameters_and_presets(self) -> None:
        source = self.new_simulation("origin")
        params = source["simulation_parameters"]
        params["partitioning_parameters"]["common"]["k_target"] = 3
        self.client.post("/api/demonstrators/origin/presets", json={"filename": "k3", "parameters": params, "set_active": True})
        clone = self.client.post("/api/demonstrators", json={"name": "copy", "clone_from": "origin"}).json()
        self.assertEqual("k3.json", clone["active_parameters_file"])
        self.assertEqual(3, clone["simulation_parameters"]["partitioning_parameters"]["common"]["k_target"])

    def test_update_parameters_validates_and_keeps_other_strategies(self) -> None:
        params = self.new_simulation("edit")["simulation_parameters"]
        params["partitioning_parameters"]["common"]["k_target"] = 6
        updated = self.client.put("/api/demonstrators/edit/parameters", json=params)
        self.assertEqual(200, updated.status_code, updated.text)
        strategies = updated.json()["simulation_parameters"]["partitioning_parameters"]["strategies"]
        self.assertTrue({"metis_partitioning", "quantum_annealing", "quantum_approximation_optimizer"} <= set(strategies))
        bad = self.client.put("/api/demonstrators/edit/parameters", json={"general_parameters": "nope"})
        self.assertEqual(400, bad.status_code)
        self.assertIn("detail", bad.json())

    def test_update_config_rejects_unknown_parameters_file(self) -> None:
        config = self.new_simulation("cfg")["simulation_config"]
        self.assertEqual(200, self.client.put("/api/demonstrators/cfg/config", json=config).status_code)
        config["parameters_file_path"] = "does_not_exist.json"
        self.assertEqual(400, self.client.put("/api/demonstrators/cfg/config", json=config).status_code)

    def test_preset_lifecycle(self) -> None:
        params = self.new_simulation("presets")["simulation_parameters"]
        saved = self.client.post("/api/demonstrators/presets/presets", json={"filename": "my preset", "parameters": params, "set_active": False}).json()
        self.assertIn("my_preset.json", saved["preset_files"])
        self.assertEqual("simulation_parameters.json", saved["active_parameters_file"])
        loaded = self.client.get("/api/demonstrators/presets/presets/my_preset.json").json()
        self.assertEqual({"filename", "parameters", "estimates"}, set(loaded))
        reserved = self.client.post("/api/demonstrators/presets/presets", json={"filename": "simulation_config", "parameters": params})
        self.assertEqual(400, reserved.status_code)
        self.assertEqual(400, self.client.delete("/api/demonstrators/presets/presets/simulation_parameters.json").status_code)
        after = self.client.delete("/api/demonstrators/presets/presets/my_preset.json").json()
        self.assertNotIn("my_preset.json", after["preset_files"])

    def test_deleting_the_active_preset_falls_back_to_the_default(self) -> None:
        params = self.new_simulation("active")["simulation_parameters"]
        self.client.post("/api/demonstrators/active/presets", json={"filename": "tmp", "parameters": params, "set_active": True})
        after = self.client.delete("/api/demonstrators/active/presets/tmp.json").json()
        self.assertEqual("simulation_parameters.json", after["active_parameters_file"])

    def test_validate_parameters_reports_instead_of_failing(self) -> None:
        params = self.new_simulation("val")["simulation_parameters"]
        ok = self.client.post("/api/demonstrators/validate-parameters", json=params).json()
        self.assertEqual({"valid", "normalized_parameters", "estimates"}, set(ok))
        self.assertTrue(ok["valid"])
        bad = self.client.post("/api/demonstrators/validate-parameters", json={})
        self.assertEqual(200, bad.status_code)
        self.assertEqual({"valid", "error"}, set(bad.json()))

    def test_quantum_estimates_follow_the_strategy(self) -> None:
        params = self.new_simulation("est")["simulation_parameters"]
        pp = params["partitioning_parameters"]
        pp["partitioning_strategy"] = "quantum_annealing"
        pp["common"]["k_target"] = 4
        pp["strategies"]["quantum_annealing"].update(num_starts=2, num_reads=10)
        estimates = self.client.post("/api/demonstrators/validate-parameters", json=params).json()["estimates"]
        self.assertEqual(3, estimates["bipartitions_per_start"])
        self.assertEqual(6, estimates["expected_qpu_submissions"])
        self.assertEqual(60, estimates["expected_qpu_reads"])

    def test_rename_and_delete(self) -> None:
        self.new_simulation("old_name")
        self.new_simulation("taken")
        renamed = self.client.put("/api/demonstrators/old_name/rename", json={"new_name": "new name"})
        self.assertEqual("new_name", renamed.json()["id"])
        self.assertEqual(409, self.client.put("/api/demonstrators/new_name/rename", json={"new_name": "taken"}).status_code)
        self.assertEqual(404, self.client.put("/api/demonstrators/old_name/rename", json={"new_name": "x"}).status_code)
        deleted = self.client.delete("/api/demonstrators/new_name").json()
        self.assertEqual("new_name", deleted["deleted"])
        self.assertNotIn("new_name", deleted["remaining_demonstrators"])
        self.assertEqual(404, self.client.delete("/api/demonstrators/new_name").status_code)

    def test_preview_coarsening_shape(self) -> None:
        params = self.new_simulation("prev")["simulation_parameters"]
        body = self.client.post("/api/demonstrators/prev/preview-coarsening", json=params).json()
        self.assertEqual(
            {"reachable", "final_coarse_nodes", "final_coarse_edges", "accepted_levels_count", "stop_reason", "elapsed_ms", "levels"},
            set(body),
        )
        self.assertEqual(0, body["levels"][0]["level"])
        self.assertEqual(
            {"level", "nodes", "edges", "reduction_ratio", "min_vweight", "max_vweight", "in_target_range", "accepted"},
            set(body["levels"][0]),
        )
        self.assertEqual(400, self.client.post("/api/demonstrators/prev/preview-coarsening", json={}).status_code)
        self.assertEqual(404, self.client.post("/api/demonstrators/missing/preview-coarsening", json=params).status_code)


class LastSimulationTest(unittest.TestCase):
    def test_last_simulation_cannot_be_deleted(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {workspace.ENV_VAR: tmp}):
            from fastapi.testclient import TestClient

            from backend.app import app

            client = TestClient(app)
            client.post("/api/demonstrators", json={"name": "only"})
            response = client.delete("/api/demonstrators/only")
            self.assertEqual(400, response.status_code)
            self.assertTrue((Path(tmp) / "simulations" / "only").is_dir())


if __name__ == "__main__":
    unittest.main()
