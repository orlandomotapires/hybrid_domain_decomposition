#!/usr/bin/env python3
"""Export a compact static demo snapshot (frontend/public/demo-snapshot.json) for GitHub Pages."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"
os.environ.setdefault("MPLCONFIGDIR", "/tmp")

for p in (str(ROOT_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.routes.matrices import get_parameter_preset, list_demonstrators
from backend.routes.batch import (
    get_batch_configuration,
    get_batch_run_detail,
    list_batch_runs,
)
from backend.routes.results import (
    get_batch_analysis,
    get_single_run_detail,
    list_demonstrator_runs,
)
from backend.routes.quantum_hw import get_environment_status


def main() -> None:
    dems = list_demonstrators()["demonstrators"]
    presets: dict[str, dict[str, dict]] = {}
    for d in dems:
        dem_id = d["id"]
        presets[dem_id] = {}
        for pf in d.get("preset_files", []):
            try:
                presets[dem_id][pf] = get_parameter_preset(dem_id, pf)
            except Exception:
                pass

    bcfg = get_batch_configuration()
    bruns = list_batch_runs()["batch_runs"]
    target_batch_id = "batch_20260521_151902"
    batch_details = {}
    batch_analysis = {}
    if any(b["id"] == target_batch_id for b in bruns):
        bdetail = get_batch_run_detail(target_batch_id)
        bdetail["log_tail"] = bdetail.get("log_tail", "")[-4000:]
        batch_details[target_batch_id] = bdetail
        batch_analysis[target_batch_id] = {
            d["id"]: get_batch_analysis(target_batch_id, d["id"]) for d in dems
        }

    dem_runs = {}
    run_details = {}
    for d in dems:
        dem_id = d["id"]
        r = list_demonstrator_runs(dem_id)
        valid_runs = [x for x in r["runs"] if x.get("kpi_summary")][:3]
        for vr in valid_runs:
            vr["can_render_plots"] = False
        dem_runs[dem_id] = {"demonstrator_id": dem_id, "runs": valid_runs}
        if valid_runs:
            d["runs_count"] = len(valid_runs)
            d["latest_run"] = valid_runs[0]["result_dir"]
        for vr in valid_runs:
            rd = get_single_run_detail(vr["result_dir"])
            rd["can_render_plots"] = False
            rd["available_plots"] = []
            rd.pop("run_metrics", None)
            rd.pop("run_metrics_txt", None)
            for m in ("K", "M"):
                pts = rd.get("curves", {}).get(m, [])
                if isinstance(pts, list) and len(pts) > 50:
                    step = max(1, len(pts) // 50)
                    sampled = pts[::step]
                    if sampled[-1] != pts[-1]:
                        sampled.append(pts[-1])
                    rd["curves"][m] = sampled
            run_details[vr["result_dir"]] = rd

    snap = {
        "demonstrators": dems,
        "presets": presets,
        "batch_config": bcfg,
        "batch_runs": [b for b in bruns if b["id"] == target_batch_id],
        "batch_details": batch_details,
        "batch_analysis": batch_analysis,
        "demonstrator_runs": dem_runs,
        "run_details": run_details,
        "hardware_status": get_environment_status(),
    }

    pub_dir = ROOT_DIR / "frontend" / "public"
    pub_dir.mkdir(parents=True, exist_ok=True)
    dst = pub_dir / "demo-snapshot.json"
    dst.write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {dst.relative_to(ROOT_DIR)} ({round(dst.stat().st_size / 1024, 1)} KB)")


if __name__ == "__main__":
    main()

