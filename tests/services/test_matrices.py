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


class RandomMatrixTest(unittest.TestCase):
    """The random generator: exact size, nonzeros and symmetry, with a band reordering recovers."""

    def _generate(self, n=400, nonzeros=4000, symmetry="symmetric", seed=7):
        from hdd.services.matrix_files import random_banded_matrix

        return random_banded_matrix(n, nonzeros, symmetry, seed)

    def test_size_and_nonzeros_are_what_was_asked(self) -> None:
        for symmetry in ("symmetric", "structural", "unsymmetric"):
            A = self._generate(symmetry=symmetry)
            self.assertEqual((400, 400), A.shape)
            self.assertEqual(4000, A.nnz, symmetry)
            self.assertTrue((A.diagonal() > 0).all())

    def test_an_odd_off_diagonal_count_rounds_down_for_symmetric_patterns(self) -> None:
        from hdd.services.matrix_files import achievable_nonzeros

        self.assertEqual(4000, self._generate(nonzeros=4001, symmetry="structural").nnz)
        self.assertEqual(4001, self._generate(nonzeros=4001, symmetry="unsymmetric").nnz)
        self.assertEqual(4000, achievable_nonzeros(400, 4001, "symmetric"))

    def test_each_symmetry_level_holds(self) -> None:
        import numpy as np

        def pattern(M):
            return (M != 0).astype(np.int8)

        sym, struct, unsym = (self._generate(symmetry=s) for s in ("symmetric", "structural", "unsymmetric"))
        self.assertEqual(0, abs(sym - sym.T).max())
        self.assertGreater(np.linalg.eigvalsh(sym.toarray()).min(), 0)  # positive definite
        self.assertEqual(0, abs(pattern(struct) - pattern(struct.T)).max())
        self.assertGreater(abs(struct - struct.T).max(), 0)
        self.assertGreater(abs(pattern(unsym) - pattern(unsym.T)).max(), 0)

    def test_the_band_is_hidden_and_reordering_recovers_it(self) -> None:
        import numpy as np
        from scipy.sparse.csgraph import reverse_cuthill_mckee

        def bandwidth(M):
            coo = M.tocoo()
            return int(np.abs(coo.row - coo.col).max())

        A = self._generate(n=1000, nonzeros=10000)
        order = reverse_cuthill_mckee(A, symmetric_mode=True)
        self.assertGreater(bandwidth(A), 800)
        self.assertLess(bandwidth(A[order][:, order]), 100)

    def test_same_seed_same_matrix(self) -> None:
        self.assertEqual(0, abs(self._generate(seed=3) - self._generate(seed=3)).max())

    def test_full_and_minimal_matrices(self) -> None:
        self.assertEqual(30 * 30, self._generate(n=30, nonzeros=900).nnz)
        self.assertEqual(30, self._generate(n=30, nonzeros=30).nnz)  # diagonal only

    def test_impossible_requests_are_explained(self) -> None:
        from hdd.services.matrix_files import check_random_matrix_request

        self.assertIn("At least", check_random_matrix_request(100, 50, "symmetric"))
        self.assertIn("At most", check_random_matrix_request(10, 101, "symmetric"))
        self.assertIn("between 2", check_random_matrix_request(1, 1, "symmetric"))
        self.assertIn("Unknown symmetry", check_random_matrix_request(10, 20, "skew"))
        self.assertIsNone(check_random_matrix_request(10, 20, "unsymmetric"))

    def test_density_and_nonzeros_convert(self) -> None:
        self.assertEqual(10000, matrices.nonzeros_for_density(1000, 1.0))
        self.assertAlmostEqual(1.0, matrices.density_percent(1000, 10000))


class GenerateIntoLibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = workspace.init(self.tmp.name)
        self.env = patch.dict(os.environ, {workspace.ENV_VAR: str(self.root), "HDD_DISABLE_HISTORY": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_a_generated_matrix_is_in_the_library_and_runnable(self) -> None:
        info = matrices.generate_random_matrix("demo", n=600, nonzeros=6001, symmetry="structural", seed=1)
        self.assertEqual("demo", info["id"])
        self.assertEqual((600, 600, 6000), (info["info"]["rows"], info["info"]["cols"], info["info"]["nnz"]))
        self.assertIn("6,000 nonzeros", info["description"])
        created = simulations.create_simulation(name="on_random", matrix="demo")
        preview = simulations.preview_coarsening("on_random", created["simulation_parameters"])
        self.assertTrue(preview["reachable"], preview["stop_reason"])

    def test_bad_requests_leave_nothing_behind(self) -> None:
        with self.assertRaises(InvalidInput):
            matrices.generate_random_matrix("bad", n=10, nonzeros=5)
        self.assertFalse((self.root / "matrices" / "bad").exists())


if __name__ == "__main__":
    unittest.main()
