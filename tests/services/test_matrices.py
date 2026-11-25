"""The matrix library service, called the way the desktop application calls it (no HTTP)."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import scipy.io

from hdd.services import matrices, simulations
from hdd.services.errors import Conflict, InvalidInput, NotFound
from libs.runtime import workspace
from tests.test_tuning import _grid_laplacian


class MatrixLibraryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = workspace.init(self.tmp.name)
        self.env = patch.dict(os.environ, {workspace.ENV_VAR: str(self.root), "HDD_DISABLE_HISTORY": "1"})
        self.env.start()
        self.source = Path(self.tmp.name) / "outside" / "Grid 20x30.mtx"
        self.source.parent.mkdir()
        scipy.io.mmwrite(str(self.source), _grid_laplacian())

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_import_copies_the_file_and_leaves_the_source_alone(self) -> None:
        info = matrices.import_matrix("My grid", self.source)
        self.assertEqual("My_grid", info["id"])
        self.assertEqual(600, info["info"]["rows"])
        self.assertTrue((self.root / "matrices" / "My_grid" / "Grid_20x30.mtx").is_file())
        self.assertTrue(self.source.is_file())
        self.assertEqual(["My_grid"], [m["id"] for m in matrices.list_matrices()["matrices"]])

    def test_import_rejects_bad_input_without_leaving_a_folder(self) -> None:
        with self.assertRaises(InvalidInput):
            matrices.import_matrix("x", self.source.with_suffix(".txt"))
        with self.assertRaises(NotFound):
            matrices.import_matrix("x", self.source.parent / "missing.mtx")
        broken = self.source.parent / "broken.mtx"
        broken.write_text("not a matrix")
        with self.assertRaises(InvalidInput):
            matrices.import_matrix("broken", broken)
        self.assertFalse((self.root / "matrices" / "broken").exists())
        matrices.import_matrix("taken", self.source)
        with self.assertRaises(Conflict):
            matrices.import_matrix("taken", self.source)

    def test_new_simulation_on_an_imported_matrix_is_runnable(self) -> None:
        matrices.import_matrix("grid", self.source)
        created = simulations.create_simulation(name="first", matrix="grid")
        preview = simulations.preview_coarsening("first", created["simulation_parameters"])
        self.assertTrue(preview["reachable"], preview["stop_reason"])
        with self.assertRaises(Conflict):
            matrices.delete_matrix("grid")

    def test_simulation_without_a_library_matrix_keeps_generic_defaults(self) -> None:
        created = simulations.create_simulation(name="empty")
        self.assertEqual("none", created["simulation_config"]["input_matrix"])
        self.assertEqual(
            simulations.DEFAULT_SIMULATION_PARAMETERS["coarsening_parameters"]["coarsen_inferior_limit"],
            created["simulation_parameters"]["coarsening_parameters"]["coarsen_inferior_limit"],
        )


if __name__ == "__main__":
    unittest.main()
