import unittest

import numpy as np
import scipy.sparse as sp

from libs.domain_decomposition import decompose_matrix
from libs.permutation import permute_matrix


def _generic_matrix(n: int = 120, seed: int = 3) -> sp.csr_matrix:
    """A non-FEM sparse matrix: random unsymmetric pattern with some zero diagonal entries."""
    rng = np.random.default_rng(seed)
    rows = rng.integers(0, n, size=6 * n)
    cols = (rows + rng.integers(-8, 9, size=6 * n)) % n
    vals = rng.normal(size=6 * n)
    A = sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    A.setdiag(0.0)
    A.eliminate_zeros()
    return A


PARAMS = dict(
    general_parameters={"dof_per_node": 1, "seed": 0},
    coarsening_parameters={
        "coarsen_inferior_limit": 10,
        "coarsen_superior_limit": 40,
        "max_levels": 20,
        "weight": "weight",
        "strategy": "modified",
        "coarsen_ratio": 1.0,
        "max_node_weight": None,
    },
    partitioning_parameters={
        "partitioning_strategy": "metis_partitioning",
        "common": {"k_target": 4, "balance_tolerance": 2.0},
        "strategies": {"metis_partitioning": {}},
    },
    uncoarsening_parameters={
        "refine_objective": "cut_balance",
        "refine_balance_lambda": 1.0,
        "refine_max_passes_per_level": 5,
        "refine_max_moves_per_pass": 500,
    },
)


class GenericMatrixTest(unittest.TestCase):
    def test_any_square_matrix_is_partitioned_and_permuted(self) -> None:
        A = _generic_matrix()
        permuted, permutation, artifacts = decompose_matrix(A, **PARAMS)

        self.assertEqual(A.shape, permuted.shape)
        self.assertEqual(sorted(permutation.tolist()), list(range(A.shape[0])))
        # P A Pᵀ: entry (i, j) of the permuted matrix is entry (p[i], p[j]) of the original.
        self.assertEqual(0.0, abs(permuted - A[permutation][:, permutation]).max())
        self.assertEqual(A.nnz, permuted.nnz)
        self.assertEqual(4, len(set(artifacts["final_partition"].values())))

    def test_non_square_matrix_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            permute_matrix(sp.csr_matrix((4, 5)), {0: 0, 1: 0, 2: 1, 3: 1})


if __name__ == "__main__":
    unittest.main()
