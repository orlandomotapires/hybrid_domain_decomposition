"""Results service on a real run: listing, details, plots and export."""

import io
import json
import os
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from hdd.services import results
from hdd.services.errors import InvalidInput, NotFound
from libs.plotting import partition_plots
from libs.runtime import workspace
from libs.runtime.runtime import run_simulation
from libs.runtime.utils import AVAILABLE_SAVE_OUTPUTS
from tests.test_workspace import make_workspace


class ResultsServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.env = patch.dict(os.environ, {workspace.ENV_VAR: cls.tmp.name, "HDD_DISABLE_HISTORY": "1"})
        cls.env.start()
        cls.addClassCleanup(cls.env.stop)
        cls.root = make_workspace(Path(cls.tmp.name).resolve())
        config_path = cls.root / "simulations" / "sim_a" / "data" / "simulation_config.json"
        config = json.loads(config_path.read_text())
        config["save_output"] = sorted(AVAILABLE_SAVE_OUTPUTS)
        config_path.write_text(json.dumps(config))
        run_dir = run_simulation("simulations/sim_a")
        cls.result_dir = workspace.rel(run_dir)

    def test_list_runs_summarises_each_run(self) -> None:
        runs = results.list_runs("sim_a")["runs"]
        self.assertEqual(1, len(runs))
        run = runs[0]
        self.assertEqual(self.result_dir, run["result_dir"])
        self.assertEqual("metis_partitioning", run["partitioning_strategy"])
        self.assertTrue(run["can_render_plots"])
        self.assertEqual(600, run["kpi_summary"]["n"])
        with self.assertRaises(NotFound):
            results.list_runs("missing")
        with self.assertRaises(InvalidInput):
            results.list_runs("../escape")

    def test_run_detail_has_kpis_and_curves(self) -> None:
        detail = results.get_run_detail(self.result_dir)
        self.assertGreater(len(detail["curves"]), 50)
        first, last = detail["curves"][0], detail["curves"][-1]
        self.assertLessEqual(first["permuted"], last["permuted"])
        self.assertIn("run_log", detail["artifacts"])
        self.assertTrue(detail["kpi_summary"]["permutation_check"])

    def test_paths_cannot_leave_the_workspace(self) -> None:
        with self.assertRaises(InvalidInput):
            results.get_run_detail("../../etc")
        with self.assertRaises(NotFound):
            results.get_run_detail("simulations/sim_a/results/run_missing")

    def test_plot_data_matches_the_saved_matrices(self) -> None:
        case = partition_plots.load_case(self.result_dir)
        nnz = case["matrix_original"].nnz
        for spec in results.AVAILABLE_CASE_PLOTS:
            data = results.plot_data(self.result_dir, spec["id"])
            self.assertEqual(data.labels.shape[0], data.n)
            self.assertEqual(data.rows.shape, data.cols.shape)
            self.assertLessEqual(len(data.parts), 4)
        permuted = results.plot_data(self.result_dir, "permuted_matrix_partitioned")
        self.assertEqual(nnz, permuted.rows.size)
        # After the permutation each part occupies one contiguous block of rows.
        changes = np.count_nonzero(np.diff(permuted.labels))
        self.assertEqual(len(permuted.parts) - 1, changes)

    def test_png_is_rendered_once_and_cached(self) -> None:
        png = results.render_plot_png(self.result_dir, "original_matrix_partitioned")
        self.assertEqual(b"\x89PNG", png.read_bytes()[:4])
        stamp = png.stat().st_mtime_ns
        self.assertEqual(stamp, results.render_plot_png(self.result_dir, "original_matrix_partitioned").stat().st_mtime_ns)
        with self.assertRaises(InvalidInput):
            results.render_plot_png(self.result_dir, "nope")

    def test_bundle_contains_files_and_cached_plots(self) -> None:
        results.render_plot_png(self.result_dir, "permuted_matrix_partitioned")
        buffer = io.BytesIO()
        results.export_run_bundle(self.result_dir, buffer)
        names = zipfile.ZipFile(buffer).namelist()
        self.assertIn("run_inputs.json", names)
        self.assertIn("plots/permuted_matrix_partitioned.png", names)

    def test_renderer_does_not_use_pyplot(self) -> None:
        import subprocess
        import sys

        code = (
            "import sys; from libs.plotting import partition_plots; from hdd.services import results; "
            "print('matplotlib.pyplot' in sys.modules)"
        )
        out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "PYTHONPATH": "src"}, capture_output=True, text=True, check=True)
        self.assertEqual("False", out.stdout.strip())


class BatchAnalysisTest(unittest.TestCase):
    def test_rows_and_curves_per_scale(self) -> None:
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {workspace.ENV_VAR: tmp}):
            batch = Path(tmp) / "batch" / "runs" / "batch_1"
            batch.mkdir(parents=True)
            row = {"geometry": "m1", "case_key": "m1__metis__big", "status": "completed", "algorithm": "metis", "coarsening_size": "big",
                   "frac_0_1pct_original": 1.0, "frac_0_1pct_permuted": 5.0}
            other = dict(row, geometry="m2", case_key="m2__metis__small", coarsening_size="small")
            (batch / "batch_summary.json").write_text(json.dumps({"rows": [row, other]}))
            analysis = results.batch_analysis("batch_1", "m1")
            self.assertEqual(["m1", "m2"], analysis["available_demonstrators"])
            self.assertEqual(["big"], [c["coarsening_size"] for c in analysis["comparison_curves"]])
            self.assertEqual(5.0, analysis["comparison_curves"][0]["points"][1]["metis"])
            self.assertEqual("m1", results.batch_analysis("batch_1")["demonstrator"])
            with self.assertRaises(NotFound):
                results.batch_analysis("batch_2")


if __name__ == "__main__":
    unittest.main()
