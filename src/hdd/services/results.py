"""Results of finished runs: listing, details, KPIs, curves, plots and export."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from libs.plotting import partition_plots
from libs.runtime import workspace

from .errors import InvalidInput, NotFound

AVAILABLE_CASE_PLOTS = partition_plots.CASE_PLOTS
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


# ----------------------------------------------------------------- paths
def resolve_result_dir(rel_path: str) -> Path:
    """Absolute path of a workspace-relative result folder. Rejects paths that leave the workspace."""
    normalized = rel_path.lstrip("/")
    if normalized.startswith("demonstrators/"):
        normalized = "matrices/" + normalized[len("demonstrators/"):].replace("demonstrator_", "matrix_")
    # Pre-simulations layout: matrices/matrix_NN/results/... now lives in simulations/simulation_NN/results/...
    legacy = re.match(r"^matrices/matrix_(\d+)/(results/.*)$", normalized)
    if legacy:
        normalized = f"simulations/simulation_{legacy.group(1)}/{legacy.group(2)}"
    try:
        return workspace.resolve_inside(normalized)
    except ValueError as exc:
        raise InvalidInput("Path must stay within the workspace") from exc


def _existing_result_dir(rel_path: str) -> Path:
    rdir = resolve_result_dir(rel_path)
    if not rdir.is_dir():
        raise NotFound(f"Result directory not found: {rel_path}")
    return rdir


def _safe_id(value: str, what: str) -> str:
    if not _RUN_ID_RE.match(value or "") or value in (".", ".."):
        raise InvalidInput(f"Invalid {what}: {value!r}")
    return value


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except Exception:
        return None


# --------------------------------------------------------------- metrics
def _percent_key(p: float) -> str:
    label = f"{p:.1f}%" if float(p).is_integer() else f"{p:.10f}".rstrip("0").rstrip(".") + "%"
    return f"frac_within_|i-j|<={label}_of_n"


def _structural(run_metrics: Any) -> tuple[dict, dict, dict]:
    block = run_metrics.get("matrix", {}) if isinstance(run_metrics, dict) else {}
    structural = block.get("structural_metrics", {}) if isinstance(block, dict) else {}
    orig = structural.get("original", {}) if isinstance(structural, dict) else {}
    perm = structural.get("permuted", {}) if isinstance(structural, dict) else {}
    return orig, perm, block.get("permutation_check", {}) if isinstance(block, dict) else {}


def extract_curve_series(run_metrics: dict[str, Any]) -> list[dict[str, float]]:
    """Share of nonzeros within a band around the diagonal, original vs permuted, for 0 to 5 % of n."""
    orig, perm, _ = _structural(run_metrics)
    if not orig and not perm:
        return []
    points = []
    for p in np.round(np.arange(0.0, 5.0, 0.05), 10):
        key = _percent_key(float(p))
        if key in orig or key in perm:
            points.append({"percent": float(p), "original": float(orig.get(key, 0.0)), "permuted": float(perm.get(key, 0.0))})
    return points


def extract_kpi_summary(run_metrics: dict[str, Any]) -> dict[str, Any]:
    """Bandwidth, average bandwidth, nB², band fractions and the permutation check, before and after."""
    orig, perm, perm_check = _structural(run_metrics)
    n = orig.get("n") or perm.get("n")
    bw_orig, bw_perm = orig.get("bandwidth"), perm.get("bandwidth")

    bw_reduction_pct = None
    if bw_orig and bw_perm is not None and float(bw_orig) > 0:
        bw_reduction_pct = 100.0 * (float(bw_orig) - float(bw_perm)) / float(bw_orig)
    nb2_orig = nb2_perm = nb2_reduction_pct = None
    if n is not None and bw_orig is not None and bw_perm is not None:
        nb2_orig, nb2_perm = float(n) * float(bw_orig) ** 2, float(n) * float(bw_perm) ** 2
        if nb2_orig > 0:
            nb2_reduction_pct = 100.0 * (nb2_orig - nb2_perm) / nb2_orig

    summary: dict[str, Any] = {
        "n": n,
        "nnz_original": orig.get("nnz"),
        "nnz_permuted": perm.get("nnz"),
        "bandwidth_original": bw_orig,
        "bandwidth_permuted": bw_perm,
        "bandwidth_reduction_pct": bw_reduction_pct,
        "avg_bandwidth_original": orig.get("avg_bandwidth"),
        "avg_bandwidth_permuted": perm.get("avg_bandwidth"),
        "nb2_original": nb2_orig,
        "nb2_permuted": nb2_perm,
        "nb2_reduction_pct": nb2_reduction_pct,
    }
    for pct in ("0.1", "0.4", "0.7", "1.0"):
        tag = pct.replace(".", "_")
        summary[f"frac_{tag}pct_original"] = orig.get(f"frac_within_|i-j|<={pct}%_of_n")
        summary[f"frac_{tag}pct_permuted"] = perm.get(f"frac_within_|i-j|<={pct}%_of_n")
    summary["permutation_check"] = perm_check
    return summary


# ------------------------------------------------------------------ runs
def scan_runs(results_dir: Path) -> list[Path]:
    """Run folders of a simulation, newest first."""
    if not results_dir.is_dir():
        return []
    return sorted((d for d in results_dir.iterdir() if d.is_dir() and d.name.startswith("run_")), key=lambda p: p.name, reverse=True)


_FAILURE_PREFIXES = ("Simulation failed: ",)


def run_outcome(rdir: Path, has_metrics: bool) -> tuple[str, str | None]:
    """``("completed" | "failed" | "incomplete", error)`` of a run folder, read from its metrics and log.

    ``error`` is the first error the run logged, without the generic "Simulation failed:" prefix.
    """
    if has_metrics:
        return "completed", None
    log_path = rdir / "run_log"
    if not log_path.exists():
        return "incomplete", None
    from hdd.services.jobs.parsing import parse_log_line

    finished = False
    for raw in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        entry = parse_log_line(raw)
        if entry["level"] == "ERROR":
            message = entry["message"].strip()
            for prefix in _FAILURE_PREFIXES:
                message = message.removeprefix(prefix)
            return "failed", message or "The run failed."
        if "Results saved in" in entry["message"] or "Completed Successfully" in entry["message"]:
            finished = True
    return ("completed" if finished else "incomplete"), None


def list_runs(simulation_id: str) -> dict[str, Any]:
    simulation_id = _safe_id(simulation_id, "simulation id")
    sim_dir = workspace.simulations_dir() / simulation_id
    if not sim_dir.exists():
        raise NotFound(f"Simulation {simulation_id!r} not found")
    runs = []
    for rdir in scan_runs(sim_dir / "results"):
        params = _read_json(rdir / "run_simulation_parameters.json") or {}
        metrics = _read_json(rdir / "run_metrics.json")
        pp, cp = params.get("partitioning_parameters", {}), params.get("coarsening_parameters", {})
        strategy = pp.get("partitioning_strategy", "unknown")
        strat_cfg = pp.get("strategies", {}).get(strategy, {})
        try:
            kpi = extract_kpi_summary(metrics) if metrics else None
        except Exception:
            kpi = None
        status, error = run_outcome(rdir, bool(metrics))
        runs.append(
            {
                "run_id": rdir.name,
                "result_dir": f"simulations/{simulation_id}/results/{rdir.name}",
                "demonstrator_id": simulation_id,
                "partitioning_strategy": strategy,
                "simulated": strat_cfg.get("simulated", True) if strategy != "metis_partitioning" else None,
                "k_target": pp.get("common", {}).get("k_target"),
                "coarsening_strategy": cp.get("strategy"),
                "coarsen_limits": [cp.get("coarsen_inferior_limit"), cp.get("coarsen_superior_limit")],
                "kpi_summary": kpi,
                "status": status,
                "error": error,
                "can_render_plots": partition_plots.can_plot(rdir),
            }
        )
    return {"demonstrator_id": simulation_id, "runs": runs}


def get_run_detail(result_dir: str) -> dict[str, Any]:
    rdir = _existing_result_dir(result_dir)
    run_metrics = _read_json(rdir / "run_metrics.json")
    metrics_txt = rdir / "run_metrics.txt"
    log_path = rdir / "run_log"
    status, error = run_outcome(rdir, bool(run_metrics))
    return {
        "result_dir": result_dir,
        "run_id": rdir.name,
        "status": status,
        "error": error,
        "run_parameters": _read_json(rdir / "run_simulation_parameters.json") or {},
        "kpi_summary": extract_kpi_summary(run_metrics) if run_metrics else None,
        "curves": extract_curve_series(run_metrics) if run_metrics else [],
        "run_metrics_txt": _read_own_text(metrics_txt),
        "run_log": _read_own_text(log_path),
        "artifacts": [f.name for f in sorted(rdir.iterdir()) if f.is_file()],
        "can_render_plots": partition_plots.can_plot(rdir),
        "available_plots": AVAILABLE_CASE_PLOTS,
    }


# ----------------------------------------------------------------- plots
def plot_spec(plot_name: str) -> dict[str, Any]:
    spec = next((item for item in AVAILABLE_CASE_PLOTS if item["id"] == plot_name), None)
    if spec is None:
        raise InvalidInput(f"Unsupported plot name: {plot_name}")
    return spec


def plot_data(result_dir: str, plot_name: str) -> partition_plots.PartitionPlotData:
    """Data of one canonical plot, for front ends that draw it themselves."""
    plot_spec(plot_name)
    rdir = _existing_result_dir(result_dir)
    if not partition_plots.can_plot(rdir):
        raise InvalidInput("This run did not save the files needed for plots (enable the matrix, permutation and graph outputs)")
    return partition_plots.case_plot_data(partition_plots.load_case(rdir), plot_name)


def render_plot_png(result_dir: str, plot_name: str, *, force: bool = False) -> Path:
    """PNG of one canonical plot, cached under ``<run>/plots/``."""
    spec = plot_spec(plot_name)
    rdir = _existing_result_dir(result_dir)
    out_file = rdir / "plots" / f"{plot_name}.png"
    if out_file.exists() and not force:
        return out_file
    data = plot_data(result_dir, plot_name)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        return partition_plots.render_png(data, out_file, show_y_axis=bool(spec["show_y_axis"]))
    except Exception as exc:
        raise InvalidInput(f"Plot rendering failed: {exc}") from exc


def _read_own_text(path: Path) -> str:
    """A run file's text; nothing for a missing file or a symlink (which may point anywhere)."""
    if path.is_symlink() or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def export_run_bundle(result_dir: str, destination) -> None:
    """Write a zip of the run (files plus cached plots under ``plots/``) to a path or binary stream."""
    rdir = _existing_result_dir(result_dir)
    with zipfile.ZipFile(destination, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # The pipeline never writes symlinks; one in a run folder (say, from a shared workspace)
        # could pull an unrelated file, such as a private key, into a bundle that gets sent away.
        for item in sorted(rdir.iterdir()):
            if item.is_symlink():
                continue
            if item.is_file():
                zf.write(item, arcname=item.name)
            elif item.is_dir() and item.name == "plots":
                for png in sorted(item.glob("*.png")):
                    if not png.is_symlink():
                        zf.write(png, arcname=f"plots/{png.name}")


# ----------------------------------------------------------------- batch
def batch_analysis(batch_id: str, matrix_id: str | None = None) -> dict[str, Any]:
    """Rows of one matrix in a batch and band-concentration curves per coarsening scale."""
    batch_id = _safe_id(batch_id, "batch id")
    summary = _read_json(workspace.batch_runs_dir() / batch_id / "batch_summary.json")
    if summary is None:
        raise NotFound(f"Batch summary not found for {batch_id!r}")
    all_rows = summary.get("rows", [])
    available = sorted({r.get("geometry") for r in all_rows if r.get("geometry")})
    matrix_id = matrix_id or (available[0] if available else "")
    rows = [r for r in all_rows if r.get("geometry") == matrix_id or str(r.get("case_key", "")).startswith(f"{matrix_id}__")]
    completed = [r for r in rows if r.get("status") == "completed"]

    present = {r.get("coarsening_size") for r in completed if r.get("coarsening_size")}
    scales = [s for s in ("small", "medium", "big") if s in present] + sorted(present - {"small", "medium", "big"})
    curves = []
    for size in scales:
        size_rows = [r for r in completed if r.get("coarsening_size") == size]
        points = []
        for pct in (0.0, 0.1, 0.4, 0.7, 1.0):
            point: dict[str, Any] = {"percent": pct}
            if pct == 0.0:
                point["Original"] = 0.0
                point.update({r["algorithm"]: 0.0 for r in size_rows})
            else:
                tag = str(pct).replace(".", "_")
                original = size_rows[0].get(f"frac_{tag}pct_original")
                if original is not None:
                    point["Original"] = float(original)
                for r in size_rows:
                    value = r.get(f"frac_{tag}pct_permuted")
                    if value is not None:
                        point[r["algorithm"]] = float(value)
            points.append(point)
        curves.append({"coarsening_size": size, "methods": [r["algorithm"] for r in size_rows], "points": points})

    return {
        "batch_id": batch_id,
        "demonstrator": matrix_id,
        "available_demonstrators": available,
        "rows": rows,
        "completed_rows": completed,
        "comparison_curves": curves,
    }
