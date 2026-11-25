"""Partition-coloured sparsity plots of a finished run.

Split in two steps so every front end can share the first one:

1. :func:`case_plot_data` turns a run's artifacts into :class:`PartitionPlotData`
   (nonzero coordinates and the part of each row);
2. :func:`draw_partition_matrix` draws that data onto a matplotlib ``Figure``
   the caller owns. Nothing here uses ``pyplot``, so figures can be built off the
   GUI thread and embedded or saved without touching global matplotlib state.

The five canonical plots are all sparsity patterns; the "graph" plots show the
graph's adjacency matrix.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.colors import hsv_to_rgb, to_hex

from libs.permutation import _create_permutation_from_partition, _permute_sparse_matrix
from libs.runtime import workspace
from libs.runtime.utils import _as_csr_matrix, graph_to_sparse_matrix, load_mtx, matrix_to_graph

#: Canonical plots of a run, in display order.
CASE_PLOTS: list[dict[str, Any]] = [
    {"id": "original_matrix_partitioned", "label": "Original Matrix (Partition Colored)", "kind": "matrix", "show_y_axis": True},
    {"id": "permuted_matrix_partitioned", "label": "Permuted Matrix (Partition Colored)", "kind": "matrix", "show_y_axis": False},
    {"id": "original_graph_partitioned", "label": "Original Graph", "kind": "graph", "show_y_axis": True},
    {"id": "coarsened_graph_partitioned", "label": "Coarsened Graph", "kind": "graph", "show_y_axis": False},
    {"id": "uncoarsened_graph_partitioned", "label": "Uncoarsened Graph", "kind": "graph", "show_y_axis": False},
]

_SPECS: dict[str, dict[str, Any]] = {
    "original_matrix_partitioned": {"kind": "matrix", "matrix_key": "matrix_original", "partition_key": "final_partition", "title": "Original matrix"},
    "permuted_matrix_partitioned": {
        "kind": "matrix", "matrix_key": "matrix_permuted", "partition_key": "final_partition", "title": "Permuted matrix", "use_permutation": True,
    },
    "original_graph_partitioned": {"kind": "graph", "matrix_key": "matrix_original", "partition_key": "final_partition", "title": "Original graph"},
    "coarsened_graph_partitioned": {
        "kind": "graph", "matrix_key": "coarsened_graph_matrix", "partition_key": "coarse_partition", "title": "Coarsened graph",
        "margin_mode": "coarsened_right_margin", "dof_per_node": 1,
    },
    "uncoarsened_graph_partitioned": {
        "kind": "graph", "matrix_key": "matrix_original", "partition_key": "final_partition", "title": "Uncoarsened graph",
        "margin_mode": "uncoarsened_match", "use_partition_order": True,
    },
}

#: Files a run must have for its plots to be drawn.
REQUIRED_ARTIFACTS = ("partition_artifacts.json", "coarsened_graph.mtx", "matrix_permuted.mtx", "permutation.txt", "run_inputs.json")


@dataclass(frozen=True)
class PartitionPlotData:
    n: int
    rows: np.ndarray  # row index of each nonzero
    cols: np.ndarray
    labels: np.ndarray  # part of each row (length n)
    title: str
    margin_mode: str | None = None

    @property
    def parts(self) -> list[int]:
        return sorted(int(p) for p in np.unique(self.labels))


# ----------------------------------------------------------------- loading
def load_partition_artifacts(result_dir: Path) -> dict[str, dict[int, int]]:
    raw = json.loads((result_dir / "partition_artifacts.json").read_text())
    return {key: {int(node): int(part) for node, part in raw[key].items()} for key in ("coarse_partition", "final_partition")}


def can_plot(result_dir: Path) -> bool:
    return all((result_dir / name).exists() for name in REQUIRED_ARTIFACTS)


def load_case(result_dir: str | Path) -> dict[str, Any]:
    """Load a run's matrices, permutation and partitions. ``result_dir`` may be workspace-relative."""
    result_dir = Path(result_dir)
    if not result_dir.is_absolute():
        result_dir = workspace.root() / result_dir
    inputs = json.loads((result_dir / "run_inputs.json").read_text())
    return {
        "result_dir": result_dir,
        "matrix_id": inputs.get("matrix"),
        "run_params": json.loads((result_dir / "run_simulation_parameters.json").read_text()),
        "permutation": np.loadtxt(result_dir / "permutation.txt", dtype=np.int64),
        "partition_artifacts": load_partition_artifacts(result_dir),
        "coarsened_graph_matrix": load_mtx(result_dir / "coarsened_graph.mtx", label="coarsened graph"),
        "matrix_original": load_mtx(workspace.root() / inputs["matrix_path"], label="original matrix"),
        "matrix_permuted": load_mtx(result_dir / "matrix_permuted.mtx", label="permuted matrix"),
    }


# -------------------------------------------------------------------- data
def _labels(partition: dict[int, int], node_order) -> np.ndarray:
    return np.array([int(partition[int(node)]) for node in node_order], dtype=np.int64)


def _data(matrix, labels: np.ndarray, title: str, margin_mode: str | None) -> PartitionPlotData:
    coo = _as_csr_matrix(matrix).tocoo()
    if labels.shape[0] != coo.shape[0]:
        raise ValueError("Matrix label count must match the matrix dimension")
    return PartitionPlotData(int(coo.shape[0]), coo.row.astype(np.int64), coo.col.astype(np.int64), labels, title, margin_mode)


