"""Job manager with scripted fake child processes, plus one real METIS run."""

import json
import os
import sys
import textwrap
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hdd.services.jobs import JobManager
from hdd.services.jobs.manager import INTERRUPTED_MESSAGE, MAX_LOG_ENTRIES
from libs.runtime import workspace
from tests.test_workspace import make_workspace

SCRIPTS = {
    # A single run that walks through the pipeline stages and announces its result folder.
    "single_ok": """
        import sys, time
        for line in ["[10:00:00 INFO] Converting matrix to graph",
                     "[10:00:00 INFO] Graph G with 600 nodes and 1150 edges created from the matrix",
                     "[10:00:00 INFO] Coarsening Heavy Edge Matching",
                     "[10:00:00 VERBOSE] Coarse graph has 86 nodes and 213 edges with 4 levels",
                     "[10:00:00 INFO] Multilevel Partitioning Scheme using METIS",
                     "[10:00:00 VERBOSE] Partitioning on coarse graph produced 4 parts",
                     "[10:00:00 INFO] Uncoarsening Kernighan-Lin",
                     "[10:00:00 INFO] Permuting matrix",
                     "[10:00:00 VERBOSE] Results saved in simulations/sim_a/results/run_fake"]:
            print(line, flush=True)
    """,
    "single_fail": """
        print("[10:00:00 INFO] Converting matrix to graph", flush=True)
        print("[10:00:00 ERROR] Simulation failed: boom", flush=True)
        raise SystemExit(1)
    """,
    "sleep": """
        import time
        print("[10:00:00 INFO] Coarsening Heavy Edge Matching", flush=True)
        time.sleep(60)
    """,
    "ignore_term": """
        import signal, time
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        print("[10:00:00 INFO] ignoring SIGTERM", flush=True)
        time.sleep(60)
    """,
    "batch": """
        print("Prepared 2 batch cases.", flush=True)
        print("[1/2] Running m__metis__big", flush=True)
        print("  Result: simulations/x", flush=True)
        print("[2/2] Running m__metis__small", flush=True)
        print("  FAILED: ValueError: nope", flush=True)
    """,
    "tune": """
        print("[tuning] study study_x: 2 trials", flush=True)
        print("[tuning] trial 1/2 status=ok edge_cut=1", flush=True)
        print("[tuning] trial 2/2 status=infeasible", flush=True)
    """,
    "flood": """
        for i in range(%d):
            print(f"[10:00:00 INFO] line {i}")
    """ % (MAX_LOG_ENTRIES + 25),
}


