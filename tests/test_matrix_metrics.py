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
            matrix_name="K",
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


if __name__ == "__main__":
    unittest.main()