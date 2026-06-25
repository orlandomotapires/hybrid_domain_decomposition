
from pathlib import Path
import json
import sys
import math

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import hsv_to_rgb, to_hex

from libs.runtime.utils import load_mtx, _as_csr_matrix, graph_to_sparse_matrix, matrix_to_graph
from libs.permutation import _create_permutation_from_partition, _permute_sparse_matrix

cwd = Path.cwd().resolve()
repo_candidates = [cwd, *cwd.parents]

BATCH_RUNS_REPO = "batch/runs"

REPO_ROOT = next(
    (path for path in repo_candidates if (path / "src").exists() and (path / BATCH_RUNS_REPO).exists()),
    None,
)
sys.path.insert(0, str(REPO_ROOT / "src"))

NAME_MAPPING = {
    "qaoa_hardware": "QAOA Hardware",
    "qaoa_emulated": "QAOA Emulated",
    "qa_hardware": "QA Hardware",
    "qa_emulated": "QA Emulated",
    "metis": "Metis",

    "small": "Small",
    "medium": "Medium",
    "big": "Big",

    "quantum_approximation_optimizer": "QAOA",
    "quantum_annealer": "QA",
    "metis_partitioning": "Metis",
}

def find_case_row(case_key: str, rows: list[dict]) -> dict:
    for row in rows:
        if row.get("case_key") == case_key:
            return row

    available = ", ".join(row.get("case_key", "") for row in rows)
    raise KeyError(f"case_key {case_key!r} not found. Available case keys: {available}")


def normalize_plot_selection(plot_names: list[str]) -> list[str]:
    expanded: list[str] = []
    for name in plot_names:
        expanded.append(name)

    return list(dict.fromkeys(expanded))


def load_partition_artifacts(result_dir: Path) -> dict:
    partition_artifacts_path = result_dir / "partition_artifacts.json"
    partition_artifacts = json.loads(partition_artifacts_path.read_text())
    return {
        "coarse_partition": {
            int(node): int(partition_id)
            for node, partition_id in partition_artifacts["coarse_partition"].items()
        },
        "final_partition": {
            int(node): int(partition_id)
            for node, partition_id in partition_artifacts["final_partition"].items()
        },
    }


def _partition_labels(partition: dict[int, int], node_order: list[int] | np.ndarray) -> np.ndarray:
    return np.array([int(partition[int(node)]) for node in node_order], dtype=np.int64)


def _figure_size_from_display_width(display_width: int | None, display_height: int | None = None, *, square: bool = True) -> tuple[float, float]:
    if display_width is None:
        return (10.0, 10.0) if square else (14.0, 5.0)

    width_inches = max(1.0, float(display_width) / 100.0)
    if square:
        return (width_inches, width_inches)
    height_inches = max(4.0, width_inches * 0.55)
    if display_height is not None:
        height_inches = max(1.0, float(display_height) / 100.0)
    return (width_inches, height_inches)


def _quarter_ticks(size: int) -> list[int]:
    if size <= 1:
        return [0]
    last = size - 1
    ticks = [
        0,
        int(round(last * 0.25)),
        int(round(last * 0.50)),
        int(round(last * 0.75)),
        last,
    ]
    deduped: list[int] = []
    for tick in ticks:
        if not deduped or tick != deduped[-1]:
            deduped.append(tick)
    return deduped


def _rounded_tick_labels(ticks: list[int], size: int) -> list[str]:
    if size <= 0:
        return ["0" for _ in ticks]

    # Round labels to readable "clean" values (example: 78108 -> 80000).
    rounding_base = 10 ** max(len(str(int(size))) - 2, 0)
    labels: list[str] = []
    for value in ticks:
        if value <= 0:
            labels.append("0")
            continue
        rounded = int(math.floor((value / rounding_base) + 0.5) * rounding_base)
        labels.append(str(rounded))
    return labels


