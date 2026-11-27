"""End-to-end pipeline runs: every backend (simulated), block matrices and reproducibility."""

import unittest
from unittest.mock import patch

import numpy as np
import scipy.sparse as sp

import libs.domain_decomposition as dd
from libs.domain_decomposition import decompose_matrix
from tests.test_tuning import _grid_laplacian, _params

QA_BLOCK = {"simulated": True, "num_reads": 20, "num_starts": 2, "qubo_balance_lambda": 2.0,
            "balance_violation_lambda": 5.0}
QAOA_BLOCK = {"simulated": True, "num_starts": 1, "num_steps": 2, "num_shots": 32, "circuit_depth": 1,
              "adam_learning_rate": 0.1, "qubo_balance_lambda": 2.0, "balance_violation_lambda": 5.0}


def _run(A, strategy="metis_partitioning", block=None, *, k=4, dof=1, seed=0, **coarsening):
    p = _params(**coarsening)
    p["general_parameters"].update(dof_per_node=dof, seed=seed)
    pp = p["partitioning_parameters"]
    pp["partitioning_strategy"] = strategy
    pp["common"]["k_target"] = k
    pp["strategies"][strategy] = dict(block or {})
    return decompose_matrix(A, p["general_parameters"], p["coarsening_parameters"], pp, p["uncoarsening_parameters"])


def _assert_valid(test: unittest.TestCase, A, result, k: int) -> None:
    permuted, permutation, artifacts = result
    test.assertEqual(sorted(permutation.tolist()), list(range(A.shape[0])))
    test.assertEqual(0.0, abs(permuted - A[permutation][:, permutation]).max())
    test.assertEqual(k, len(set(artifacts["final_partition"].values())))


@patch.object(dd, "log", lambda *args, **kwargs: None)
class BackendsTest(unittest.TestCase):
    def test_simulated_annealing_partitions_and_permutes(self) -> None:
        A = _grid_laplacian()
        with patch.object(dd, "recursive_kway_anneal", wraps=dd.recursive_kway_anneal) as anneal:
            result = _run(A, "quantum_annealing", QA_BLOCK)
        anneal.assert_called_once()
        _assert_valid(self, A, result, 4)
        self.assertLessEqual(result[2]["decomposition_metrics"]["imbalance"], 0.10 + 1 / 150)

    def test_emulated_qaoa_partitions_and_permutes(self) -> None:
        A = _grid_laplacian(5, 6)
        with patch("libs.multilevel_scheme.partitioning.partitioning.qaoa_bipartition",
                   wraps=dd.recursive_kway_qaoa.__globals__["qaoa_bipartition"]) as bipartition:
            result = _run(A, "quantum_approximation_optimizer", QAOA_BLOCK, k=2,
                          coarsen_inferior_limit=6, coarsen_superior_limit=12)
        self.assertGreaterEqual(bipartition.call_count, 1)
        _assert_valid(self, A, result, 2)

    def test_qaoa_emulation_trains_the_circuit_angles(self) -> None:
        # With plain numpy angles PennyLane's optimizer saw no trainable parameters and every
        # step returned them unchanged, so num_steps had no effect.
        import networkx as nx
        import pennylane as qml

        from libs.multilevel_scheme.partitioning.qaoa.qaoa import qaoa_bipartition

        G = nx.cycle_graph(6)
        nx.set_node_attributes(G, 1.0, "vweight")
        nx.set_edge_attributes(G, 1.0, "weight")
        steps, real_step = [], qml.AdamOptimizer.step

        def spy(optimizer, fn, params, *args, **kwargs):
            new = real_step(optimizer, fn, params, *args, **kwargs)
            steps.append((np.array(params), np.array(new)))
            return new

        with patch.object(qml.AdamOptimizer, "step", spy):
            qaoa_bipartition(G, p=1, steps=3, lr=0.2, shots=16, seed=1)
        self.assertEqual(3, len(steps))
        self.assertTrue(all(not np.allclose(before, after) for before, after in steps))

    def test_qaoa_emulation_needs_a_learning_rate(self) -> None:
        block = {**QAOA_BLOCK}
        block.pop("adam_learning_rate")
        with self.assertRaisesRegex(ValueError, "adam_learning_rate"):
            dd.recursive_kway_qaoa(*_coarse_graph(), k=2, balance_lambda=1.0, balance_tolerance=2.0, num_starts=1,
                                   balance_violation_lambda=1.0, circuit_depth=1, num_steps=1, num_shots=4,
                                   adam_learning_rate=None, simulated=True)

    def test_unknown_strategy_is_a_clear_error(self) -> None:
        p = _params()
        p["partitioning_parameters"]["partitioning_strategy"] = "simulated_bifurcation"
        with self.assertRaisesRegex(ValueError, "Unknown partitioning_strategy"):
            decompose_matrix(_grid_laplacian(), p["general_parameters"], p["coarsening_parameters"],
                             p["partitioning_parameters"], p["uncoarsening_parameters"])

    def test_only_the_weight_attribute_the_pipeline_reads_is_accepted(self) -> None:
        from libs.runtime.utils import validate_and_normalize_simulation_parameters

        p = _params()
        p["coarsening_parameters"]["weight"] = "stiffness"
        with self.assertRaisesRegex(ValueError, "coarsening_parameters.weight"):
            validate_and_normalize_simulation_parameters(p)

    def test_same_seed_gives_the_same_permutation(self) -> None:
        A = _grid_laplacian()
        for strategy, block in (("metis_partitioning", {}), ("quantum_annealing", QA_BLOCK)):
            first = _run(A, strategy, block, seed=5)[1]
            second = _run(A, strategy, block, seed=5)[1]
            self.assertTrue(np.array_equal(first, second), strategy)


def _coarse_graph():
    import networkx as nx

    G = nx.path_graph(4)
    nx.set_node_attributes(G, 1.0, "vweight")
    nx.set_edge_attributes(G, 1.0, "weight")
    return (G,)


@patch.object(dd, "log", lambda *args, **kwargs: None)
class BlockMatrixTest(unittest.TestCase):
    """FEM matrices have several degrees of freedom per mesh node; they must stay together."""

    def test_dof_blocks_stay_contiguous(self) -> None:
        dof = 3
        A = sp.kron(_grid_laplacian(10, 12), np.ones((dof, dof))).tocsr()  # 120 nodes x 3 DOF
        result = _run(A, dof=dof, coarsen_inferior_limit=20, coarsen_superior_limit=60)
        _assert_valid(self, A, result, 4)
        blocks = result[1].reshape(-1, dof)
        self.assertTrue(np.all(blocks[:, 0] % dof == 0))
        self.assertTrue(np.all(blocks - blocks[:, :1] == np.arange(dof)))

    def test_size_must_be_a_multiple_of_the_block_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "not divisible"):
            _run(_grid_laplacian(11, 11), dof=3)


if __name__ == "__main__":
    unittest.main()
