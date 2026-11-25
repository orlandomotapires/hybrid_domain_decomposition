"""Tuning service: studies on a temporary workspace with a fake job manager."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hdd.services import tuning
from hdd.services.errors import Conflict, InvalidInput, NotFound
from libs.runtime import workspace
from tests.test_workspace import make_workspace


class FakeJobs:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def list_jobs(self) -> list[dict]:
        return list(self.jobs)

    def start_tuning_study(self, *, study_dir: Path, title: str, demonstrator_id: str | None = None) -> dict:
        job = {"job_id": f"job_{len(self.jobs)}", "job_type": "tuning", "status": "running", "study_dir": workspace.rel(study_dir), "title": title}
        self.jobs.append(job)
        return job


class TuningServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.env = patch.dict(os.environ, {workspace.ENV_VAR: self.tmp.name, "HDD_HISTORY_PATH": str(Path(self.tmp.name) / "h.jsonl")})
        self.env.start()
        self.root = make_workspace(Path(self.tmp.name).resolve())
        self.jobs = FakeJobs()

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_meta_and_defaults(self) -> None:
        meta = tuning.meta()
        self.assertIn("edge_cut", [o["key"] for o in meta["objectives"]])
        defaults = tuning.study_defaults("sim_a")
        self.assertEqual("grid", defaults["matrix_id"])
        self.assertEqual(600, defaults["features"]["matrix"]["n"])
        with self.assertRaises(NotFound):
            tuning.study_defaults("missing")

    def test_auto_select_can_apply(self) -> None:
        result = tuning.auto_select("sim_a", apply=True)
        self.assertTrue(result["feasible"])
        self.assertTrue(result["applied"])
        saved = json.loads((self.root / "simulations/sim_a/data/simulation_parameters.json").read_text())
        self.assertEqual(result["parameters"]["coarsening_parameters"]["coarsen_inferior_limit"],
                         saved["coarsening_parameters"]["coarsen_inferior_limit"])

    def test_study_lifecycle_with_a_job_manager(self) -> None:
        created = tuning.create_study("sim_a", {"objectives": ["edge_cut"], "n_trials": 3}, jobs=self.jobs)
        study_id = created["study"]["id"]
        self.assertEqual("job_0", created["job"]["job_id"])
        self.assertEqual("job_0", created["study"]["running_job_id"])
        self.assertEqual([study_id], [s["id"] for s in tuning.list_studies("sim_a", self.jobs)])
        with self.assertRaises(Conflict):
            tuning.resume_study("sim_a", study_id, self.jobs)
        with self.assertRaises(Conflict):
            tuning.delete_study("sim_a", study_id, self.jobs)
        self.assertTrue(tuning.stop_study("sim_a", study_id)["stopping"])
        self.jobs.jobs[0]["status"] = "completed"
        resumed = tuning.resume_study("sim_a", study_id, self.jobs, n_trials=5)
        self.assertEqual("job_1", resumed["job"]["job_id"])
        self.assertEqual(5, tuning.get_study("sim_a", study_id)["config"]["n_trials"])
        with self.assertRaises(InvalidInput):
            tuning.apply_study("sim_a", study_id)
        self.jobs.jobs[1]["status"] = "completed"
        self.assertEqual({"deleted": study_id}, tuning.delete_study("sim_a", study_id, self.jobs))

    def test_study_ids_are_checked(self) -> None:
        with self.assertRaises(InvalidInput):
            tuning.get_study("sim_a", "../../etc")
        with self.assertRaises(NotFound):
            tuning.get_study("sim_a", "study_missing")
        with self.assertRaises(InvalidInput):
            tuning.create_study("sim_a", {"objectives": ["edge_cut"]}, jobs=None)
        with self.assertRaises(InvalidInput):
            tuning.create_study("sim_a", {"objectives": ["not_an_objective"]}, start=False)


if __name__ == "__main__":
    unittest.main()
