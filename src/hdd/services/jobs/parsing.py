"""Reading job output: log levels, pipeline stage, telemetry and progress.

Jobs report through their log text; this module is the only place that knows its wording.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from libs.runtime import workspace

PIPELINE_STAGES = [
    {"id": "initialization", "label": "Graph Construction", "index": 0},
    {"id": "coarsening", "label": "Multilevel Coarsening (HEM)", "index": 1},
    {"id": "partitioning", "label": "Coarse Partitioning", "index": 2},
    {"id": "uncoarsening", "label": "Uncoarsening & Refinement", "index": 3},
    {"id": "permutation", "label": "Matrix Permutation & Profiling", "index": 4},
]

_STAGE_PATTERNS: list[tuple[str, str]] = [
    (r"Converting matrix to graph|Graph G with", "initialization"),
    (r"Coarsening Heavy Edge Matching|Coarse graph has", "coarsening"),
    (
        r"Multilevel Partitioning Scheme using METIS|Running simulated quantum annealing|"
        r"Running quantum annealing|Partitioning QAOA|Running QAOA on|Partitioning on coarse graph",
        "partitioning",
    ),
    (r"Uncoarsening Kernighan-Lin", "uncoarsening"),
    (r"Permuting matrix|Permutation check", "permutation"),
]

_INITIAL_GRAPH_RE = re.compile(r"Graph G with (\d+) nodes and (\d+) edges")
_COARSE_GRAPH_RE = re.compile(r"Coarse graph has (\d+) nodes and (\d+) edges with (\d+) levels")
_PARTS_RE = re.compile(r"Partitioning on coarse graph produced (\d+) parts")
_RESULTS_SAVED_RE = re.compile(r"Results saved in (.+)$")
_BATCH_PREPARED_RE = re.compile(r"^Prepared (\d+) batch cases")
_BATCH_CASE_RE = re.compile(r"^\[(\d+)/(\d+)\] Running (\S+)")
_BATCH_CASE_DONE_RE = re.compile(r"^\s+(Result|FAILED):")
_TUNING_TRIAL_RE = re.compile(r"\[tuning\] trial (\d+)/(\d+) status=(\w+)")
_TUNING_STUDY_RE = re.compile(r"\[tuning\] study (\S+): (\d+) trials")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_BRACKET_LOG_RE = re.compile(
    r"^\[(?:(?P<date_prefix>.*?\b(?P<hms>\d{2}:\d{2}:\d{2})\b[^\]]*?)\s+)?(?P<level>INFO|VERBOSE|WARNING|ERROR)\]\s*(?P<msg>.*)$"
)


# "FAILED:", "failed", "ValueError:", "Traceback", "error:" — but not "0 failed" / "no failed".
_ERROR_TEXT_RE = re.compile(
    r"(?i)(?<!\b0 )(?<!\bno )\bfail(?:ed|ure|s)?\b|^\s*error\b|^\s*\w*(?:Error|Exception)\s*:|traceback \(most recent call last\)"
)
# "warning:", "UserWarning:", "PennyLaneDeprecationWarning:", and the "warnings.warn(" echo line.
_WARNING_TEXT_RE = re.compile(r"(?i)^\s*warning\b|\w*Warning:|^\s*warnings\.warn\(")


def _parse_log_line(raw_line: str, default_hms: str | None = None) -> dict[str, str]:
    clean = _ANSI_ESCAPE_RE.sub("", raw_line).rstrip("\r\n")
    hms = default_hms or datetime.now().strftime("%H:%M:%S")
    level = "INFO"
    message = clean

    m = _BRACKET_LOG_RE.match(clean)
    if m:
        if m.group("hms"):
            hms = m.group("hms")
        level = m.group("level").upper()
        message = m.group("msg").strip()

    # Escalate by content: a line that reports a failure is an ERROR even when the
    # emitting logger tagged it INFO (e.g. batch "  FAILED: ValueError: ...").
    if level in ("INFO", "VERBOSE"):
        if _ERROR_TEXT_RE.search(message):
            level = "ERROR"
        elif _WARNING_TEXT_RE.search(message):
            level = "WARNING"

    return {
        "timestamp": hms,
        "level": level,
        "message": message,
    }


def parse_log_line(raw_line: str, default_hms: str | None = None) -> dict[str, str]:
    """``{"timestamp", "level", "message"}`` of one output line, escalating by content."""
    return _parse_log_line(raw_line, default_hms)


STAGE_INDEX = {s["id"]: s["index"] for s in PIPELINE_STAGES}


def update_telemetry(telemetry: dict[str, Any], message: str) -> None:
    """Graph sizes reported by a pipeline run."""
    m_init = _INITIAL_GRAPH_RE.search(message)
    if m_init:
        telemetry["initial_nodes"] = int(m_init.group(1))
        telemetry["initial_edges"] = int(m_init.group(2))
    m_coarse = _COARSE_GRAPH_RE.search(message)
    if m_coarse:
        telemetry["coarse_nodes"] = int(m_coarse.group(1))
        telemetry["coarse_edges"] = int(m_coarse.group(2))
        telemetry["coarsening_levels"] = int(m_coarse.group(3))
    m_parts = _PARTS_RE.search(message)
    if m_parts:
        telemetry["coarse_parts"] = int(m_parts.group(1))


def detect_stage(message: str) -> str | None:
    for pattern, stage_id in _STAGE_PATTERNS:
        if re.search(pattern, message):
            return stage_id
    return None


def update_batch_progress(telemetry: dict[str, Any], message: str) -> None:
    m_prep = _BATCH_PREPARED_RE.search(message)
    if m_prep:
        telemetry["batch_total"] = int(m_prep.group(1))
        telemetry.setdefault("batch_done", 0)
        telemetry.setdefault("batch_failed", 0)
        return
    m_case = _BATCH_CASE_RE.search(message)
    if m_case:
        telemetry["batch_index"] = int(m_case.group(1))
        telemetry["batch_total"] = int(m_case.group(2))
        telemetry["batch_case"] = m_case.group(3)
        return
    m_done = _BATCH_CASE_DONE_RE.search(message)
    if m_done:
        telemetry["batch_done"] = int(telemetry.get("batch_done", 0)) + 1
        if m_done.group(1) == "FAILED":
            telemetry["batch_failed"] = int(telemetry.get("batch_failed", 0)) + 1


def update_tuning_progress(telemetry: dict[str, Any], message: str) -> int | None:
    """Update trial counters; return the new progress percentage when a trial finished."""
    m_study = _TUNING_STUDY_RE.search(message)
    if m_study:
        telemetry["tuning_total"] = int(m_study.group(2))
        telemetry.setdefault("tuning_done", 0)
        return None
    m_trial = _TUNING_TRIAL_RE.search(message)
    if m_trial:
        done, total, status = int(m_trial.group(1)), int(m_trial.group(2)), m_trial.group(3)
        telemetry["tuning_done"], telemetry["tuning_total"] = done, total
        key = f"tuning_{status}"
        telemetry[key] = int(telemetry.get(key, 0)) + 1
        return min(99, int(100 * done / max(total, 1)))
    return None


def result_dir_from(message: str) -> str | None:
    """Workspace-relative result folder announced by a finished single run."""
    m_res = _RESULTS_SAVED_RE.search(message)
    if not m_res:
        return None
    return workspace.rel(Path(m_res.group(1).strip()))
