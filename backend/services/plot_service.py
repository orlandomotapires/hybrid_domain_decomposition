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

from libs.runtime.utils import load_mtx
import notebook_functions as nf


AVAILABLE_CASE_PLOTS = [
    {"id": "k_original_matrix_partitioned", "label": "Original K Matrix (Partition Colored)", "matrix": "K", "kind": "matrix", "show_y_axis": True},
    {"id": "k_permuted_matrix_partitioned", "label": "Permuted K Matrix (Partition Colored)", "matrix": "K", "kind": "matrix", "show_y_axis": False},
    {"id": "k_original_graph_partitioned", "label": "Original K Graph", "matrix": "K", "kind": "graph", "show_y_axis": True},
    {"id": "k_coarsened_graph_partitioned", "label": "Coarsened K Graph", "matrix": "K", "kind": "graph", "show_y_axis": False},
    {"id": "k_uncoarsened_graph_partitioned", "label": "Uncoarsened K Graph", "matrix": "K", "kind": "graph", "show_y_axis": False},
    {"id": "m_original_matrix_partitioned", "label": "Original M Matrix (Partition Colored)", "matrix": "M", "kind": "matrix", "show_y_axis": True},
    {"id": "m_permuted_matrix_partitioned", "label": "Permuted M Matrix (Partition Colored)", "matrix": "M", "kind": "matrix", "show_y_axis": False},
    {"id": "m_original_graph_partitioned", "label": "Original M Graph", "matrix": "M", "kind": "graph", "show_y_axis": True},
    {"id": "m_coarsened_graph_partitioned", "label": "Coarsened M Graph", "matrix": "M", "kind": "graph", "show_y_axis": False},
    {"id": "m_uncoarsened_graph_partitioned", "label": "Uncoarsened M Graph", "matrix": "M", "kind": "graph", "show_y_axis": False},
]