def _render_partition_matrix_plot(
    matrix,
    labels: np.ndarray,
    *,
    title: str,
    display_width: int | None = None,
    display_height: int | None = None,
    show_y_axis: bool = True,
    partition_colors: dict[int, str] | None = None,
    title_fontsize: float = 25,
    label_fontsize: float = 20,
    tick_labelsize: float = 20,
    margin_mode: str | None = None,
    save_path: str | Path | None = None,
    dpi: int = 200,
) -> None:
    matrix_csr = _as_csr_matrix(matrix)
    matrix_coo = matrix_csr.tocoo()
    normalized_labels = np.asarray(labels, dtype=np.int64).ravel()
    matrix_size = matrix_csr.shape[0]
    if normalized_labels.shape[0] != matrix_size:
        raise ValueError("Matrix label count must match the matrix dimension")

    color_map = partition_colors or _build_partition_color_map(set(int(label) for label in normalized_labels.tolist()))
    row_colors = np.array([color_map[int(label)] for label in normalized_labels], dtype=object)

    figsize = _figure_size_from_display_width(display_width, display_height) if display_width is not None else ((10.0, 10.0) if matrix_size <= 500 else (12.0, 12.0))
    fig, ax = plt.subplots(figsize=figsize, constrained_layout=False)
    # Keep a fixed inner square size across all plots.
    graph_frac = 0.82
    vertical_pad = (1.0 - graph_frac) / 2.0
    if show_y_axis:
        left = 0.16
        right = left + graph_frac
    else:
        if margin_mode == "coarsened_right_margin":
            left = 0.0
            right = 0.98
        elif margin_mode == "uncoarsened_match":
            left = 0.0
            right = graph_frac
        else:
            left = 0.0
            right = left + graph_frac
    fig.subplots_adjust(left=left, right=right, bottom=vertical_pad, top=1.0 - vertical_pad)

    marker_size = 18.0 if matrix_size <= 200 else 8.0 if matrix_size <= 2000 else 2.5
    if matrix_coo.nnz > 0:
        ax.scatter(
            matrix_coo.col,
            matrix_coo.row,
            c=row_colors[matrix_coo.row],
            s=marker_size,
            marker="s",
            linewidths=0,
        )

    diagonal_index = np.arange(matrix_size, dtype=int)
    if matrix_size > 0:
        ax.scatter(
            diagonal_index,
            diagonal_index,
            c=row_colors,
            s=marker_size * 1.5,
            marker="s",
            linewidths=0,
        )

    ax.set_title(title, fontsize=title_fontsize)
    ax.set_xlabel("")
    ax.set_aspect("equal", adjustable="box")
    ax.invert_yaxis()
    ax.tick_params(axis="both", labelsize=tick_labelsize)
    ax.set_xlim(-0.5, max(matrix_size - 0.5, 0.5))
    ax.set_ylim(max(matrix_size - 0.5, 0.5), -0.5)
    ax.tick_params(axis="x", bottom=False, top=False, labelbottom=False, labeltop=False)
    ax.set_xticks([])
    if show_y_axis:
        ax.set_ylabel("Row index", fontsize=label_fontsize)
        y_ticks = _quarter_ticks(matrix_size)
        ax.set_yticks(y_ticks)
        ax.set_yticklabels(_rounded_tick_labels(y_ticks, matrix_size))
        ax.tick_params(axis="y", left=True, labelleft=True)
    else:
        ax.set_ylabel("")
        ax.set_yticks([])
        ax.tick_params(axis="y", left=False, labelleft=False)
    if save_path:
        # Keep the full figure canvas so images with/without y-axis have identical file dimensions.
        fig.savefig(str(save_path), dpi=dpi)
        plt.close(fig)
    else:
        plt.show()
        plt.close(fig)


def render_partition_graph_preview(
    matrix,
    partition: dict[int, int],
    *,
    title: str,
    dof_per_node: int = 1,
    order: np.ndarray | None = None,
    display_width: int | None = None,
    display_height: int | None = None,
    title_fontsize: float = 25,
    label_fontsize: float = 20,
    tick_labelsize: float = 20,
    margin_mode: str | None = None,
    show_y_axis: bool = True,
    save_path: str | Path | None = None,
    dpi: int = 200,
) -> None:
    graph = matrix_to_graph(matrix, dof_per_node=dof_per_node)
    graph_matrix = graph_to_sparse_matrix(graph)
    node_order = sorted(partition)
    labels = _partition_labels(partition, node_order)

    if order is not None:
        order = np.asarray(order, dtype=int)
        graph_matrix = _permute_sparse_matrix(graph_matrix, order)
        labels = labels[order]

    _render_partition_matrix_plot(
        graph_matrix,
        labels,
        title=title,
        display_width=display_width,
        display_height=display_height,
        show_y_axis=show_y_axis,
        margin_mode=margin_mode,
        save_path=save_path,
        dpi=dpi,
        title_fontsize=title_fontsize,
        label_fontsize=label_fontsize,
        tick_labelsize=tick_labelsize,
    )

