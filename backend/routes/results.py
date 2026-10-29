from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
import zipfile
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from backend.services.plot_service import (
    AVAILABLE_CASE_PLOTS,
    build_nb2_latex_lines,
    extract_curve_series,
    extract_kpi_summary,
    render_or_get_cached_plot,
)
import notebook_functions as nf

router = APIRouter(prefix="/api/results", tags=["results"])

ROOT_DIR = Path(__file__).resolve().parents[2]
DEMONSTRATORS_ROOT = ROOT_DIR / "matrices"
BATCH_RUNS_DIR = ROOT_DIR / "batch" / "runs"


def _safe_resolve_inside_repo(rel_path: str) -> Path:
    normalized = rel_path.lstrip("/")
    if normalized.startswith("demonstrators/"):
        normalized = "matrices/" + normalized[len("demonstrators/"):].replace("demonstrator_", "matrix_")
    resolved = (ROOT_DIR / normalized).resolve()
    try:
        resolved.relative_to(ROOT_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path must stay within repository root") from exc
    return resolved


@router.get("/demonstrators/{dem_id}/runs")
def list_demonstrator_runs(dem_id: str) -> dict[str, Any]:
    dem_dir = DEMONSTRATORS_ROOT / dem_id
    if not dem_dir.exists():
        raise HTTPException(status_code=404, detail=f"Matrix workspace {dem_id!r} not found")

    results_dir = dem_dir / "results"
    runs: list[dict[str, Any]] = []

    if results_dir.exists() and results_dir.is_dir():
        for rdir in sorted(
            [d for d in results_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
            key=lambda p: p.name,
            reverse=True,
        ):
            rel_dir = f"matrices/{dem_id}/results/{rdir.name}"
            params_path = rdir / "run_simulation_parameters.json"
            metrics_path = rdir / "run_metrics.json"
            params = {}
            metrics = None
            kpi = None
            if params_path.exists():
                try:
                    params = json.loads(params_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if metrics_path.exists():
                try:
                    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                    kpi = extract_kpi_summary(metrics)
                except Exception:
                    pass

            pp = params.get("partitioning_parameters", {})
            cp = params.get("coarsening_parameters", {})
            strategy = pp.get("partitioning_strategy", "unknown")
            strat_cfg = pp.get("strategies", {}).get(strategy, {})

            runs.append(
                {
                    "run_id": rdir.name,
                    "result_dir": rel_dir,
                    "demonstrator_id": dem_id,
                    "partitioning_strategy": strategy,
                    "simulated": strat_cfg.get("simulated", True) if strategy != "metis_partitioning" else None,
                    "k_target": pp.get("common", {}).get("k_target"),
                    "coarsening_strategy": cp.get("strategy"),
                    "coarsen_limits": [cp.get("coarsen_inferior_limit"), cp.get("coarsen_superior_limit")],
                    "kpi_summary": kpi,
                    "can_render_plots": (rdir / "partition_artifacts.json").exists()
                    and (rdir / "matrix_k_permuted.mtx").exists(),
                }
            )

    return {"demonstrator_id": dem_id, "runs": runs}


@router.get("/run-detail")
def get_single_run_detail(result_dir: str = Query(..., description="Relative path to run result directory")) -> dict[str, Any]:
    rdir = _safe_resolve_inside_repo(result_dir)
    if not rdir.exists() or not rdir.is_dir():
        raise HTTPException(status_code=404, detail=f"Result directory not found: {result_dir}")

    metrics_path = rdir / "run_metrics.json"
    metrics_txt_path = rdir / "run_metrics.txt"
    params_path = rdir / "run_simulation_parameters.json"
    log_path = rdir / "run_log"

    run_metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
    run_params = json.loads(params_path.read_text(encoding="utf-8")) if params_path.exists() else {}
    metrics_txt = metrics_txt_path.read_text(encoding="utf-8", errors="ignore") if metrics_txt_path.exists() else ""
    run_log = log_path.read_text(encoding="utf-8", errors="ignore") if log_path.exists() else ""

    kpi_summary = extract_kpi_summary(run_metrics) if run_metrics else None
    curves = (
        {
            "K": extract_curve_series(run_metrics, "K"),
            "M": extract_curve_series(run_metrics, "M"),
        }
        if run_metrics
        else {"K": [], "M": []}
    )

    artifacts = [f.name for f in sorted(rdir.iterdir()) if f.is_file()]
    can_render = (
        (rdir / "partition_artifacts.json").exists()
        and (rdir / "coarsened_graph.mtx").exists()
        and (rdir / "matrix_k_permuted.mtx").exists()
        and (rdir / "permutation.txt").exists()
    )

    return {
        "result_dir": result_dir,
        "run_id": rdir.name,
        "run_parameters": run_params,
        "kpi_summary": kpi_summary,
        "curves": curves,
        "run_metrics_txt": metrics_txt,
        "run_log": run_log,
        "artifacts": artifacts,
        "can_render_plots": can_render,
        "available_plots": AVAILABLE_CASE_PLOTS,
    }


@router.get("/plot-image")
def get_case_plot_image(
    result_dir: str = Query(...),
    plot_name: str = Query(...),
    force: bool = Query(False),
) -> FileResponse:
    _safe_resolve_inside_repo(result_dir)
    try:
        img_path = render_or_get_cached_plot(result_dir, plot_name, force_rerender=force)
        return FileResponse(img_path, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Plot rendering failed: {exc}") from exc


@router.get("/download-bundle")
def download_run_bundle(result_dir: str = Query(...)) -> StreamingResponse:
    rdir = _safe_resolve_inside_repo(result_dir)
    if not rdir.exists() or not rdir.is_dir():
        raise HTTPException(status_code=404, detail=f"Result directory not found: {result_dir}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(rdir.iterdir()):
            if item.is_file():
                zf.write(item, arcname=item.name)
            elif item.is_dir() and item.name == ".plot_cache":
                for png in sorted(item.glob("*.png")):
                    zf.write(png, arcname=f"plots/{png.name}")

    buf.seek(0)
    filename = f"{rdir.name}_bundle.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/batch/{batch_id}/analysis")
def get_batch_analysis(
    batch_id: str,
    demonstrator: str = Query("matrix_01"),
) -> dict[str, Any]:
    bdir = BATCH_RUNS_DIR / batch_id
    summary_path = bdir / "batch_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail=f"Batch summary not found for {batch_id!r}")

    batch_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    all_rows = batch_summary.get("rows", [])
    available_demonstrators = sorted({r.get("geometry") for r in all_rows if r.get("geometry")})

    demo_rows = [
        r
        for r in all_rows
        if r.get("geometry") == demonstrator or str(r.get("case_key", "")).startswith(f"{demonstrator}__")
    ]
    completed_demo_rows = [r for r in demo_rows if r.get("status") == "completed"]

    demo_suffix = "".join(ch for ch in demonstrator if ch.isdigit())

    latex_k_summary = (
        "\n".join(nf.build_matrix_summary_lines("K", demonstrator, completed_demo_rows, demo_suffix=demo_suffix))
        if completed_demo_rows
        else ""
    )
    latex_m_summary = (
        "\n".join(nf.build_matrix_summary_lines("M", demonstrator, completed_demo_rows, demo_suffix=demo_suffix))
        if completed_demo_rows
        else ""
    )
    latex_k_nb2 = (
        "\n".join(build_nb2_latex_lines("K", demonstrator, completed_demo_rows))
        if completed_demo_rows
        else ""
    )
    latex_m_nb2 = (
        "\n".join(build_nb2_latex_lines("M", demonstrator, completed_demo_rows))
        if completed_demo_rows
        else ""
    )

    # Build multi-method curve comparison data (uses full 100-point curve if run_metrics.json is on disk,
    # or the 5 summary bands [0%, 0.1%, 0.4%, 0.7%, 1.0%] from batch_summary.json)
    comparison_curves: dict[str, list[dict[str, Any]]] = {"K": [], "M": []}
    for mat_prefix in ("K", "M"):
        for size in ("small", "medium", "big"):
            size_rows = [r for r in completed_demo_rows if r.get("coarsening_size") == size]
            if not size_rows:
                continue

            # Check if full run_metrics.json exists for all size_rows
            band_points = [0.0, 0.1, 0.4, 0.7, 1.0]
            series_points: list[dict[str, Any]] = []
            first_row = size_rows[0]

            for pct in band_points:
                pt: dict[str, Any] = {"percent": pct}
                if pct == 0.0:
                    pt["Original"] = 0.0
                    for r in size_rows:
                        pt[r["algorithm"]] = 0.0
                else:
                    pct_key = str(pct).replace(".", "_")
                    orig_val = first_row.get(f"{mat_prefix}_frac_{pct_key}pct_original")
                    if orig_val is not None:
                        pt["Original"] = float(orig_val)
                    for r in size_rows:
                        perm_val = r.get(f"{mat_prefix}_frac_{pct_key}pct_permuted")
                        if perm_val is not None:
                            pt[r["algorithm"]] = float(perm_val)
                series_points.append(pt)

            comparison_curves[mat_prefix].append(
                {
                    "coarsening_size": size,
                    "methods": [r["algorithm"] for r in size_rows],
                    "points": series_points,
                }
            )

    return {
        "batch_id": batch_id,
        "demonstrator": demonstrator,
        "available_demonstrators": available_demonstrators,
        "rows": demo_rows,
        "completed_rows": completed_demo_rows,
        "comparison_curves": comparison_curves,
        "latex_tables": {
            "k_summary": latex_k_summary,
            "m_summary": latex_m_summary,
            "k_nb2": latex_k_nb2,
            "m_nb2": latex_m_nb2,
        },
    }
