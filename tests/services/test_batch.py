"""Batch service: configuration validation, plan and totals, estimates from past runs."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hdd.services import batch
from hdd.services.errors import InvalidInput, NotFound
from libs.runtime import workspace

REPO_CONFIG = Path(__file__).resolve().parents[2] / "batch" / "batch_configuration.json"


def config(**overrides) -> dict:
    base = {
        "matrices": [{"key": "m1"}, {"key": "m2"}],
        "algorithm_presets": [
            {"key": "metis", "partitioning_strategy": "metis_partitioning", "allowed_sizes": ["big", "small"], "strategy_parameters": {}},
            {"key": "qa_hw", "partitioning_strategy": "quantum_annealing", "allowed_sizes": ["big", "small"],
             "strategy_parameters": {"simulated": False, "num_starts": 2, "num_reads": 10}},
            {"key": "qaoa_hw", "partitioning_strategy": "quantum_approximation_optimizer", "allowed_sizes": ["small"],
             "strategy_parameters": {"simulated": False, "num_starts": 1, "num_steps": 3, "num_shots": 7, "qlm_qpu_name": "qat.qpus:Ascella12QPU"}},
        ],
        "coarsening_presets": [
            {"key": "big", "coarsen_inferior_limit": 100, "coarsen_superior_limit": 200},
            {"key": "small", "coarsen_inferior_limit": 8, "coarsen_superior_limit": 12},
        ],
        "common_defaults": {"partitioning_common": {"k_target": 4}},
        "async_remote_case_keys": ["qaoa_hw"],
    }
    base.update(overrides)
    return base


class PlanTest(unittest.TestCase):
    def test_cases_expand_matrices_by_allowed_scales(self) -> None:
        cases = batch.dry_run_cases(config())
        self.assertEqual(2 * (2 + 2 + 1), len(cases))
        self.assertEqual("m1__metis__big", cases[0]["case_key"])
        self.assertTrue(next(c for c in cases if c["algorithm"] == "qaoa_hw")["is_async"])

    def test_saving_checks_every_preset_and_reference(self) -> None:
        from tests.test_tuning import _params

        bad = config(base_parameters=_params())
        bad["algorithm_presets"][1]["strategy_parameters"]["num_reads"] = 0  # invalid
        bad["algorithm_presets"][0]["allowed_sizes"].append("huge")  # no such coarsening preset
        bad["async_remote_case_keys"].append("nope")
        with self.assertRaises(batch.InvalidInput) as raised:
            batch.validate_configuration(bad)
        message = str(raised.exception)
        self.assertIn("'qa_hw'", message)
        self.assertIn("'huge'", message)
        self.assertIn("'nope'", message)
        batch.validate_configuration(config(base_parameters=_params()))  # a good one passes

    def test_a_repeated_matrix_runs_once_as_in_the_batch_runner(self) -> None:
        from libs.batch.run_batch import expand_cases, parse_batch_configuration

        repeated = config(matrices=[{"key": "m1"}, {"key": "m1"}], base_parameters={})
        planned = [c["case_key"] for c in batch.dry_run_cases(repeated)]
        self.assertEqual([c.case_key for c in expand_cases(parse_batch_configuration(repeated))], planned)
        self.assertEqual(len(planned), len(set(planned)))

    def test_qpu_load_and_capacity(self) -> None:
        plan = batch.plan(config())
        by_key = {c["case_key"]: c for c in plan["cases"]}
        qa = by_key["m1__qa_hw__big"]
        self.assertEqual({"submissions": 6, "samples": 60, "unit": "reads"}, qa["qpu"])
        self.assertEqual(175, qa["over_capacity"]["limit"])
        self.assertIsNone(by_key["m1__qa_hw__small"]["over_capacity"])
        qaoa = by_key["m1__qaoa_hw__small"]
        # 1 start x 3 bipartitions x (3 + 1) evaluations, 7 shots each; the QPU name says 12 qubits.
        self.assertEqual({"submissions": 12, "samples": 84, "unit": "shots"}, qaoa["qpu"])
        self.assertIsNone(qaoa["over_capacity"])
        self.assertIsNone(by_key["m1__metis__big"]["qpu"])
        totals = plan["totals"]
        self.assertEqual(2 * (6 + 6 + 12), totals["submissions"])
        self.assertEqual(2 * (60 + 60), totals["reads"])
        self.assertEqual(2 * 84, totals["shots"])
        self.assertEqual(2, totals["over_capacity"])

    def test_estimates_prefer_the_exact_case_and_skip_async_in_the_duration(self) -> None:
        estimates = {
            "by_case": {"m1__metis__big": {"median_seconds": 10.0, "samples": 3}},
            "by_algorithm_scale": {"metis__big": {"median_seconds": 4.0, "samples": 5}, "qaoa_hw__small": {"median_seconds": 99.0, "samples": 1}},
        }
        plan = batch.plan(config(), estimates)
        by_key = {c["case_key"]: c for c in plan["cases"]}
        self.assertEqual("matrix", by_key["m1__metis__big"]["estimate"]["basis"])
        self.assertEqual("algorithm", by_key["m2__metis__big"]["estimate"]["basis"])
        self.assertEqual(10.0 + 4.0, plan["totals"]["seconds"])
        self.assertEqual(4, plan["totals"]["estimated"])
        self.assertEqual(6, plan["totals"]["missing"])

    def test_repository_configuration_is_valid(self) -> None:
        batch.validate_configuration(json.loads(REPO_CONFIG.read_text()))


class ConfigurationTest(unittest.TestCase):
    def test_save_validates_before_writing(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {workspace.ENV_VAR: tmp}):
            with self.assertRaises(NotFound):
                batch.load_configuration()
            with self.assertRaises(InvalidInput):
                batch.save_configuration({"matrices": []})
            broken = config(coarsening_presets=[{"key": "big"}])
            with self.assertRaises(InvalidInput):
                batch.save_configuration(broken)
            self.assertFalse(workspace.batch_config_path().exists())
            saved = batch.save_configuration(config())
            self.assertEqual(10, saved["case_count"])
            self.assertEqual(config(), batch.load_configuration()["configuration"])


class RunsTest(unittest.TestCase):
    def test_runs_and_estimates_from_manifests(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {workspace.ENV_VAR: tmp}):
            bdir = workspace.batch_runs_dir() / "batch_20260101_000000"
            bdir.mkdir(parents=True)
            cases = [
                {"case_key": "m1__metis__big", "status": "completed", "started_at": "2026-01-01T00:00:00", "finished_at": "2026-01-01T00:00:30"},
                {"case_key": "m2__metis__big", "status": "completed", "started_at": "2026-01-01T00:01:00", "finished_at": "2026-01-01T00:01:10"},
                {"case_key": "m1__qa_hw__big", "status": "failed"},
            ]
            (bdir / "batch_manifest.json").write_text(json.dumps({"cases": cases}))
            runs = batch.list_batch_runs()["batch_runs"]
            self.assertEqual([(3, 2, 1)], [(r["total_cases"], r["completed_cases"], r["failed_cases"]) for r in runs])
            estimates = batch.duration_estimates()
            self.assertEqual({"median_seconds": 20.0, "samples": 2}, estimates["by_algorithm_scale"]["metis__big"])
            self.assertEqual(30.0, estimates["by_case"]["m1__metis__big"]["median_seconds"])
            self.assertEqual("batch_20260101_000000", batch.get_batch_run("batch_20260101_000000")["id"])
            with self.assertRaises(InvalidInput):
                batch.get_batch_run("..")
            with self.assertRaises(NotFound):
                batch.get_batch_run("batch_x")


if __name__ == "__main__":
    unittest.main()
