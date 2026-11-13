"""Deterministic example data for the visual prototype.

The sparse pattern is a real (small) computation so the plots and the numbers
shown beside them agree with each other: a 30 x 20 grid with an 8-neighbour
stencil, split into four quadrants.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

WORKSPACE_LABEL = "Example data (visual prototype)"

GRID_X, GRID_Y, PARTS = 30, 20, 4


@dataclass(frozen=True)
class SampleDecomposition:
    n: int
    k: int
    rows: np.ndarray  # node index of each nonzero's row
    cols: np.ndarray
    part: np.ndarray  # part of each node
    original: np.ndarray  # node -> position in the original ordering
    permuted: np.ndarray  # node -> position after the permutation
    edge_cut: int
    interface_nodes: int
    bandwidth_original: int
    bandwidth_permuted: int

    @property
    def nnz(self) -> int:
        return int(self.rows.size)

    def positions(self, ordering: str) -> np.ndarray:
        return self.original if ordering == "original" else self.permuted

    def is_cut(self) -> np.ndarray:
        """Boolean mask of nonzeros that couple two different parts."""
        return self.part[self.rows] != self.part[self.cols]

    def locality_curve(self, ordering: str, widths_pct: np.ndarray) -> np.ndarray:
        """Share of nonzeros (in %) within each half-bandwidth, given in % of n."""
        position = self.positions(ordering)
        distance = np.abs(position[self.rows] - position[self.cols])
        limits = widths_pct / 100.0 * self.n
        return np.array([(distance <= limit).mean() * 100.0 for limit in limits])


@lru_cache(maxsize=1)
def decomposition() -> SampleDecomposition:
    n = GRID_X * GRID_Y
    x = np.arange(n) % GRID_X
    y = np.arange(n) // GRID_X
    rows, cols = [], []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nx_, ny_ = x + dx, y + dy
            valid = (nx_ >= 0) & (nx_ < GRID_X) & (ny_ >= 0) & (ny_ < GRID_Y)
            rows.append(np.arange(n)[valid])
            cols.append((ny_ * GRID_X + nx_)[valid])
    rows_a, cols_a = np.concatenate(rows), np.concatenate(cols)
    part = (x >= GRID_X // 2).astype(int) + 2 * (y >= GRID_Y // 2).astype(int)

    # "Original" ordering: nodes numbered in scrambled stripes, as a mesher might emit them.
    rng = np.random.default_rng(7)
    order = np.arange(n)
    stripe = 3 * GRID_X
    for start in range(0, n, stripe):
        rng.shuffle(order[start : start + stripe])
    original = np.empty(n, dtype=int)
    original[order] = np.arange(n)

    # Permuted ordering: parts become contiguous, grid order inside each part.
    permuted = np.empty(n, dtype=int)
    permuted[np.lexsort((np.arange(n), part))] = np.arange(n)

    cut = part[rows_a] != part[cols_a]
    return SampleDecomposition(
        n=n,
        k=PARTS,
        rows=rows_a,
        cols=cols_a,
        part=part,
        original=original,
        permuted=permuted,
        edge_cut=int(cut.sum() // 2),
        interface_nodes=int(np.unique(rows_a[cut]).size),
        bandwidth_original=int(np.abs(original[rows_a] - original[cols_a]).max()),
        bandwidth_permuted=int(np.abs(permuted[rows_a] - permuted[cols_a]).max()),
    )


# ------------------------------------------------------------------ project tree
# (kind, label, icon, icon role, children)
Node = tuple[str, str, str, str, list]


def project_tree() -> list[Node]:
    def simulation(name: str, runs: list[tuple[str, str, str]]) -> Node:
        return (
            "simulation",
            name,
            "simulation",
            "default",
            [
                ("input", "Input matrix", "matrix", "default", []),
                ("coarsening", "Coarsening", "coarsening", "default", []),
                ("partitioning", "Partitioning", "partitioning", "default", []),
                ("refinement", "Refinement", "refinement", "default", []),
                ("outputs", "Outputs", "outputs", "default", []),
                (
                    "presets",
                    "Presets",
                    "presets",
                    "default",
                    [
                        ("preset", "simulation_parameters.json (active)", "file", "default", []),
                        ("preset", "annealing_emulated.json", "file", "default", []),
                    ],
                ),
                (
                    "tuning",
                    "Tuning",
                    "tuning",
                    "default",
                    [("study", "study_20261110_101500", "study", "default", [])],
                ),
                (
                    "results",
                    "Results",
                    "results",
                    "default",
                    [("run", label, icon, role, []) for label, icon, role in runs],
                ),
            ],
        )

    return [
        (
            "matrices",
            "Matrices",
            "matrices",
            "default",
            [
                ("matrix", "simpleblade_t14mm_h60", "matrix", "default", []),
                ("matrix", "demo_fem_600", "matrix", "default", []),
            ],
        ),
        (
            "simulations",
            "Simulations",
            "simulations",
            "default",
            [
                simulation(
                    "simulation_01",
                    [
                        ("run_20261112_141502 · METIS", "ok", "ok"),
                        ("run_20261112_101133 · Annealing", "ok", "ok"),
                        ("run_20261111_174820 · QAOA", "error", "error"),
                    ],
                ),
                simulation("simulation_03", [("run_20261104_093355 · METIS", "ok", "ok")]),
            ],
        ),
        (
            "batch",
            "Batch",
            "batch",
            "default",
            [
                ("batch_config", "Configuration", "settings", "default", []),
                (
                    "batch_runs",
                    "Runs",
                    "history",
                    "default",
                    [("batch_run", "batch_20261104_093011", "result", "default", [])],
                ),
            ],
        ),
        ("hardware", "Quantum hardware", "hardware", "default", []),
    ]


# --------------------------------------------------------------- bottom panels
def edge_count() -> int:
    """Undirected edges of the example graph (off-diagonal nonzeros / 2)."""
    d = decomposition()
    return (d.nnz - d.n) // 2


def log_lines() -> list[tuple[str, str, str]]:
    """(time, level, message) lines of an example run, consistent with the example graph."""
    d = decomposition()
    return [
        ("14:15:02", "INFO", "Run started: simulations/simulation_01 (preset simulation_parameters.json)"),
        ("14:15:02", "INFO", f"Loading matrix demo_fem_600 ({d.n} x {d.n}, {d.nnz} nonzeros, symmetric)"),
        ("14:15:02", "DEBUG", "dof_per_node = 1, seed = 42"),
        ("14:15:02", "INFO", f"Stage 1/5  graph build: {d.n} nodes, {edge_count()} edges"),
        ("14:15:02", "INFO", "Stage 2/5  coarsening (heavy-edge matching, sorted)"),
        ("14:15:02", "DEBUG", f"level 1: {d.n} -> 312 nodes"),
        ("14:15:02", "DEBUG", "level 2: 312 -> 163 nodes"),
        ("14:15:02", "DEBUG", "level 3: 163 -> 86 nodes"),
        ("14:15:02", "DEBUG", "level 4: 86 -> 48 nodes"),
        ("14:15:02", "INFO", "Coarsest graph: 48 nodes, 131 edges (target range 32-64)"),
        ("14:15:03", "INFO", "Stage 3/5  partitioning (quantum annealing, emulated, k = 4)"),
        ("14:15:03", "WARNING", "balance_tolerance 0.02 is tight for 48 nodes; allowing +-1 node per part"),
        ("14:15:07", "INFO", "Recursive bisection 1/3: 1000 reads, best energy -183.25"),
        ("14:15:11", "INFO", "Recursive bisection 2/3: 1000 reads, best energy -91.50"),
    ]

JOB_HEADERS = ("Job", "Type", "Target", "State", "Stage", "Progress", "Started", "Duration")
# (id, type, target, state, stage, progress %, started, duration)
JOBS: list[tuple[str, str, str, str, str, int, str, str]] = [
    ("job_0007", "Simulation", "simulation_01", "running", "Partitioning", 54, "14:15:02", "00:00:11"),
    ("job_0006", "Simulation", "simulation_01", "completed", "Completed", 100, "14:15:02", "00:00:01"),
    ("job_0005", "Tuning", "study_20261110_101500", "completed", "20 of 20 trials", 100, "10:15:00", "00:03:42"),
    ("job_0004", "Simulation", "simulation_01", "failed", "Partitioning", 54, "17:48:20", "00:00:06"),
    ("job_0003", "Batch", "batch_20261104_093011", "completed", "18 of 18 cases", 100, "09:30:11", "00:21:37"),
    ("job_0002", "Simulation", "simulation_03", "cancelled", "Coarsening", 36, "09:12:40", "00:00:03"),
]
JOB_STATE = {
    "running": ("Running", "running", "accent"),
    "completed": ("Completed", "ok", "ok"),
    "failed": ("Failed", "error", "error"),
    "cancelled": ("Cancelled", "cancelled", "muted"),
}

PROBLEM_HEADERS = ("Description", "Location")
# (severity, description, location)
PROBLEMS: list[tuple[str, str, str]] = [
    (
        "warning",
        "balance_tolerance = 0.02 may be infeasible with 48 nodes in the coarsest graph",
        "simulation_01 › Partitioning",
    ),
    (
        "error",
        "coarsen_superior_limit (24) must be greater than coarsen_inferior_limit (32)",
        "simulation_03 › Coarsening",
    ),
]

COARSENING_HEADERS = ("Level", "Nodes", "Edges", "Ratio")


def coarsening_levels() -> list[tuple[int, int, int, str]]:
    """(level, nodes, edges, ratio to previous level). Level 0 is the example graph itself."""
    d = decomposition()
    return [
        (0, d.n, edge_count(), "—"),
        (1, 312, 1087, "0.52"),
        (2, 163, 529, "0.52"),
        (3, 86, 251, "0.53"),
        (4, 48, 131, "0.56"),
    ]
