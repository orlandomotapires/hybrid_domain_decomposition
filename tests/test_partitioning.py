"""Coarse partitioning: recursive k-way bipartition, QUBO algebra and the quantum backends (simulated)."""
import unittest

import networkx as nx

from libs.multilevel_scheme.partitioning.utils.recursive import recursive_kway_via_bipartition


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


if __name__ == "__main__":
    unittest.main()
