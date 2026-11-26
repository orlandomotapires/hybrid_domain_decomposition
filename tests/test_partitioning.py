"""Coarse partitioning: recursive k-way bipartition, QUBO algebra and the quantum backends (simulated)."""
import os
import unittest
from unittest.mock import patch

import networkx as nx

from libs.multilevel_scheme.partitioning.capacity import local_capacity_error
from libs.multilevel_scheme.partitioning.partitioning import metis_ufactor
from libs.multilevel_scheme.partitioning.utils.metrics import (
    balance_violation,
    legacy_tolerance_percent,
    tolerance_ratio,
)
from libs.multilevel_scheme.partitioning.utils.recursive import recursive_kway_via_bipartition


class BalanceToleranceTest(unittest.TestCase):
    def test_tolerance_is_always_a_percentage(self) -> None:
        # No jump at 1.0: the old rule read 1.0 as 100% and 1.01 as 1.01%.
        for percent, ratio in [(0, 0.0), (0.5, 0.005), (1.0, 0.01), (1.01, 0.0101), (2.0, 0.02), (100, 1.0)]:
            self.assertAlmostEqual(ratio, tolerance_ratio(percent))
        self.assertEqual(0.0, tolerance_ratio(-3))

    def test_legacy_values_keep_their_old_meaning(self) -> None:
        self.assertAlmostEqual(10.0, legacy_tolerance_percent(0.1))
        self.assertAlmostEqual(100.0, legacy_tolerance_percent(1.0))
        self.assertAlmostEqual(2.0, legacy_tolerance_percent(2.0))

    def test_metis_ufactor_follows_tolerance(self) -> None:
        self.assertEqual(20, metis_ufactor(2.0))
        self.assertEqual(1, metis_ufactor(0.0))

    def test_violation_uses_percent(self) -> None:
        G = nx.empty_graph(2)
        nx.set_node_attributes(G, {0: 1.015, 1: 0.985}, "vweight")  # ±1.5% around the ideal 1.0
        part = {0: 0, 1: 1}
        self.assertAlmostEqual(0.0, balance_violation(G, part, 2, balance_tolerance=2.0))
        self.assertGreater(balance_violation(G, part, 2, balance_tolerance=1.0), 0.0)


def _isolate_heaviest(G, target_weight, seed, simulated=True):
    """Stub bipartitioner: the heaviest node alone on side 0, every other node on side 1."""
    heaviest = max(G.nodes(), key=lambda n: G.nodes[n].get("vweight", 1.0))
    return {n: 0 if n == heaviest else 1 for n in G.nodes()}


class RecursiveKwayTest(unittest.TestCase):
    def test_single_node_heaviest_block_is_not_split(self) -> None:
        # After the first split the heaviest block is the lone heavy node; splitting it again used to
        # raise "Bipartition fallback failed". The next split must go to the multi-node block instead.
        G = nx.path_graph(4)
        nx.set_node_attributes(G, {0: 10.0, 1: 1.0, 2: 1.0, 3: 1.0}, "vweight")
        nx.set_edge_attributes(G, 1.0, "weight")

        part = recursive_kway_via_bipartition(
            G, 4, weight="vweight", balance_tolerance=2.0, seed=0, num_starts=1,
            balance_violation_lambda=1.0, bipartition=_isolate_heaviest, simulated=True,
        )

        self.assertEqual(set(G.nodes()), set(part))
        self.assertEqual({0, 1, 2, 3}, set(part.values()))

    def test_k_equal_to_node_count_gives_singletons(self) -> None:
        G = nx.cycle_graph(6)
        nx.set_node_attributes(G, {n: float(10 ** n) for n in G.nodes()}, "vweight")
        nx.set_edge_attributes(G, 1.0, "weight")

        part = recursive_kway_via_bipartition(
            G, 6, weight="vweight", balance_tolerance=2.0, seed=1, num_starts=2,
            balance_violation_lambda=1.0, bipartition=_isolate_heaviest, simulated=True,
        )

        self.assertEqual(6, len(set(part.values())))


class MetisWeightsTest(unittest.TestCase):
    def test_ratios_survive_a_wide_weight_range(self) -> None:
        from libs.multilevel_scheme.partitioning.partitioning import _weights_to_metis_ints

        # FEM diagonals can span many orders of magnitude; the heavy values must stay distinct.
        weights = _weights_to_metis_ints([1e-9, 1.0, 2.0, 100.0, 200.0])
        self.assertEqual(1, weights[0])
        self.assertLess(weights[1], weights[2])
        self.assertLess(weights[3], weights[4])
        self.assertAlmostEqual(2.0, weights[4] / weights[3], places=3)

    def test_totals_stay_within_32_bit_integers(self) -> None:
        from libs.multilevel_scheme.partitioning.partitioning import _weights_to_metis_ints

        self.assertLess(sum(_weights_to_metis_ints([5.0] * 5000)), 2**31)


class MatrixValuesTest(unittest.TestCase):
    def test_nan_and_inf_entries_are_rejected_on_load(self) -> None:
        import tempfile
        from pathlib import Path

        import scipy.io
        import scipy.sparse as sp

        from libs.runtime.utils import load_mtx

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.mtx"
            A = sp.identity(3, format="csr")
            A.data[1] = float("nan")
            scipy.io.mmwrite(str(path), A)
            with self.assertRaisesRegex(ValueError, "NaN or infinite"):
                load_mtx(path)


class LocalCapacityTest(unittest.TestCase):
    def _params(self, strategy: str, **block):
        from tests.test_tuning import _params

        params = _params()
        params["partitioning_parameters"]["partitioning_strategy"] = strategy
        params["partitioning_parameters"]["strategies"][strategy] = {"simulated": True, **block}
        return params

    def test_oversized_coarse_graph_fails_before_qaoa_emulation(self) -> None:
        from libs.domain_decomposition import decompose_matrix
        from tests.test_tuning import _grid_laplacian

        p = self._params("quantum_approximation_optimizer", circuit_depth=1, num_steps=1, num_shots=1,
                         num_starts=1, qubo_balance_lambda=1.0, balance_violation_lambda=1.0, adam_learning_rate=0.1)
        with patch("libs.domain_decomposition.recursive_kway_qaoa") as qaoa:
            with self.assertRaisesRegex(ValueError, "QAOA statevector emulation limit of 18"):
                decompose_matrix(_grid_laplacian(), p["general_parameters"], p["coarsening_parameters"],
                                 p["partitioning_parameters"], p["uncoarsening_parameters"])
        qaoa.assert_not_called()

    def test_simulated_annealing_limit_is_configurable(self) -> None:
        pp = self._params("quantum_annealing")["partitioning_parameters"]
        self.assertIsNone(local_capacity_error(pp, 2500))  # the thesis' "Big" scale
        self.assertIn("HDD_SIMULATED_QA_NODE_LIMIT", local_capacity_error(pp, 3001))
        with patch.dict(os.environ, {"HDD_SIMULATED_QA_NODE_LIMIT": "5000"}):
            self.assertIsNone(local_capacity_error(pp, 4000))

    def test_remote_backends_are_not_checked_here(self) -> None:
        pp = self._params("quantum_annealing")["partitioning_parameters"]
        pp["strategies"]["quantum_annealing"]["simulated"] = False
        self.assertIsNone(local_capacity_error(pp, 10_000))


if __name__ == "__main__":
    unittest.main()
