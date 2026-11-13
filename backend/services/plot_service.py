from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
NOTEBOOKS_DIR = ROOT_DIR / "notebooks"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(NOTEBOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKS_DIR))

from libs.runtime import workspace  # noqa: E402
import notebook_functions as nf


AVAILABLE_CASE_PLOTS = [
    {"id": "original_matrix_partitioned", "label": "Original Matrix (Partition Colored)", "kind": "matrix", "show_y_axis": True},
    {"id": "permuted_matrix_partitioned", "label": "Permuted Matrix (Partition Colored)", "kind": "matrix", "show_y_axis": False},
    {"id": "original_graph_partitioned", "label": "Original Graph", "kind": "graph", "show_y_axis": True},
    {"id": "coarsened_graph_partitioned", "label": "Coarsened Graph", "kind": "graph", "show_y_axis": False},
    {"id": "uncoarsened_graph_partitioned", "label": "Uncoarsened Graph", "kind": "graph", "show_y_axis": False},
]


def extract_curve_series(run_metrics: dict[str, Any]) -> list[dict[str, float]]:
    """Extract interactive curve points (percent vs original & permuted fraction within band)."""
    mat_block = run_metrics.get("matrix", {}) if isinstance(run_metrics, dict) else {}
    structural = mat_block.get("structural_metrics", {}) if isinstance(mat_block, dict) else {}
    orig = structural.get("original", {}) if isinstance(structural, dict) else {}
    perm = structural.get("permuted", {}) if isinstance(structural, dict) else {}

    if not orig and not perm:
        return []

    percent_values = np.round(np.arange(0.0, 5.0, 0.05), 10)
    points: list[dict[str, float]] = []
    for p in percent_values:
        if float(p).is_integer():
            label = f"{p:.1f}%"
        else:
            label = f"{p:.10f}".rstrip("0").rstrip(".") + "%"
        key = f"frac_within_|i-j|<={label}_of_n"
        if key in orig or key in perm:
            points.append(
                {
                    "percent": float(p),
                    "original": float(orig.get(key, 0.0)),
                    "permuted": float(perm.get(key, 0.0)),
                }
            )
    return points


def extract_kpi_summary(run_metrics: dict[str, Any]) -> dict[str, Any]:
    """Compute high-level KPIs (bandwidth reduction, avg bandwidth, nB^2 reduction, band fractions, permutation check)."""
    block = run_metrics.get("matrix", {}) if isinstance(run_metrics, dict) else {}
    structural = block.get("structural_metrics", {}) if isinstance(block, dict) else {}
    orig = structural.get("original", {}) if isinstance(structural, dict) else {}
    perm = structural.get("permuted", {}) if isinstance(structural, dict) else {}
    perm_check = block.get("permutation_check", {}) if isinstance(block, dict) else {}

    n = orig.get("n") or perm.get("n")
    bw_orig = orig.get("bandwidth")
    bw_perm = perm.get("bandwidth")
    avg_bw_orig = orig.get("avg_bandwidth")
    avg_bw_perm = perm.get("avg_bandwidth")

    bw_reduction_pct = None
    if bw_orig and bw_perm is not None and float(bw_orig) > 0:
        bw_reduction_pct = 100.0 * (float(bw_orig) - float(bw_perm)) / float(bw_orig)

    nb2_orig = None
    nb2_perm = None
    nb2_reduction_pct = None
    if n is not None and bw_orig is not None and bw_perm is not None:
        nb2_orig = float(n) * (float(bw_orig) ** 2)
        nb2_perm = float(n) * (float(bw_perm) ** 2)
        if nb2_orig > 0:
            nb2_reduction_pct = 100.0 * (nb2_orig - nb2_perm) / nb2_orig

    summary = {
        "n": n,
        "nnz_original": orig.get("nnz"),
        "nnz_permuted": perm.get("nnz"),
        "bandwidth_original": bw_orig,
        "bandwidth_permuted": bw_perm,
        "bandwidth_reduction_pct": bw_reduction_pct,
        "avg_bandwidth_original": avg_bw_orig,
        "avg_bandwidth_permuted": avg_bw_perm,
        "nb2_original": nb2_orig,
        "nb2_permuted": nb2_perm,
        "nb2_reduction_pct": nb2_reduction_pct,
        "frac_0_1pct_original": orig.get("frac_within_|i-j|<=0.1%_of_n"),
        "frac_0_1pct_permuted": perm.get("frac_within_|i-j|<=0.1%_of_n"),
        "frac_0_4pct_original": orig.get("frac_within_|i-j|<=0.4%_of_n"),
        "frac_0_4pct_permuted": perm.get("frac_within_|i-j|<=0.4%_of_n"),
        "frac_0_7pct_original": orig.get("frac_within_|i-j|<=0.7%_of_n"),
        "frac_0_7pct_permuted": perm.get("frac_within_|i-j|<=0.7%_of_n"),
        "frac_1_0pct_original": orig.get("frac_within_|i-j|<=1.0%_of_n"),
        "frac_1_0pct_permuted": perm.get("frac_within_|i-j|<=1.0%_of_n"),
        "permutation_check": perm_check,
    }
    return summary


def load_case_from_result_dir(result_dir_rel: str) -> dict[str, Any]:
    """Load run artifacts from a result directory for plot rendering."""
    if not (workspace.root() / result_dir_rel).resolve().exists():
        raise FileNotFoundError(f"Result directory not found: {result_dir_rel}")
    case = nf.load_case_from_summary({"result_dir": result_dir_rel})
    case["row"] = {"result_dir": result_dir_rel}
    return case


def render_or_get_cached_plot(
    result_dir_rel: str,
    plot_name: str,
    *,
    force_rerender: bool = False,
) -> Path:
    """Render one of the canonical partition/matrix/graph plots and cache it under <result_dir>/plots/."""
    spec_info = next((item for item in AVAILABLE_CASE_PLOTS if item["id"] == plot_name), None)
    if spec_info is None:
        raise ValueError(f"Unsupported plot name: {plot_name}")

    result_dir = (workspace.root() / result_dir_rel).resolve()
    plots_dir = result_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    out_file = plots_dir / f"{plot_name}.png"

    if out_file.exists() and not force_rerender:
        return out_file

    case = load_case_from_result_dir(result_dir_rel)
    strategy = case["run_params"]["partitioning_parameters"]["partitioning_strategy"]
    nf.render_case_plot(
        case,
        strategy,
        plot_name,
        display_width=700,
        display_height=700,
        title_fontsize=22,
        label_fontsize=18,
        tick_labelsize=16,
        show_y_axis=bool(spec_info["show_y_axis"]),
        save_path=str(out_file),
        dpi=160,
    )
    return out_file
