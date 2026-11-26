"""Invariants of the multilevel building blocks: QUBO algebra, matching, coarsening, refinement."""

import itertools
import unittest

import networkx as nx
import numpy as np

from libs.multilevel_scheme.coarsening.coarsening import coarsen_graph, heavy_edge_matching
from libs.multilevel_scheme.partitioning.utils.metrics import cut_value
from libs.multilevel_scheme.partitioning.utils.qubo import (
    build_qubo_from_graph,
    qubo_dense_from_dict,
    qubo_energy,
    qubo_to_ising,
)
from libs.multilevel_scheme.uncoarsening.uncoarsening import refine_kway_boundary_moves

STRATEGIES = ("random", "sorted", "modified", "light")


def _weighted_graph(n: int, seed: int, p: float = 0.5) -> nx.Graph:
    """A connected random graph with positive edge and node weights."""
    rng = np.random.default_rng(seed)
    G = nx.connected_watts_strogatz_graph(n, 4, p, seed=seed) if n > 4 else nx.cycle_graph(n)
    for u, v in G.edges():
        G[u][v]["weight"] = float(rng.uniform(0.5, 3.0))
    for u in G.nodes():
        G.nodes[u]["vweight"] = float(rng.uniform(0.5, 2.0))
    return G


class QuboTest(unittest.TestCase):
    """Brute force over every bitstring of small graphs."""

    def _check(self, G: nx.Graph, balance_lambda: float, target: float | None) -> None:
        nodes = list(G.nodes())
        Qm = qubo_dense_from_dict(build_qubo_from_graph(G, balance_lambda=balance_lambda, target_weight=target), nodes)
        total_w = sum(G.nodes[u]["vweight"] for u in nodes)
        edge_scale = sum(d["weight"] for _, _, d in G.edges(data=True))
        T = (0.5 * total_w if target is None else target) / total_w
        h, J = qubo_to_ising(Qm)

        energies, ising = [], []
        for bits in itertools.product((0, 1), repeat=len(nodes)):
            x = np.array(bits)
            part = dict(zip(nodes, bits))
            balance = sum(G.nodes[u]["vweight"] * b for u, b in part.items()) / total_w
            expected = cut_value(G, part) / edge_scale + balance_lambda * (balance - T) ** 2 - balance_lambda * T ** 2
            self.assertAlmostEqual(expected, qubo_energy(Qm, x), places=9)
            z = 1 - 2 * x  # x = 1 <-> z = -1, as the QAOA decoder reads samples
            energies.append(qubo_energy(Qm, x))
            ising.append(float(h @ z + z @ np.triu(J, 1) @ z))
        # The Ising form equals the QUBO up to one constant offset.
        offsets = np.array(energies) - np.array(ising)
        self.assertLess(offsets.max() - offsets.min(), 1e-9)

    def test_qubo_is_cut_plus_balance_penalty(self) -> None:
        for seed, n in itertools.product(range(3), (4, 6, 8)):
            self._check(_weighted_graph(n, seed), balance_lambda=2.0, target=None)

    def test_custom_target_and_zero_lambda(self) -> None:
        G = _weighted_graph(6, 7)
        self._check(G, balance_lambda=0.0, target=None)
        self._check(G, balance_lambda=1.5, target=0.3 * sum(G.nodes[u]["vweight"] for u in G))

    def test_minimum_is_a_balanced_cut(self) -> None:
        # Two triangles joined by one light edge: the best balanced cut separates them.
        G = nx.Graph()
        G.add_weighted_edges_from([(0, 1, 5), (1, 2, 5), (0, 2, 5), (3, 4, 5), (4, 5, 5), (3, 5, 5), (2, 3, 0.1)])
        nx.set_node_attributes(G, 1.0, "vweight")
        nodes = list(G.nodes())
        Qm = qubo_dense_from_dict(build_qubo_from_graph(G, balance_lambda=4.0), nodes)
        best = min(itertools.product((0, 1), repeat=6), key=lambda b: qubo_energy(Qm, np.array(b)))
        self.assertIn(best, [(0, 0, 0, 1, 1, 1), (1, 1, 1, 0, 0, 0)])


