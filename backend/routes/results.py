"""Results API. Thin adapter over ``hdd.services.results``."""

from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, StreamingResponse

from hdd.services import results

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("/demonstrators/{dem_id}/runs")
def list_demonstrator_runs(dem_id: str) -> dict[str, Any]:
    return results.list_runs(dem_id)


@router.get("/run-detail")
def get_single_run_detail(result_dir: str = Query(..., description="Workspace-relative path of the run folder")) -> dict[str, Any]:
    return results.get_run_detail(result_dir)


@router.get("/plot-image")
def get_case_plot_image(result_dir: str = Query(...), plot_name: str = Query(...), force: bool = Query(False)) -> FileResponse:
    return FileResponse(results.render_plot_png(result_dir, plot_name, force=force), media_type="image/png")


@router.get("/download-bundle")
def download_run_bundle(result_dir: str = Query(...)) -> StreamingResponse:
    buffer = io.BytesIO()
    results.export_run_bundle(result_dir, buffer)
    buffer.seek(0)
    name = results.resolve_result_dir(result_dir).name
    return StreamingResponse(
        buffer, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}_bundle.zip"'}
    )


@router.get("/batch/{batch_id}/analysis")
def get_batch_analysis(batch_id: str, demonstrator: str | None = Query(None)) -> dict[str, Any]:
    return results.batch_analysis(batch_id, demonstrator)