def case_plot_data(case: dict[str, Any], plot_name: str) -> PartitionPlotData:
    spec = _SPECS.get(plot_name)
    if spec is None:
        raise ValueError(f"Unsupported plot name: {plot_name}")
    dof = int(case["run_params"]["general_parameters"]["dof_per_node"])
    partition = case["partition_artifacts"][spec["partition_key"]]
    matrix = case[spec["matrix_key"]]
    margin = spec.get("margin_mode")

    if spec["kind"] == "matrix":
        labels = np.repeat(_labels(partition, sorted(partition)), dof)
        if spec.get("use_permutation"):
            labels = labels[np.asarray(case["permutation"], dtype=int)]
        return _data(matrix, labels, spec["title"], margin)

    graph_dof = int(spec.get("dof_per_node", dof))
    graph_matrix = graph_to_sparse_matrix(matrix_to_graph(matrix, dof_per_node=graph_dof))
    labels = _labels(partition, sorted(partition))
    if spec.get("use_partition_order"):
        order = _create_permutation_from_partition(partition, len(partition))
        graph_matrix = _permute_sparse_matrix(graph_matrix, order)
        labels = labels[order]
    return _data(graph_matrix, labels, spec["title"], margin)


# ----------------------------------------------------------------- drawing
def default_part_colors(parts: list[int]) -> dict[int, str]:
    """Evenly spaced hues, one per part (the look of the published figures)."""
    hsv = np.column_stack((np.linspace(0.0, 1.0, len(parts), endpoint=False), np.full(len(parts), 0.70), np.full(len(parts), 0.95)))
    rgb = hsv_to_rgb(hsv) if parts else np.empty((0, 3))
    return {part: to_hex(rgb[i]) for i, part in enumerate(parts)}


def quarter_ticks(size: int) -> list[int]:
    if size <= 1:
        return [0]
    last = size - 1
    ticks = [0, round(last * 0.25), round(last * 0.5), round(last * 0.75), last]
    return [int(t) for i, t in enumerate(ticks) if i == 0 or t != ticks[i - 1]]


def rounded_tick_labels(ticks: list[int], size: int) -> list[str]:
    if size <= 0:
        return ["0" for _ in ticks]
    base = 10 ** max(len(str(int(size))) - 2, 0)
    return ["0" if v <= 0 else str(int(math.floor(v / base + 0.5) * base)) for v in ticks]


@dataclass(frozen=True)
class FigureStyle:
    width_px: int = 700
    title_fontsize: float = 22
    label_fontsize: float = 18
    tick_labelsize: float = 16
    dpi: int = 160


def draw_partition_matrix(
    fig,
    data: PartitionPlotData,
    *,
    show_y_axis: bool = True,
    style: FigureStyle = FigureStyle(),
    part_colors: dict[int, str] | None = None,
):
    """Draw ``data`` onto ``fig`` (a ``matplotlib.figure.Figure``) and return the axes."""
    inches = max(1.0, style.width_px / 100.0)
    fig.set_size_inches(inches, inches)
    graph_frac = 0.82
    pad = (1.0 - graph_frac) / 2.0
    if show_y_axis:
        left, right = 0.16, 0.16 + graph_frac
    elif data.margin_mode == "coarsened_right_margin":
        left, right = 0.0, 0.98
    else:
        left, right = 0.0, graph_frac
    fig.subplots_adjust(left=left, right=right, bottom=pad, top=1.0 - pad)
    ax = fig.add_subplot(1, 1, 1)

    colors = part_colors or default_part_colors(data.parts)
    row_colors = np.array([colors[int(label)] for label in data.labels], dtype=object)
    n = data.n
    marker = 18.0 if n <= 200 else 8.0 if n <= 2000 else 2.5
    if data.rows.size:
        ax.scatter(data.cols, data.rows, c=row_colors[data.rows], s=marker, marker="s", linewidths=0)
    if n:
        diagonal = np.arange(n)
        ax.scatter(diagonal, diagonal, c=row_colors, s=marker * 1.5, marker="s", linewidths=0)

    ax.set_title(data.title, fontsize=style.title_fontsize)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-0.5, max(n - 0.5, 0.5))
    ax.set_ylim(max(n - 0.5, 0.5), -0.5)
    ax.set_xticks([])
    ax.tick_params(axis="both", labelsize=style.tick_labelsize)
    if show_y_axis:
        ax.set_ylabel("Row index", fontsize=style.label_fontsize)
        ticks = quarter_ticks(n)
        ax.set_yticks(ticks)
        ax.set_yticklabels(rounded_tick_labels(ticks, n))
    else:
        ax.set_yticks([])
    return ax


def render_png(data: PartitionPlotData, path: str | Path, *, show_y_axis: bool = True, style: FigureStyle = FigureStyle()) -> Path:
    """Draw ``data`` and save it as PNG (Agg canvas, no pyplot)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure()
    FigureCanvasAgg(fig)
    draw_partition_matrix(fig, data, show_y_axis=show_y_axis, style=style)
    fig.savefig(str(path), dpi=style.dpi)
    return Path(path)