class CoarseningTest(unittest.TestCase):
    def test_matching_is_symmetric_uses_edges_and_respects_the_weight_cap(self) -> None:
        for seed, strategy in itertools.product(range(5), STRATEGIES):
            G = _weighted_graph(60, seed)
            cap = 3.0
            mate = heavy_edge_matching(G, seed=seed, strategy=strategy, max_node_weight=cap)
            self.assertEqual(set(G.nodes()), set(mate))
            for u, v in mate.items():
                self.assertEqual(u, mate[v], f"{strategy}: not symmetric")
                if u != v:
                    self.assertTrue(G.has_edge(u, v))
                    self.assertLessEqual(G.nodes[u]["vweight"] + G.nodes[v]["vweight"], cap + 1e-12)

    def test_unknown_strategy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            heavy_edge_matching(_weighted_graph(10, 0), strategy="nope")

    def test_contraction_keeps_node_weight_and_cross_edge_weight(self) -> None:
        for seed, strategy in itertools.product(range(5), STRATEGIES):
            G = _weighted_graph(80, seed)
            Gc, label = coarsen_graph(G, seed=seed, strategy=strategy)
            self.assertEqual(set(G.nodes()), set(label))
            self.assertLess(Gc.number_of_nodes(), G.number_of_nodes())
            self.assertAlmostEqual(sum(d["vweight"] for _, d in G.nodes(data=True)),
                                   sum(d["vweight"] for _, d in Gc.nodes(data=True)))
            crossing = sum(d["weight"] for u, v, d in G.edges(data=True) if label[u] != label[v])
            self.assertAlmostEqual(crossing, sum(d["weight"] for _, _, d in Gc.edges(data=True)))

    def test_same_seed_same_coarse_graph(self) -> None:
        G = _weighted_graph(80, 3)
        for strategy in STRATEGIES:
            a = coarsen_graph(G, seed=11, strategy=strategy)[1]
            b = coarsen_graph(G, seed=11, strategy=strategy)[1]
            self.assertEqual(a, b, strategy)


class RefinementTest(unittest.TestCase):
    def _start(self, G: nx.Graph, k: int, seed: int) -> dict:
        rng = np.random.default_rng(seed)
        return {u: int(rng.integers(k)) for u in G.nodes()}

    def _weights(self, G, part, k):
        w = np.zeros(k)
        for u, p in part.items():
            w[p] += G.nodes[u]["vweight"]
        return w

    def test_cut_objective_never_increases_the_cut(self) -> None:
        for seed in range(10):
            G = _weighted_graph(100, seed)
            start = self._start(G, 4, seed)
            refined = refine_kway_boundary_moves(G, start, k=4, balance_tolerance=30.0, objective="cut",
                                                 max_passes=10, seed=seed)
            self.assertLessEqual(cut_value(G, refined), cut_value(G, start) + 1e-12)

    def test_parts_within_the_bounds_stay_within(self) -> None:
        for seed, objective in itertools.product(range(10), ("cut", "cut_balance")):
            G = _weighted_graph(100, seed)
            k, tol = 4, 10.0
            start = self._start(G, k, seed)
            w0 = self._weights(G, start, k)
            target = w0.sum() / k
            lo, hi = target * (1 - tol / 100), target * (1 + tol / 100)
            refined = refine_kway_boundary_moves(G, start, k=k, balance_tolerance=tol, objective=objective,
                                                 max_passes=10, seed=seed)
            w1 = self._weights(G, refined, k)
            for p in range(k):
                if lo <= w0[p] <= hi:
                    self.assertTrue(lo - 1e-9 <= w1[p] <= hi + 1e-9, f"part {p} left its bounds ({objective})")
            self.assertEqual(set(G.nodes()), set(refined))


if __name__ == "__main__":
    unittest.main()
