"""The coarsening preview must predict exactly what a run will do."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import scipy.io
import scipy.sparse as sp

from hdd.services import simulations
from libs.runtime import workspace
from libs.runtime.runtime import run_simulation
from tests.test_tuning import _grid_laplacian, _params
from tests.test_workspace import make_workspace


def weighted_matrix() -> sp.csr_matrix:
    """Grid Laplacian with a strongly varying diagonal, so node weights change the coarsening."""
    A = _grid_laplacian().tolil()
    rng = np.random.default_rng(3)
    A.setdiag(A.diagonal() * rng.uniform(0.2, 20.0, A.shape[0]))
    return A.tocsr()


class PreviewMatchesRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.env = patch.dict(os.environ, {workspace.ENV_VAR: self.tmp.name, "HDD_DISABLE_HISTORY": "1"})
        self.env.start()
        self.root = make_workspace(Path(self.tmp.name).resolve())
        scipy.io.mmwrite(str(self.root / "matrices" / "grid" / "grid.mtx"), weighted_matrix())

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def check(self, **coarsening) -> dict:
        params = _params(**coarsening)
        (self.root / "simulations/sim_a/data/simulation_parameters.json").write_text(json.dumps(params))
        preview = simulations.preview_coarsening("sim_a", params)
        self.assertTrue(preview["reachable"], preview["stop_reason"])
        run_dir = run_simulation("simulations/sim_a")
        artifacts = json.loads((run_dir / "partition_artifacts.json").read_text())
        metrics = json.loads((run_dir / "decomposition_metrics.json").read_text())
        self.assertEqual(len(artifacts["coarse_partition"]), preview["final_coarse_nodes"])
        self.assertEqual(metrics["levels"], preview["accepted_levels_count"])
        return preview

    def test_preview_matches_the_run(self) -> None:
        self.check()
        self.check(coarsen_inferior_limit=20, coarsen_superior_limit=40, strategy="modified")

    def test_unreachable_range_reports_the_rejected_level(self) -> None:
        params = _params(coarsen_inferior_limit=1500, coarsen_superior_limit=2500)
        preview = simulations.preview_coarsening("sim_a", params)
        self.assertFalse(preview["reachable"])
        self.assertTrue(preview["levels"][0]["accepted"])

        params = _params(coarsen_inferior_limit=200, coarsen_superior_limit=210)
        preview = simulations.preview_coarsening("sim_a", params)
        self.assertFalse(preview["reachable"])
        self.assertFalse(preview["levels"][-1]["accepted"])
        self.assertIn("undershoot", preview["stop_reason"])


if __name__ == "__main__":
    unittest.main()
