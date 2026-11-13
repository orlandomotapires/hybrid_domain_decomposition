from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"

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


def _run_meta_from_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Extract display metadata (strategy, simulated flag, k_target) from simulation parameters."""
    meta: dict[str, Any] = {"partitioning_strategy": None, "simulated": None, "k_target": None}
    if not isinstance(params, dict):
        return meta
    try:
        pp = params.get("partitioning_parameters") or {}
        strat = pp.get("partitioning_strategy") or None
        meta["partitioning_strategy"] = strat
        if strat and strat != "metis_partitioning":
            sim = (pp.get("strategies") or {}).get(strat, {}).get("simulated")
            meta["simulated"] = bool(sim) if sim is not None else None
        k_t = (pp.get("common") or {}).get("k_target")
        if k_t is not None:
            meta["k_target"] = int(k_t)
    except Exception:
        pass
    return meta


def _load_params_file(demonstrator_dir: str, parameters_file: str | None) -> dict[str, Any] | None:
    """Best-effort load of the parameters file a live run will use (when no in-memory override)."""
    try:
        data_dir = ROOT_DIR / demonstrator_dir / "data"
        name = parameters_file
        if not name:
            cfg = json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8"))
            name = cfg.get("parameters_file_path") or "simulation_parameters.json"
        path = Path(name)
        if not path.is_absolute():
            path = data_dir / path
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@dataclass
class SimulationJob:
    job_id: str
    job_type: str  # "single" | "batch" | "tuning"
    title: str
    demonstrator_dir: str | None = None
    parameters_override: dict[str, Any] | None = None
    status: str = "running"  # "running" | "completed" | "failed" | "cancelled"
    current_stage: str = "initialization"
    stage_progress: int = 5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str | None = None
    started_epoch: float = field(default_factory=time.time)
    finished_epoch: float | None = None
    stage_started_epoch: float = field(default_factory=time.time)
    stage_durations_sec: dict[str, float] = field(default_factory=dict)
    result_dir: str | None = None
    batch_dir: str | None = None
    study_dir: str | None = None
    pid: int | None = None
    exit_code: int | None = None
    error_message: str | None = None
    logs: list[dict[str, Any]] = field(default_factory=list)
    telemetry: dict[str, Any] = field(default_factory=dict)
    demonstrator_id: str | None = None
    partitioning_strategy: str | None = None
    simulated: bool | None = None
    k_target: int | None = None
    _process: subprocess.Popen | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_dict(self, include_logs: bool = True, log_offset: int = 0) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            end_t = self.finished_epoch if self.finished_epoch is not None else now
            elapsed_sec = round(max(0.0, end_t - self.started_epoch), 2)

            durations = {k: round(v, 2) for k, v in self.stage_durations_sec.items()}
            if self.status == "running" and self.current_stage:
                live_stage_sec = max(0.0, now - self.stage_started_epoch)
                durations[self.current_stage] = round(
                    self.stage_durations_sec.get(self.current_stage, 0.0) + live_stage_sec,
                    2,
                )

            payload = {
                "job_id": self.job_id,
                "job_type": self.job_type,
                "title": self.title,
                "demonstrator_dir": self.demonstrator_dir,
                "demonstrator_id": self.demonstrator_id,
                "partitioning_strategy": self.partitioning_strategy,
                "simulated": self.simulated,
                "k_target": self.k_target,
                "status": self.status,
                "current_stage": self.current_stage,
                "stage_progress": self.stage_progress,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
                "elapsed_sec": elapsed_sec,
                "stage_durations_sec": durations,
                "result_dir": self.result_dir,
                "batch_dir": self.batch_dir,
                "study_dir": self.study_dir,
                "pid": self.pid,
                "exit_code": self.exit_code,
                "error_message": self.error_message,
                "telemetry": dict(self.telemetry),
                "log_count": len(self.logs),
            }
            if include_logs:
                payload["logs"] = self.logs[log_offset:]
            return payload


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, SimulationJob] = {}
        self._lock = threading.Lock()
        self._load_historical_runs()

    def _load_historical_runs(self) -> None:
        dem_root = ROOT_DIR / "simulations"
        if not dem_root.exists():
            return
        for dem_dir in sorted(dem_root.iterdir()):
            results_dir = dem_dir / "results"
            if not results_dir.is_dir():
                continue
            for run_dir in sorted(results_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue
                job_id = f"hist_{dem_dir.name}_{run_dir.name}"
                rel_res = f"simulations/{dem_dir.name}/results/{run_dir.name}"
                strategy_str = ""
                telemetry: dict[str, Any] = {}
                run_meta = _run_meta_from_params(None)

                params_file = run_dir / "run_simulation_parameters.json"
                if params_file.exists():
                    try:
                        p = json.loads(params_file.read_text(encoding="utf-8"))
                        run_meta = _run_meta_from_params(p)
                        strat = p.get("partitioning_parameters", {}).get("partitioning_strategy", "")
                        if strat:
                            strategy_str = f" ({strat})"
                        k_t = p.get("partitioning_parameters", {}).get("common", {}).get("k_target")
                        if k_t is not None:
                            telemetry["coarse_parts"] = int(k_t)
                    except Exception:
                        pass

                metrics_file = run_dir / "run_metrics.json"
                if metrics_file.exists():
                    try:
                        m = json.loads(metrics_file.read_text(encoding="utf-8"))
                        k_m = m.get("matrix", {})
                        fg = k_m.get("fine_graph_partition", {})
                        cg = k_m.get("coarse_graph_partition", {})
                        if fg.get("num_nodes") is not None:
                            telemetry["initial_nodes"] = int(fg["num_nodes"])
                            telemetry["initial_edges"] = int(fg.get("num_edges", 0))
                        if cg.get("num_nodes") is not None:
                            telemetry["coarse_nodes"] = int(cg["num_nodes"])
                            telemetry["coarse_edges"] = int(cg.get("num_edges", 0))
                        if cg.get("num_parts") is not None:
                            telemetry["coarse_parts"] = int(cg["num_parts"])
                    except Exception:
                        pass

                mtime = run_dir.stat().st_mtime
                created_iso = datetime.fromtimestamp(mtime).isoformat()
                default_hms = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")

                parsed_logs: list[dict[str, str]] = []
                has_error_log = False
                run_log_file = run_dir / "run_log"
                if run_log_file.exists():
                    try:
                        for raw_l in run_log_file.read_text(encoding="utf-8", errors="replace").splitlines():
                            if not raw_l.strip():
                                continue
                            entry = _parse_log_line(raw_l, default_hms=default_hms)
                            parsed_logs.append(entry)
                            if entry["level"] == "ERROR":
                                has_error_log = True
                            msg = entry["message"]
                            m_init = _INITIAL_GRAPH_RE.search(msg)
                            if m_init:
                                telemetry["initial_nodes"] = int(m_init.group(1))
                                telemetry["initial_edges"] = int(m_init.group(2))
                            m_coarse = _COARSE_GRAPH_RE.search(msg)
                            if m_coarse:
                                telemetry["coarse_nodes"] = int(m_coarse.group(1))
                                telemetry["coarse_edges"] = int(m_coarse.group(2))
                                telemetry["coarsening_levels"] = int(m_coarse.group(3))
                            m_parts = _PARTS_RE.search(msg)
                            if m_parts:
                                telemetry["coarse_parts"] = int(m_parts.group(1))
                    except Exception:
                        pass

                if not parsed_logs:
                    parsed_logs = [
                        {
                            "timestamp": default_hms,
                            "level": "INFO",
                            "message": f"Loaded historical run from {rel_res}",
                        }
                    ]

                status_val = "failed" if (has_error_log and not metrics_file.exists()) else "completed"
                job = SimulationJob(
                    job_id=job_id,
                    job_type="single",
                    title=f"{dem_dir.name}{strategy_str}",
                    demonstrator_dir=f"simulations/{dem_dir.name}",
                    status=status_val,
                    current_stage="permutation" if status_val == "completed" else "initialization",
                    stage_progress=100 if status_val == "completed" else 15,
                    created_at=created_iso,
                    finished_at=created_iso,
                    started_epoch=mtime,
                    finished_epoch=mtime,
                    result_dir=rel_res if status_val == "completed" else None,
                    exit_code=0 if status_val == "completed" else 1,
                    telemetry=telemetry,
                    logs=parsed_logs,
                    demonstrator_id=dem_dir.name,
                    **run_meta,
                )
                self._jobs[job_id] = job

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict(include_logs=False) for j in jobs[:40]]

    def get_job(self, job_id: str, log_offset: int = 0) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        return job.to_dict(include_logs=True, log_offset=log_offset)

    def delete_job(self, job_id: str, delete_files: bool = False) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status == "running":
                return False
            del self._jobs[job_id]

        if delete_files and job.result_dir:
            target = (ROOT_DIR / job.result_dir).resolve()
            try:
                target.relative_to((ROOT_DIR / "simulations").resolve())
                if target.exists() and target.is_dir() and target.name.startswith("run_"):
                    shutil.rmtree(target)
            except Exception:
                pass
        return True

    def start_single_simulation(
        self,
        demonstrator_dir: str,
        *,
        parameters_override: dict[str, Any] | None = None,
        parameters_file_override: str | None = None,
    ) -> dict[str, Any]:
        job_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        dem_name = demonstrator_dir.strip("/").split("/")[-1]
        strategy = ""
        if parameters_override and "partitioning_parameters" in parameters_override:
            strategy = f" ({parameters_override['partitioning_parameters'].get('partitioning_strategy', '')})"

        run_meta = _run_meta_from_params(
            parameters_override
            if parameters_override is not None
            else _load_params_file(demonstrator_dir, parameters_file_override)
        )

        now_t = time.time()
        job = SimulationJob(
            job_id=job_id,
            job_type="single",
            title=f"Simulation: {dem_name}{strategy}",
            demonstrator_dir=demonstrator_dir,
            demonstrator_id=dem_name,
            **run_meta,
            parameters_override=parameters_override,
            started_epoch=now_t,
            stage_started_epoch=now_t,
        )

        with self._lock:
            self._jobs[job_id] = job

        runner_code = (
            "import sys, json\n"
            f"sys.path.insert(0, {str(SRC_DIR)!r})\n"
            "from libs.runtime.runtime import run_simulation\n"
            "from libs.runtime.log import log, close_log_file\n"
            "import traceback\n"
            "payload = json.loads(sys.argv[1])\n"
            "try:\n"
            "    out_dir = run_simulation(\n"
            "        payload['demonstrator_dir'],\n"
            "        parameters_file_override=payload.get('parameters_file_override'),\n"
            "        simulation_parameters_override=payload.get('parameters_override'),\n"
            "    )\n"
            "    log('INFO', 'Simulation Completed Successfully')\n"
            "    log('VERBOSE', f'Results saved in {out_dir}')\n"
            "except Exception as exc:\n"
            "    log('ERROR', f'Simulation failed: {exc}')\n"
            "    for line in traceback.format_exc().splitlines():\n"
            "        log('ERROR', line)\n"
            "    sys.exit(1)\n"
            "finally:\n"
            "    close_log_file()\n"
        )

        arg_payload = json.dumps(
            {
                "demonstrator_dir": demonstrator_dir,
                "parameters_file_override": parameters_file_override,
                "parameters_override": parameters_override,
            }
        )

        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", runner_code, arg_payload],
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
            env=env,
        )
        job._process = proc
        job.pid = proc.pid

        thread = threading.Thread(
            target=self._consume_process_output,
            args=(job,),
            daemon=True,
        )
        thread.start()

        return job.to_dict(include_logs=True)

    def start_batch_study(
        self,
        *,
        stop_on_error: bool = False,
    ) -> dict[str, Any]:
        job_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        batch_dir_rel = f"batch/runs/batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        batch_dir = ROOT_DIR / batch_dir_rel
        batch_dir.mkdir(parents=True, exist_ok=True)

        now_t = time.time()
        job = SimulationJob(
            job_id=job_id,
            job_type="batch",
            title=f"Batch Study ({batch_dir.name})",
            batch_dir=batch_dir_rel,
            current_stage="initialization",
            started_epoch=now_t,
            stage_started_epoch=now_t,
        )

        with self._lock:
            self._jobs[job_id] = job

        cmd = [sys.executable, "-u", str(ROOT_DIR / "batch" / "run_batch.py")]
        if stop_on_error:
            cmd.append("--stop-on-error")

        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["HDD_BATCH_DIR"] = batch_dir_rel

        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
            env=env,
        )
        job._process = proc
        job.pid = proc.pid

        thread = threading.Thread(
            target=self._consume_process_output,
            args=(job,),
            daemon=True,
        )
        thread.start()

        return job.to_dict(include_logs=True)

    def start_tuning_study(self, *, study_dir: Path, title: str, demonstrator_id: str | None = None) -> dict[str, Any]:
        """Run ``libs.tuning.cli --resume <study_dir>`` as a background job."""
        try:
            study_dir_rel = str(study_dir.resolve().relative_to(ROOT_DIR))
        except ValueError:
            study_dir_rel = str(study_dir)
        job_id = f"tuning_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_t = time.time()
        job = SimulationJob(
            job_id=job_id,
            job_type="tuning",
            title=title,
            study_dir=study_dir_rel,
            demonstrator_id=demonstrator_id,
            current_stage="initialization",
            stage_progress=0,
            started_epoch=now_t,
            stage_started_epoch=now_t,
        )
        with self._lock:
            self._jobs[job_id] = job

        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "libs.tuning.cli", "--resume", str(study_dir.resolve())],
            cwd=str(SRC_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
            env=env,
        )
        job._process = proc
        job.pid = proc.pid
        threading.Thread(target=self._consume_process_output, args=(job,), daemon=True).start()
        return job.to_dict(include_logs=True)

    @staticmethod
    def _update_tuning_progress(job: SimulationJob, message: str) -> None:
        """Track tuning trial progress (caller holds job._lock)."""
        t = job.telemetry
        m_study = _TUNING_STUDY_RE.search(message)
        if m_study:
            t["tuning_total"] = int(m_study.group(2))
            t.setdefault("tuning_done", 0)
            return
        m_trial = _TUNING_TRIAL_RE.search(message)
        if m_trial:
            done, total, status = int(m_trial.group(1)), int(m_trial.group(2)), m_trial.group(3)
            t["tuning_done"], t["tuning_total"] = done, total
            key = f"tuning_{status}"
            t[key] = int(t.get(key, 0)) + 1
            job.stage_progress = min(99, int(100 * done / max(total, 1)))

    def cancel_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None

        proc = job._process
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass

        with job._lock:
            if job.status == "running":
                now_t = time.time()
                if job.current_stage:
                    job.stage_durations_sec[job.current_stage] = (
                        job.stage_durations_sec.get(job.current_stage, 0.0)
                        + max(0.0, now_t - job.stage_started_epoch)
                    )
                job.status = "cancelled"
                job.finished_epoch = now_t
                job.finished_at = datetime.now().isoformat()
                job.logs.append(
                    {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "level": "WARNING",
                        "message": "Job cancelled by user.",
                    }
                )
        return job.to_dict(include_logs=True)

    @staticmethod
    def _update_batch_progress(job: SimulationJob, message: str) -> None:
        """Track batch case progress (caller holds job._lock)."""
        t = job.telemetry
        m_prep = _BATCH_PREPARED_RE.search(message)
        if m_prep:
            t["batch_total"] = int(m_prep.group(1))
            t.setdefault("batch_done", 0)
            t.setdefault("batch_failed", 0)
            return
        m_case = _BATCH_CASE_RE.search(message)
        if m_case:
            t["batch_index"] = int(m_case.group(1))
            t["batch_total"] = int(m_case.group(2))
            t["batch_case"] = m_case.group(3)
            return
        m_done = _BATCH_CASE_DONE_RE.search(message)
        if m_done:
            t["batch_done"] = int(t.get("batch_done", 0)) + 1
            if m_done.group(1) == "FAILED":
                t["batch_failed"] = int(t.get("batch_failed", 0)) + 1

    def _consume_process_output(self, job: SimulationJob) -> None:
        proc = job._process
        if proc is None or proc.stdout is None:
            return

        stage_map = {s["id"]: s["index"] for s in PIPELINE_STAGES}

        for raw_line in proc.stdout:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue

            entry = _parse_log_line(line)
            level = entry["level"]
            message = entry["message"]

            with job._lock:
                now_t = time.time()
                job.logs.append(entry)

                for pattern, stage_id in ([] if job.job_type == "tuning" else _STAGE_PATTERNS):
                    if re.search(pattern, message):
                        if stage_id != job.current_stage:
                            prev_stage = job.current_stage
                            if prev_stage:
                                job.stage_durations_sec[prev_stage] = (
                                    job.stage_durations_sec.get(prev_stage, 0.0)
                                    + max(0.0, now_t - job.stage_started_epoch)
                                )
                            job.current_stage = stage_id
                            job.stage_started_epoch = now_t
                        idx = stage_map.get(stage_id, 0)
                        job.stage_progress = min(95, int((idx + 1) * 18))
                        break

                m_init = _INITIAL_GRAPH_RE.search(message)
                if m_init:
                    job.telemetry["initial_nodes"] = int(m_init.group(1))
                    job.telemetry["initial_edges"] = int(m_init.group(2))

                m_coarse = _COARSE_GRAPH_RE.search(message)
                if m_coarse:
                    job.telemetry["coarse_nodes"] = int(m_coarse.group(1))
                    job.telemetry["coarse_edges"] = int(m_coarse.group(2))
                    job.telemetry["coarsening_levels"] = int(m_coarse.group(3))

                m_parts = _PARTS_RE.search(message)
                if m_parts:
                    job.telemetry["coarse_parts"] = int(m_parts.group(1))

                if job.job_type == "batch":
                    self._update_batch_progress(job, message)
                elif job.job_type == "tuning":
                    self._update_tuning_progress(job, message)

                m_res = _RESULTS_SAVED_RE.search(message)
                if m_res:
                    raw_path = Path(m_res.group(1).strip())
                    try:
                        job.result_dir = str(raw_path.resolve().relative_to(ROOT_DIR))
                    except ValueError:
                        job.result_dir = str(raw_path)

                # Tuning trials may fail individually; only the exit code decides the job status.
                if level == "ERROR" and job.error_message is None and job.job_type != "tuning":
                    job.error_message = message

        exit_code = proc.wait()
        with job._lock:
            now_t = time.time()
            if job.current_stage:
                job.stage_durations_sec[job.current_stage] = (
                    job.stage_durations_sec.get(job.current_stage, 0.0)
                    + max(0.0, now_t - job.stage_started_epoch)
                )
            job.exit_code = exit_code
            job.pid = None
            job.finished_epoch = now_t
            job.finished_at = datetime.now().isoformat()
            if job.status == "cancelled":
                return
            if exit_code == 0:
                job.status = "completed"
                job.stage_progress = 100
            else:
                job.status = "failed"


job_manager = JobManager()