# Render the matrix with the partition colored
def render_partition_matrix(
    matrix,
    partition: dict[int, int],
    dof_per_node: int,
    title: str,
    permutation: np.ndarray | None = None,
    *,
    display_width: int | None = None,
    display_height: int | None = None,
    title_fontsize: float = 16,
    label_fontsize: float = 14,
    tick_labelsize: float = 12,
    margin_mode: str | None = None,
    show_y_axis: bool = True,
    save_path: str | Path | None = None,
    dpi: int = 200,
) -> None:
    node_order = sorted(partition)
    labels = np.array([int(partition[int(node)]) for node in node_order], dtype=np.int64)
    labels = np.repeat(labels, int(dof_per_node))
    if permutation is not None:
        labels = labels[np.asarray(permutation, dtype=int)]

    _render_partition_matrix_plot(
        matrix,
        labels,
        title=title,
        display_width=display_width,
        display_height=display_height,
        show_y_axis=show_y_axis,
        margin_mode=margin_mode,
        save_path=save_path,
        dpi=dpi,
        title_fontsize=title_fontsize,
        label_fontsize=label_fontsize,
        tick_labelsize=tick_labelsize,
    )


def _curve_points_from_metrics(structural_metrics: dict[str, dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    percent_values = np.round(np.arange(0.0, 5.0, 0.05), 10)

    def metric_value(metrics: dict[str, float], percent: float) -> float:
        if float(percent).is_integer():
            percent_label = f"{percent:.1f}%"
        else:
            percent_label = f"{percent:.10f}".rstrip("0").rstrip(".") + "%"
        key = f"frac_within_|i-j|<={percent_label}_of_n"
        return float(metrics[key])

    original_metrics = structural_metrics["original"]
    permuted_metrics = structural_metrics["permuted"]
    original_curve = np.array([metric_value(original_metrics, percent) for percent in percent_values], dtype=float)
    permuted_curve = np.array([metric_value(permuted_metrics, percent) for percent in percent_values], dtype=float)
    return percent_values, original_curve, permuted_curve

def load_case_from_summary(row: dict) -> dict:
    result_dir = REPO_ROOT / row["result_dir"]
    demonstrator_dir = result_dir.parents[1]
    data_dir = demonstrator_dir / "data"
    simulation_config = json.loads((data_dir / "simulation_config.json").read_text())
    run_params = json.loads((result_dir / "run_simulation_parameters.json").read_text())
    permutation = np.loadtxt(result_dir / "permutation.txt", dtype=np.int64)
    coarsened_graph_matrix = load_mtx(result_dir / "coarsened_graph.mtx", label="coarsened graph")
    run_metrics_path = result_dir / "run_metrics.json"
    run_metrics = json.loads(run_metrics_path.read_text()) if run_metrics_path.exists() else None
    partition_artifacts = load_partition_artifacts(result_dir)

    matrices_dir = data_dir / "matrices"
    matrix_k_original = load_mtx(matrices_dir / simulation_config["input_matrices"]["matrix_k_file_path"], label="K original")
    matrix_m_original = load_mtx(matrices_dir / simulation_config["input_matrices"]["matrix_m_file_path"], label="M original")
    matrix_k_permuted = load_mtx(result_dir / "matrix_k_permuted.mtx", label="K permuted")
    matrix_m_permuted = load_mtx(result_dir / "matrix_m_permuted.mtx", label="M permuted")

    return {
        "row": row,
        "result_dir": result_dir,
        "demonstrator_dir": demonstrator_dir,
        "simulation_config": simulation_config,
        "run_params": run_params,
        "run_metrics": run_metrics,
        "permutation": permutation,
        "partition_artifacts": partition_artifacts,
        "coarsened_graph_matrix": coarsened_graph_matrix,
        "matrix_k_original": matrix_k_original,
        "matrix_m_original": matrix_m_original,
        "matrix_k_permuted": matrix_k_permuted,
        "matrix_m_permuted": matrix_m_permuted,
    }

_CASE_PLOT_SPECS = {
    "k_original_matrix_partitioned": {
        "kind": "matrix",
        "matrix_key": "matrix_k_original",
        "partition_key": "final_partition",
        "title": "Original K",
    },
    "k_permuted_matrix_partitioned": {
        "kind": "matrix",
        "matrix_key": "matrix_k_permuted",
        "partition_key": "final_partition",
        "title": "Permuted K",
        "use_permutation": True,
    },
    "k_original_graph_partitioned": {
        "kind": "graph",
        "matrix_key": "matrix_k_original",
        "partition_key": "final_partition",
        "title": "Original K graph",
    },
    "k_coarsened_graph_partitioned": {
        "kind": "graph",
        "matrix_key": "coarsened_graph_matrix",
        "partition_key": "coarse_partition",
        "title": "Coarsened K graph",
        "margin_mode": "coarsened_right_margin",
        "dof_per_node": 1,
    },
    "k_uncoarsened_graph_partitioned": {
        "kind": "graph",
        "matrix_key": "matrix_k_original",
        "partition_key": "final_partition",
        "title": "Uncoarsened K graph",
        "margin_mode": "uncoarsened_match",
        "use_partition_order": True,
    },
    "m_original_matrix_partitioned": {
        "kind": "matrix",
        "matrix_key": "matrix_m_original",
        "partition_key": "final_partition",
        "title": "Original M",
    },
    "m_permuted_matrix_partitioned": {
        "kind": "matrix",
        "matrix_key": "matrix_m_permuted",
        "partition_key": "final_partition",
        "title": "Permuted M",
        "use_permutation": True,
    },
    "m_original_graph_partitioned": {
        "kind": "graph",
        "matrix_key": "matrix_m_original",
        "partition_key": "final_partition",
        "title": "Original M graph",
    },
    "m_coarsened_graph_partitioned": {
        "kind": "graph",
        "matrix_key": "coarsened_graph_matrix",
        "partition_key": "coarse_partition",
        "title": "Coarsened M graph",
        "margin_mode": "coarsened_right_margin",
        "dof_per_node": 1,
    },
    "m_uncoarsened_graph_partitioned": {
        "kind": "graph",
        "matrix_key": "matrix_m_original",
        "partition_key": "final_partition",
        "title": "Uncoarsened M graph",
        "margin_mode": "uncoarsened_match",
        "use_partition_order": True,
    },
}


def _render_case_plot_from_spec(
    case: dict,
    method: str,
    spec: dict,
    *,
    display_width: int | None,
    display_height: int | None,
    title_fontsize: float,
    label_fontsize: float,
    tick_labelsize: float,
    show_y_axis: bool,
    save_path: str | Path | None = None,
    dpi: int = 200,
) -> None:
    dof_per_node = int(case["run_params"]["general_parameters"]["dof_per_node"])
    partitioning_strategy = case["run_params"]["partitioning_parameters"]["partitioning_strategy"]
    partition = case["partition_artifacts"][spec["partition_key"]]
    title = spec.get("title_template", spec.get("title", ""))
    if "title_template" in spec:
        title = str(title).format(strategy=NAME_MAPPING[method])

    if spec["kind"] == "matrix":    
        render_partition_matrix(
            case[spec["matrix_key"]],
            partition=partition,
            dof_per_node=dof_per_node,
            title=str(title),
            permutation=case["permutation"] if spec.get("use_permutation") else None,
            display_width=display_width,
            display_height=display_height,
            title_fontsize=title_fontsize,
            label_fontsize=label_fontsize,
            tick_labelsize=tick_labelsize,
            margin_mode=spec.get("margin_mode"),
            show_y_axis=show_y_axis,
            save_path=save_path,
            dpi=dpi,
        )
        return

    if spec["kind"] == "graph":
        graph_dof_per_node = int(spec.get("dof_per_node", dof_per_node))
        order = _create_permutation_from_partition(partition, len(partition)) if spec.get("use_partition_order") else None
        render_partition_graph_preview(
            case[spec["matrix_key"]],
            partition,
            title=str(title),
            dof_per_node=graph_dof_per_node,
            order=order,
            display_width=display_width,
            display_height=display_height,
            title_fontsize=title_fontsize,
            label_fontsize=label_fontsize,
            tick_labelsize=tick_labelsize,
            margin_mode=spec.get("margin_mode"),
            show_y_axis=show_y_axis,
            save_path=save_path,
            dpi=dpi,
        )
        return

    raise ValueError(f"Unknown plot kind: {spec['kind']}")


def render_case_plot(
    case: dict,
    method: str,
    plot_name: str,
    *,
    display_width: int | None = None,
    display_height: int | None = None,
    title_fontsize: float = 16,
    label_fontsize: float = 14,
    tick_labelsize: float = 12,
    show_y_axis: bool = True,
    save_path: str | Path | None = None,
    dpi: int = 200,
) -> None:
    spec = _CASE_PLOT_SPECS.get(plot_name)
    if spec is None:
        raise ValueError(f"Unknown plot name: {plot_name}")

    _render_case_plot_from_spec(
        case,
        method,
        spec,
        display_width=display_width,
        display_height=display_height,
        title_fontsize=title_fontsize,
        label_fontsize=label_fontsize,
        tick_labelsize=tick_labelsize,
        show_y_axis=show_y_axis,
        save_path=save_path,
        dpi=dpi,
    )


def render_k_curve_comparison(
    backend_case: dict,
    metis_case: dict,
    *,
    title: str,
    backend_label: str,
    metis_label: str,
    display_width: int | None = None,
    display_height: int | None = None,
    title_fontsize: float = 16,
    label_fontsize: float = 14,
    tick_labelsize: float = 12,
    save_path: str | Path | None = None,
    dpi: int = 200,
) -> None:
    backend_row = backend_case["row"]
    metis_row = metis_case["row"]
    if backend_row["geometry"] != metis_row["geometry"]:
        raise ValueError("Curve comparisons must use the same geometry")
    if backend_row["coarsening_size"] != metis_row["coarsening_size"]:
        raise ValueError("Curve comparisons must use the same coarsening size")

    if backend_case["run_metrics"] is None or metis_case["run_metrics"] is None:
        raise ValueError("Both curve comparison cases must have run_metrics.json")

    percent_values, backend_original_curve, backend_permuted_curve = _curve_points_from_metrics(
        backend_case["run_metrics"]["K"]["structural_metrics"]
    )
    _, _, metis_permuted_curve = _curve_points_from_metrics(metis_case["run_metrics"]["K"]["structural_metrics"])

    fig, ax = plt.subplots(1, 1, figsize=_figure_size_from_display_width(display_width, display_height, square=False), constrained_layout=True)
    if display_height is not None:
        fig.set_size_inches(fig.get_size_inches()[0], max(1.0, float(display_height) / 100.0))
    curves = [
        (backend_original_curve, "Original K"),
        (backend_permuted_curve, f"{backend_label} permuted K"),
        (metis_permuted_curve, f"{metis_label} permuted K"),
    ]
    for curve_values, curve_label in curves:
        ax.plot(percent_values, curve_values, linewidth=2.0, label=curve_label)
    ax.set_title(f"{title}: fraction within bandwidth", fontsize=title_fontsize)
    ax.set_xlabel("Band range (% of n)", fontsize=label_fontsize)
    ax.set_ylabel("Fraction of nonzeros within band", fontsize=label_fontsize)
    ax.set_xlim(0.0, 2.0)
    ax.set_ylim(0.0, 1.02)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=tick_labelsize)
    ax.legend()
    if save_path:
        fig.savefig(str(save_path), dpi=dpi)
        plt.close(fig)
    else:
        plt.show()
        plt.close(fig)

def get_completed_rows(batch_run_name: str) -> list[dict]:
    BATCH_DIR = REPO_ROOT / BATCH_RUNS_REPO / batch_run_name
    BATCH_SUMMARY_PATH = BATCH_DIR / "batch_summary.json"
    batch_summary = json.loads(BATCH_SUMMARY_PATH.read_text())
    batch_rows = batch_summary.get("rows", [])
    completed_rows = [row for row in batch_rows if row.get("status") == "completed" and row.get("result_dir")]

    print(f"Batch directory: {BATCH_DIR}")
    print(f"Cases in summary: {len(batch_rows)}")
    print(f"Completed cases with result_dir: {len(completed_rows)}")

    # Show all cases
    print("\nAvailable cases:")
    for row in batch_rows:
        status = row.get("status", "unknown")
        case_key = row.get("case_key", "unknown")
        print(f"  - {case_key} (status: {status})")

    return completed_rows


def _build_distinct_node_colors(count: int) -> np.ndarray:
    if count <= 0:
        return np.empty((0, 3), dtype=float)
    hsv = np.column_stack(
        (
            np.linspace(0.0, 1.0, count, endpoint=False),
            np.full(count, 0.70, dtype=float),
            np.full(count, 0.95, dtype=float),
        )
    )
    return hsv_to_rgb(hsv)


def _build_partition_color_map(partitions: set[int]) -> dict[int, str]:
    sorted_partitions = sorted(int(partition) for partition in partitions)
    palette = _build_distinct_node_colors(len(sorted_partitions))
    return {
        partition: to_hex(palette[index], keep_alpha=False)
        for index, partition in enumerate(sorted_partitions)
    }

def render_m_curve_comparison(
    backend_case: dict,
    metis_case: dict,
    *,
    title: str,
    backend_label: str,
    metis_label: str,
    display_width: int | None = None,
    display_height: int | None = None,
    title_fontsize: float = 16,
    label_fontsize: float = 14,
    tick_labelsize: float = 12,
    save_path: str | Path | None = None,
    dpi: int = 200,
) -> None:
    backend_row = backend_case["row"]
    metis_row = metis_case["row"]
    if backend_row["geometry"] != metis_row["geometry"]:
        raise ValueError("Curve comparisons must use the same geometry")
    if backend_row["coarsening_size"] != metis_row["coarsening_size"]:
        raise ValueError("Curve comparisons must use the same coarsening size")

    if backend_case["run_metrics"] is None or metis_case["run_metrics"] is None:
        raise ValueError("Both curve comparison cases must have run_metrics.json")

    percent_values, backend_original_curve, backend_permuted_curve = _curve_points_from_metrics(
        backend_case["run_metrics"]["M"]["structural_metrics"]
    )
    _, _, metis_permuted_curve = _curve_points_from_metrics(metis_case["run_metrics"]["M"]["structural_metrics"])

    fig, ax = plt.subplots(1, 1, figsize=_figure_size_from_display_width(display_width, display_height, square=False), constrained_layout=True)
    if display_height is not None:
        fig.set_size_inches(fig.get_size_inches()[0], max(1.0, float(display_height) / 100.0))
    curves = [
        (backend_original_curve, "Original M"),
        (backend_permuted_curve, f"{backend_label} permuted M"),
        (metis_permuted_curve, f"{metis_label} permuted M"),
    ]
    for curve_values, curve_label in curves:
        ax.plot(percent_values, curve_values, linewidth=2.0, label=curve_label)
    ax.set_title(f"{title}: fraction within bandwidth (M)", fontsize=title_fontsize)
    ax.set_xlabel("Band range (% of n)", fontsize=label_fontsize)
    ax.set_ylabel("Fraction of nonzeros within band", fontsize=label_fontsize)
    ax.set_xlim(0.0, 2.0)
    ax.set_ylim(0.0, 1.02)
    ax.grid(True, alpha=0.3)
    ax.tick_params(axis="both", labelsize=tick_labelsize)
    ax.legend()
    if save_path:
        fig.savefig(str(save_path), dpi=dpi)
        plt.close(fig)
    else:
        plt.show()
        plt.close(fig)
def build_matrix_summary_lines(prefix, DEMONSTRATOR, demo_rows, demo_suffix=None):
    """
    Generate LaTeX table lines for K or M matrix metrics from batch summary rows.
    prefix: 'K' or 'M'
    DEMONSTRATOR: demonstrator name (e.g. 'demonstrator_01')
    demo_rows: filtered rows for this demonstrator
    demo_suffix: string of digits for display/label (optional)
    """
    def fmt_int(value):
        return str(int(round(float(value)))) if value is not None else "N/A"

    def fmt_avg(value):
        return f"{float(value):.2f}" if value is not None else "N/A"

    def fmt_frac(value):
        return f"{float(value):.4f}" if value is not None else "N/A"

    def pretty_method(method: str) -> str:
        return {
            "metis": "METIS",
            "qa_hardware": "QA hardware",
            "qa_emulated": "QA emulated",
            "qaoa_emulated": "QAOA emulated",
            "qaoa_hardware": "QAOA hardware",
        }.get(method, method)

    method_order = ["metis", "qa_hardware", "qa_emulated", "qaoa_emulated", "qaoa_hardware"]
    size_order = ["big", "medium", "small"]
    row_end = chr(92) * 2

    row_by_case = {row["case_key"]: row for row in demo_rows}
    original_row = demo_rows[0] if demo_rows else None

    table_rows = []
    if original_row:
        table_rows.append(
            (
                "Original",
                "N/A",
                fmt_int(original_row.get(f"{prefix}_bandwidth_original")),
                fmt_avg(original_row.get(f"{prefix}_avg_bandwidth_original")),
                fmt_frac(original_row.get(f"{prefix}_frac_0_1pct_original")),
                fmt_frac(original_row.get(f"{prefix}_frac_0_4pct_original")),
                fmt_frac(original_row.get(f"{prefix}_frac_0_7pct_original")),
                fmt_frac(original_row.get(f"{prefix}_frac_1_0pct_original")),
            )
        )

    for method in method_order:
        for size in size_order:
            case_key = f"{DEMONSTRATOR}__{method}__{size}"
            row = row_by_case.get(case_key)
            if row is None:
                continue
            table_rows.append(
                (
                    pretty_method(method),
                    size,
                    fmt_int(row.get(f"{prefix}_bandwidth_permuted")),
                    fmt_avg(row.get(f"{prefix}_avg_bandwidth_permuted")),
                    fmt_frac(row.get(f"{prefix}_frac_0_1pct_permuted")),
                    fmt_frac(row.get(f"{prefix}_frac_0_4pct_permuted")),
                    fmt_frac(row.get(f"{prefix}_frac_0_7pct_permuted")),
                    fmt_frac(row.get(f"{prefix}_frac_1_0pct_permuted")),
                )
            )

    demo_display = f"Demonstrator~{demo_suffix}" if demo_suffix else DEMONSTRATOR
    demo_label = f"tab:results_demo{int(demo_suffix)}_{prefix.lower()}" if demo_suffix else f"tab:results_{prefix.lower()}"

    lines = [
        "\\begin{table}[H]",
        f"\\caption{{{prefix}-matrix numerical summary for {demo_display}}}",
        "\\scriptsize",
        "\\renewcommand{\\arraystretch}{1.15}",
        "\\begin{tabularx}{\\textwidth}{X l r r r r r r}",
        "\\toprule",
        "\\textbf{Method} & \\textbf{Size} & \\textbf{Bandwidth} & \\textbf{Avg. Bandwidth} & \\textbf{$\\mathrm{frac}_{0.1\\%}$} & \\textbf{$\\mathrm{frac}_{0.4\\%}$} & \\textbf{$\\mathrm{frac}_{0.7\\%}$} & \\textbf{$\\mathrm{frac}_{1.0\\%}$}" + row_end,
        "\\midrule",
    ]
    for method_name, size_name, bandwidth, avg_bandwidth, frac_01, frac_04, frac_07, frac_10 in table_rows:
        lines.append(
            f"{method_name} & {size_name} & {bandwidth} & {avg_bandwidth} & {frac_01} & {frac_04} & {frac_07} & {frac_10}" + row_end
        )
    lines.extend([
        "\\bottomrule",
        "\\end{tabularx}",
        "\\centering",
        "Source: Author (2026)",
        f"\\label{{{demo_label}}}",
        "\\end{table}",
    ])
    return lines