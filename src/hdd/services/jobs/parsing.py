"""Reading job output: log levels and graph telemetry from the text of log lines.

Stage and progress come from structured events (``libs.runtime.events``), not from here.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

PIPELINE_STAGES = [
    {"id": "initialization", "label": "Graph Construction", "index": 0},
    {"id": "coarsening", "label": "Multilevel Coarsening (HEM)", "index": 1},
    {"id": "partitioning", "label": "Coarse Partitioning", "index": 2},
    {"id": "uncoarsening", "label": "Uncoarsening & Refinement", "index": 3},
    {"id": "permutation", "label": "Matrix Permutation & Profiling", "index": 4},
]

_INITIAL_GRAPH_RE = re.compile(r"Graph G with (\d+) nodes and (\d+) edges")
_COARSE_GRAPH_RE = re.compile(r"Coarse graph has (\d+) nodes and (\d+) edges with (\d+) levels")
_PARTS_RE = re.compile(r"Partitioning on coarse graph produced (\d+) parts")
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
