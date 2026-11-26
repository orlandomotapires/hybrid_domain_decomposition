import unittest

import numpy as np
from scipy import sparse

from libs.profiling.matrix_metrics import collect_metrics


class MatrixMetricsTest(unittest.TestCase):
    def test_collect_metrics_uses_percentage_band_keys_without_band200_duplicates(self) -> None:
        matrix = sparse.csr_matrix(
            np.array(
                [
                    [1.0, 0.0, 0.0, 2.0],
                    [0.0, 3.0, 0.0, 0.0],
                    [0.0, 0.0, 4.0, 0.0],
                    [2.0, 0.0, 0.0, 5.0],
                ]
            )
        )
        permutation = np.arange(matrix.shape[0], dtype=int)

        metrics = collect_metrics(
            matrix_name="A",
            method_name="identity",
            original=matrix,
            permuted=matrix,
            permutation=permutation,
            perm_check_samples=16,
            perm_check_seed=0,
            perm_check_tol=0.0,
        )

        structural = metrics["structural_metrics"]
        self.assertEqual({"original", "permuted"}, set(structural.keys()))
        for key in (
            "frac_within_|i-j|<=0.1%_of_n",
            "frac_within_|i-j|<=0.4%_of_n",
            "frac_within_|i-j|<=0.7%_of_n",
            "frac_within_|i-j|<=1.0%_of_n",
        ):
            self.assertIn(key, structural["original"])
            self.assertIn(key, structural["permuted"])


class PermutationCheckTest(unittest.TestCase):
    def _check(self, original, permuted, permutation):
        from libs.profiling.matrix_metrics import _check_permutation_matrix_relation

        return _check_permutation_matrix_relation("A", original, permuted, permutation)

    def test_a_correct_permutation_passes(self) -> None:
        A = sparse.random(2000, 2000, density=1e-3, random_state=1, format="csr")
        p = np.random.default_rng(1).permutation(2000)
        self.assertEqual((0, 0.0), self._check(A, A[p][:, p], p))

    def test_a_single_wrong_entry_is_found_in_a_large_sparse_matrix(self) -> None:
        # Uniform sampling over n^2 positions almost never hit the few nonzeros of such a matrix.
        A = sparse.random(2000, 2000, density=1e-3, random_state=2, format="csr")
        p = np.random.default_rng(2).permutation(2000)
        wrong = A[p][:, p].tolil()
        i, j = wrong.nonzero()[0][0], wrong.nonzero()[1][0]
        wrong[i, j] += 1.0
        mismatches, max_err = self._check(A, wrong.tocsr(), p)
        self.assertEqual(1, mismatches)
        self.assertAlmostEqual(1.0, max_err)

    def test_band_fractions_of_a_small_matrix(self) -> None:
        from libs.profiling.matrix_metrics import _sparsity_metrics

        A = sparse.csr_matrix(np.array([[1.0, 0, 0, 2.0], [0, 3.0, 0, 0], [0, 0, 4.0, 0], [2.0, 0, 0, 5.0]]))
        m = _sparsity_metrics(A, band=1)
        self.assertEqual(3, m["bandwidth"])
        self.assertEqual(4, m["nnz_within_|i-j|<=1"])  # the diagonal; the two corner entries are 3 away
        self.assertAlmostEqual(4 / 6, m["frac_within_|i-j|<=1"])


if __name__ == "__main__":
    unittest.main()