def extract_curve_series(run_metrics: dict[str, Any], matrix_name: str = "K") -> list[dict[str, float]]:
    """Extract interactive curve points (percent vs original & permuted fraction within band)."""
    mat_block = run_metrics.get(matrix_name, {}) if isinstance(run_metrics, dict) else {}
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
    summary: dict[str, Any] = {}
    for mat_name in ("K", "M"):
        block = run_metrics.get(mat_name, {}) if isinstance(run_metrics, dict) else {}
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

        summary[mat_name] = {
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
    result_dir = (ROOT_DIR / result_dir_rel).resolve()
    if not result_dir.exists():
        raise FileNotFoundError(f"Result directory not found: {result_dir_rel}")

    demonstrator_dir = result_dir.parents[1]
    data_dir = demonstrator_dir / "data"
    simulation_config = json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8"))
    run_params = json.loads((result_dir / "run_simulation_parameters.json").read_text(encoding="utf-8"))
    permutation = np.loadtxt(result_dir / "permutation.txt", dtype=np.int64)
    coarsened_graph_matrix = load_mtx(result_dir / "coarsened_graph.mtx", label="coarsened graph")
    run_metrics_path = result_dir / "run_metrics.json"
    run_metrics = json.loads(run_metrics_path.read_text(encoding="utf-8")) if run_metrics_path.exists() else None
    partition_artifacts = nf.load_partition_artifacts(result_dir)

    matrices_dir = data_dir / "matrices"
    matrix_k_original = load_mtx(matrices_dir / simulation_config["input_matrices"]["matrix_k_file_path"], label="K original")
    matrix_m_original = load_mtx(matrices_dir / simulation_config["input_matrices"]["matrix_m_file_path"], label="M original")
    matrix_k_permuted = load_mtx(result_dir / "matrix_k_permuted.mtx", label="K permuted")
    matrix_m_permuted = load_mtx(result_dir / "matrix_m_permuted.mtx", label="M permuted")

    return {
        "row": {"result_dir": result_dir_rel},
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


def render_or_get_cached_plot(
    result_dir_rel: str,
    plot_name: str,
    *,
    force_rerender: bool = False,
) -> Path:
    """Render one of the 10 canonical partition/matrix/graph plots and cache it under <result_dir>/plots/."""
    spec_info = next((item for item in AVAILABLE_CASE_PLOTS if item["id"] == plot_name), None)
    if spec_info is None:
        raise ValueError(f"Unsupported plot name: {plot_name}")

    result_dir = (ROOT_DIR / result_dir_rel).resolve()
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


def build_nb2_latex_lines(prefix: str, demonstrator: str, demo_rows: list[dict[str, Any]]) -> list[str]:
    """Generate the LaTeX nB^2 iteration complexity table matching plots_notebook.ipynb."""
    method_order = ["metis", "qa_hardware", "qa_emulated", "qaoa_emulated", "qaoa_hardware"]
    size_order = ["big", "medium", "small"]
    row_by_case = {row["case_key"]: row for row in demo_rows if "case_key" in row}
    row_end = chr(92) * 2

    def pretty_method(method: str) -> str:
        return {
            "metis": "METIS",
            "qa_hardware": "QA hardware",
            "qa_emulated": "QA emulated",
            "qaoa_emulated": "QAOA emulated",
            "qaoa_hardware": "QAOA hardware",
        }.get(method, method)

    def fmt_sci(value: Any) -> str:
        if value is None:
            return "N/A"
        try:
            return f"{float(value):.2e}"
        except Exception:
            return "N/A"

    def infer_n(row: dict[str, Any]) -> int | None:
        if row.get("matrix_ncols"):
            return int(row["matrix_ncols"])
        res_dir = row.get("result_dir")
        if res_dir:
            metrics_path = ROOT_DIR / res_dir / "run_metrics.json"
            if metrics_path.exists():
                try:
                    m = json.loads(metrics_path.read_text(encoding="utf-8"))
                    n_val = m.get(prefix, {}).get("structural_metrics", {}).get("original", {}).get("n")
                    if n_val:
                        return int(n_val)
                except Exception:
                    pass
        return None

    table_rows = []
    for method in method_order:
        for size in size_order:
            case_key = f"{demonstrator}__{method}__{size}"
            row = row_by_case.get(case_key)
            if row is None:
                continue
            nnz_orig = row.get(f"{prefix}_nnz_original")
            nnz_perm = row.get(f"{prefix}_nnz_permuted")
            nnz_diff = abs(int(nnz_orig) - int(nnz_perm)) if nnz_orig is not None and nnz_perm is not None else None
            max_err = row.get(f"{prefix}_permutation_max_abs_err")
            bw_orig = row.get(f"{prefix}_bandwidth_original")
            bw_perm = row.get(f"{prefix}_bandwidth_permuted")
            n = infer_n(row)
            nb2_orig = float(n) * (float(bw_orig) ** 2) if n is not None and bw_orig is not None else None
            nb2_perm = float(n) * (float(bw_perm) ** 2) if n is not None and bw_perm is not None else None
            nb2_reduction = (
                100.0 * (nb2_orig - nb2_perm) / nb2_orig
                if nb2_orig is not None and nb2_perm is not None and nb2_orig != 0
                else None
            )
            table_rows.append(
                {
                    "method": pretty_method(method),
                    "size": size,
                    "nnz_diff": str(nnz_diff) if nnz_diff is not None else "N/A",
                    "max_err": str(max_err) if max_err is not None else "N/A",
                    "nB2_orig": fmt_sci(nb2_orig),
                    "nB2_perm": fmt_sci(nb2_perm),
                    "nB2_reduction": f"{nb2_reduction:.1f}\\%" if nb2_reduction is not None else "N/A",
                }
            )

    demo_suffix = "".join(ch for ch in demonstrator if ch.isdigit())
    demo_display = f"Demonstrator~{demo_suffix}" if demo_suffix else demonstrator
    demo_label = f"tab:results_demo{int(demo_suffix)}_{prefix.lower()}_nb2" if demo_suffix else f"tab:results_{prefix.lower()}_nb2"

    lines = [
        "\\begin{table}[H]",
        f"\\caption{{{prefix}-matrix $n B^2$ metrics for {demo_display}}}",
        "\\scriptsize",
        "\\renewcommand{\\arraystretch}{1.15}",
        "\\begin{tabularx}{\\textwidth}{X l r r r r r}",
        "\\toprule",
        "\\textbf{Method} & \\textbf{Size} & \\textbf{NNZ Diff} & \\textbf{Max Abs Err} & $n B^2_\\mathrm{original}$ & $n B^2_\\mathrm{permuted}$ & $n B^2$ \\% Reduction" + row_end,
        "\\midrule",
    ]
    for r in table_rows:
        lines.append(
            f"{r['method']} & {r['size']} & {r['nnz_diff']} & {r['max_err']} & {r['nB2_orig']} & {r['nB2_perm']} & {r['nB2_reduction']}" + row_end
        )
    lines.extend(
        [
            "\\bottomrule",
            "\\end{tabularx}",
            "\\centering",
            "Source: Author (2026)",
            f"\\label{{{demo_label}}}",
            "\\end{table}",
        ]
    )
    return lines