class FakeCommands:
    """Maps a job kind to one of the scripts above."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.next: dict[str, str] = {}
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, kind: str, args: list[str]) -> list[str]:
        self.calls.append((kind, args))
        name = self.next.get(kind, kind)
        path = self.directory / f"{name}.py"
        path.write_text(textwrap.dedent(SCRIPTS[name]))
        return [sys.executable, "-u", str(path)]


def wait_for(predicate, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not reached in time")


class JobManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = make_workspace(Path(self.tmp.name).resolve() / "ws")
        self.env = patch.dict(os.environ, {workspace.ENV_VAR: str(self.root), "HDD_DISABLE_HISTORY": "1"})
        self.env.start()
        self.fake = FakeCommands(Path(self.tmp.name))
        self.manager = JobManager(self.root, command_factory=self.fake, kill_grace_sec=0.5)
        self.events: list[tuple[str, str]] = []
        self.manager.subscribe(lambda event, job_id: self.events.append((event, job_id)))

    def tearDown(self) -> None:
        self.manager.cancel_all()
        self.env.stop()
        self.tmp.cleanup()

    def finished(self, job_id: str):
        return lambda: self.manager.get_job(job_id)["status"] != "running"

    def test_single_run_reports_stages_telemetry_and_result(self) -> None:
        self.fake.next["single"] = "single_ok"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(self.finished(job_id))
        job = self.manager.get_job(job_id)
        self.assertEqual("completed", job["status"])
        self.assertEqual(100, job["stage_progress"])
        self.assertEqual("permutation", job["current_stage"])
        self.assertEqual({"initial_nodes": 600, "initial_edges": 1150, "coarse_nodes": 86, "coarse_edges": 213,
                          "coarsening_levels": 4, "coarse_parts": 4}, job["telemetry"])
        self.assertEqual("simulations/sim_a/results/run_fake", job["result_dir"])
        self.assertEqual("metis_partitioning", job["partitioning_strategy"])
        self.assertEqual(("single", ["simulations/sim_a", "--payload"]), (self.fake.calls[0][0], self.fake.calls[0][1][:2]))

    def test_incremental_log_reads(self) -> None:
        self.fake.next["single"] = "single_ok"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(self.finished(job_id))
        full = self.manager.get_job(job_id)
        self.assertEqual(9, full["log_count"])
        self.assertEqual(full["logs"][5:], self.manager.get_job(job_id, log_offset=5)["logs"])
        self.assertEqual([], self.manager.get_job(job_id, log_offset=9)["logs"])

    def test_failure_keeps_the_first_error(self) -> None:
        self.fake.next["single"] = "single_fail"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(self.finished(job_id))
        job = self.manager.get_job(job_id)
        self.assertEqual(("failed", 1), (job["status"], job["exit_code"]))
        self.assertEqual("Simulation failed: boom", job["error_message"])

    def test_listeners_see_added_changes_and_finished_in_order(self) -> None:
        self.fake.next["single"] = "single_ok"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(self.finished(job_id))
        wait_for(lambda: ("finished", job_id) in self.events)
        kinds = [event for event, jid in self.events if jid == job_id]
        self.assertEqual("added", kinds[0])
        self.assertEqual("finished", kinds[-1])
        self.assertEqual(9, kinds.count("changed"))

    def test_a_failing_listener_does_not_break_the_job(self) -> None:
        self.manager.subscribe(lambda *_: 1 / 0)
        self.fake.next["single"] = "single_ok"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(self.finished(job_id))
        self.assertEqual("completed", self.manager.get_job(job_id)["status"])

    def test_unsubscribe(self) -> None:
        seen = []
        unsubscribe = self.manager.subscribe(lambda e, j: seen.append(e))
        unsubscribe()
        self.fake.next["single"] = "single_ok"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(self.finished(job_id))
        self.assertEqual([], seen)

    def test_cancel_terminates_the_process_group(self) -> None:
        self.fake.next["single"] = "sleep"
        job = self.manager.start_single_simulation("simulations/sim_a")
        wait_for(lambda: self.manager.get_job(job["job_id"])["log_count"] >= 1)
        cancelled = self.manager.cancel_job(job["job_id"])
        self.assertEqual("cancelled", cancelled["status"])
        self.assertEqual("Job cancelled by user.", cancelled["logs"][-1]["message"])
        wait_for(lambda: self.manager.get_job(job["job_id"])["pid"] is None)
        self.assertEqual("cancelled", self.manager.get_job(job["job_id"])["status"])

    def test_cancel_escalates_to_sigkill(self) -> None:
        self.fake.next["single"] = "ignore_term"
        job = self.manager.start_single_simulation("simulations/sim_a")
        wait_for(lambda: self.manager.get_job(job["job_id"])["log_count"] >= 1)
        self.manager.cancel_job(job["job_id"])
        wait_for(lambda: self.manager.get_job(job["job_id"])["pid"] is None, timeout=5)
        self.assertEqual(-9, self.manager.get_job(job["job_id"])["exit_code"])

    def test_batch_progress_and_log_file(self) -> None:
        job = self.manager.start_batch_study()
        wait_for(self.finished(job["job_id"]))
        done = self.manager.get_job(job["job_id"])
        self.assertEqual({"batch_total": 2, "batch_done": 2, "batch_failed": 1, "batch_index": 2, "batch_case": "m__metis__small"}, done["telemetry"])
        log = (self.root / done["batch_dir"] / "batch.log").read_text()
        self.assertIn("FAILED: ValueError: nope", log)

    def test_tuning_progress(self) -> None:
        job = self.manager.start_tuning_study(study_dir=self.root / "simulations/sim_a/tuning/study_x", title="t")
        wait_for(self.finished(job["job_id"]))
        done = self.manager.get_job(job["job_id"])
        self.assertEqual({"tuning_total": 2, "tuning_done": 2, "tuning_ok": 1, "tuning_infeasible": 1}, done["telemetry"])
        self.assertEqual("simulations/sim_a/tuning/study_x", done["study_dir"])

    def test_logs_are_bounded_but_offsets_stay_valid(self) -> None:
        self.fake.next["single"] = "flood"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(self.finished(job_id), timeout=60)
        job = self.manager.get_job(job_id, log_offset=MAX_LOG_ENTRIES + 20)
        self.assertEqual(MAX_LOG_ENTRIES + 25, job["log_count"])
        self.assertEqual([f"line {i}" for i in range(MAX_LOG_ENTRIES + 20, MAX_LOG_ENTRIES + 25)], [e["message"] for e in job["logs"]])

    def test_records_survive_a_restart(self) -> None:
        self.fake.next["single"] = "single_ok"
        done_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        batch_id = self.manager.start_batch_study()["job_id"]
        wait_for(self.finished(done_id))
        wait_for(self.finished(batch_id))
        self.fake.next["single"] = "sleep"
        running_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        wait_for(lambda: self.manager.get_job(running_id)["log_count"] >= 1)

        reopened = JobManager(self.root, command_factory=self.fake)
        ids = {j["job_id"] for j in reopened.list_jobs()}
        self.assertTrue({done_id, batch_id, running_id} <= ids)
        restored = reopened.get_job(done_id)
        self.assertEqual("completed", restored["status"])
        self.assertEqual(9, restored["log_count"])
        self.assertEqual(86, restored["telemetry"]["coarse_nodes"])
        interrupted = reopened.get_job(running_id)
        self.assertEqual("failed", interrupted["status"])
        self.assertEqual(INTERRUPTED_MESSAGE, interrupted["error_message"])
        self.assertEqual(INTERRUPTED_MESSAGE, interrupted["logs"][-1]["message"])
        self.assertTrue(reopened.delete_job(done_id))
        self.assertFalse((self.root / ".hdd" / "jobs" / f"{done_id}.json").exists())

    def test_running_jobs_cannot_be_deleted(self) -> None:
        self.fake.next["single"] = "sleep"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        self.assertFalse(self.manager.delete_job(job_id))
        self.manager.cancel_job(job_id)
        wait_for(lambda: self.manager.get_job(job_id)["pid"] is None)
        self.assertTrue(self.manager.delete_job(job_id))
        self.assertIn(("removed", job_id), self.events)

    def test_concurrent_readers_while_a_job_writes(self) -> None:
        self.fake.next["single"] = "flood"
        job_id = self.manager.start_single_simulation("simulations/sim_a")["job_id"]
        errors = []

        def reader() -> None:
            offset = 0
            try:
                while self.manager.get_job(job_id)["status"] == "running" or offset < self.manager.get_job(job_id)["log_count"]:
                    snap = self.manager.get_job(job_id, log_offset=offset)
                    offset = snap["log_count"]
                    self.manager.list_jobs()
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        self.assertEqual([], errors)


class RealJobTest(unittest.TestCase):
    def test_metis_run_end_to_end_through_the_job_entry_point(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"HDD_DISABLE_HISTORY": "1"}):
            root = make_workspace(Path(tmp).resolve())
            manager = JobManager(root)
            job_id = manager.start_single_simulation("simulations/sim_a")["job_id"]
            wait_for(lambda: manager.get_job(job_id)["status"] != "running", timeout=120)
            job = manager.get_job(job_id)
            self.assertEqual("completed", job["status"], [e["message"] for e in job["logs"] if e["level"] == "ERROR"])
            self.assertTrue((root / job["result_dir"] / "permutation.txt").is_file())
            self.assertEqual(600, job["telemetry"]["initial_nodes"])
            record = json.loads((root / ".hdd" / "jobs" / f"{job_id}.json").read_text())
            self.assertEqual("completed", record["status"])


if __name__ == "__main__":
    unittest.main()
