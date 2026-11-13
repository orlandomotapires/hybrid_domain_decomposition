"""The job manager: starts jobs as child processes, follows their output and keeps their records.

Thread model: one reader thread per running job parses its output under the job's
lock. Listeners registered with :meth:`JobManager.subscribe` are called with
``(event, job_id)`` from those threads, outside every lock; they should only
note the change and let their own thread pull the state with :meth:`get_job`.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from libs.runtime import workspace

from . import commands, parsing
from .parsing import _parse_log_line
from .store import JobStore

Listener = Callable[[str, str], None]
CommandFactory = Callable[[str, list[str]], list[str]]
EVENTS = ("added", "changed", "finished", "removed")
MAX_LOG_ENTRIES = 50_000
INTERRUPTED_MESSAGE = "Interrupted: the Studio was closed while this job was running."
# Fields written to a job record (everything else is runtime state).
_RECORD_EXCLUDE = {"logs", "parameters_override"}


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


def _load_params_file(root: Path, demonstrator_dir: str, parameters_file: str | None) -> dict[str, Any] | None:
    """Best-effort load of the parameters file a live run will use (when no in-memory override)."""
    try:
        data_dir = root / demonstrator_dir / "data"
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
    log_path: str | None = None  # workspace-relative file holding the raw output
    logs_dropped: int = 0  # entries removed from the head of ``logs`` to bound memory
    _process: subprocess.Popen | None = field(default=None, repr=False)
    _logs_loaded: bool = field(default=True, repr=False)
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
                "log_count": self.logs_dropped + len(self.logs),
            }
            if include_logs:
                payload["logs"] = self.logs[max(0, log_offset - self.logs_dropped):]
            return payload

    def append_log(self, entry: dict[str, Any]) -> None:
        """Append under the caller's lock, keeping at most ``MAX_LOG_ENTRIES`` in memory."""
        self.logs.append(entry)
        overflow = len(self.logs) - MAX_LOG_ENTRIES
        if overflow > 0:
            del self.logs[:overflow]
            self.logs_dropped += overflow

    def close_stage(self, now: float) -> None:
        if self.current_stage:
            self.stage_durations_sec[self.current_stage] = self.stage_durations_sec.get(self.current_stage, 0.0) + max(
                0.0, now - self.stage_started_epoch
            )

    def to_record(self) -> dict[str, Any]:
        with self._lock:
            return {f.name: getattr(self, f.name) for f in fields(self) if not f.name.startswith("_") and f.name not in _RECORD_EXCLUDE}

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "SimulationJob":
        known = {f.name for f in fields(cls) if not f.name.startswith("_")}
        job = cls(**{k: v for k, v in record.items() if k in known and k not in _RECORD_EXCLUDE})
        job._logs_loaded = not job.log_path
        return job




class JobManager:
    def __init__(
        self,
        root: Path | None = None,
        *,
        command_factory: CommandFactory | None = None,
        load_history: bool = True,
        kill_grace_sec: float = 5.0,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else workspace.root()
        self.store = JobStore(self.root / workspace.STATE_DIR_NAME / "jobs")
        self._command = command_factory or commands.job_command
        self._kill_grace_sec = kill_grace_sec
        self._jobs: dict[str, SimulationJob] = {}
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []
        self._listeners_lock = threading.Lock()
        self._load_records()
        if load_history:
            self._load_historical_runs()

    # ------------------------------------------------------------ listeners
    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call ``listener(event, job_id)`` on every change. Returns a function that unsubscribes."""
        with self._listeners_lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._listeners_lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def _notify(self, event: str, job_id: str) -> None:
        with self._listeners_lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event, job_id)
            except Exception:
                pass  # a broken listener must never stop a job

    # -------------------------------------------------------------- records
    def _rel(self, path: Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    def _save(self, job: SimulationJob) -> None:
        if job.job_id.startswith("hist_"):
            return
        try:
            self.store.save(job.to_record())
        except OSError:
            pass

    def _load_records(self) -> None:
        for record in self.store.load_all():
            job = SimulationJob.from_record(record)
            if job.status == "running":
                # The process belonged to a previous session and its output pipe is gone.
                job.status = "failed"
                job.error_message = INTERRUPTED_MESSAGE
                job.pid = None
                job.finished_epoch = job.finished_epoch or time.time()
                job.finished_at = job.finished_at or datetime.now().isoformat()
                if job.log_path:
                    try:
                        with (self.root / job.log_path).open("a", encoding="utf-8") as handle:
                            handle.write(f"[{datetime.now():%H:%M:%S} WARNING] {INTERRUPTED_MESSAGE}\n")
                    except OSError:
                        pass
                self._save(job)
            self._jobs[job.job_id] = job

    def _ensure_logs(self, job: SimulationJob) -> None:
        """Read a reloaded job's log file the first time someone asks for its logs."""
        with job._lock:
            if job._logs_loaded:
                return
            job._logs_loaded = True
            path = self.root / job.log_path if job.log_path else None
            if path is None or not path.exists():
                return
            stamp = datetime.fromtimestamp(job.started_epoch).strftime("%H:%M:%S")
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if raw.strip():
                    job.append_log(_parse_log_line(raw, default_hms=stamp))

    def _load_historical_runs(self) -> None:
        dem_root = self.root / "simulations"
        recorded = {j.result_dir for j in self._jobs.values() if j.result_dir}
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
                if rel_res in recorded:
                    continue  # already known from its job record
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
                            parsing.update_telemetry(telemetry, entry["message"])
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

    # ---------------------------------------------------------------- queries
    def list_jobs(self, limit: int | None = 40) -> list[dict[str, Any]]:
        """Newest jobs first, without logs."""
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict(include_logs=False) for j in (jobs if limit is None else jobs[:limit])]

    def get_job(self, job_id: str, log_offset: int = 0) -> dict[str, Any] | None:
        """One job with the log entries from ``log_offset`` on (pass the last ``log_count`` to get only new ones)."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        self._ensure_logs(job)
        return job.to_dict(include_logs=True, log_offset=log_offset)

    def running_jobs(self) -> list[str]:
        with self._lock:
            return [j.job_id for j in self._jobs.values() if j.status == "running"]

    # -------------------------------------------------------------- mutation
    def delete_job(self, job_id: str, delete_files: bool = False) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status == "running":
                return False
            del self._jobs[job_id]
        self.store.delete(job_id)
        if delete_files and job.result_dir:
            target = (self.root / job.result_dir).resolve()
            try:
                target.relative_to((self.root / "simulations").resolve())
                if target.is_dir() and target.name.startswith("run_"):
                    shutil.rmtree(target)
            except Exception:
                pass
        self._notify("removed", job_id)
        return True

    def start_single_simulation(
        self,
        demonstrator_dir: str,
        *,
        parameters_override: dict[str, Any] | None = None,
        parameters_file_override: str | None = None,
    ) -> dict[str, Any]:
        job_id = f"sim_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
        name = demonstrator_dir.strip("/").split("/")[-1]
        params = parameters_override if parameters_override is not None else _load_params_file(self.root, demonstrator_dir, parameters_file_override)
        meta = _run_meta_from_params(params)
        strategy = f" ({meta['partitioning_strategy']})" if parameters_override and meta["partitioning_strategy"] else ""
        job = SimulationJob(
            job_id=job_id,
            job_type="single",
            title=f"Simulation: {name}{strategy}",
            demonstrator_dir=demonstrator_dir,
            demonstrator_id=name,
            parameters_override=parameters_override,
            **meta,
        )
        payload = json.dumps({"parameters_file_override": parameters_file_override, "parameters_override": parameters_override})
        return self._launch(job, self._command("single", [demonstrator_dir, "--payload", payload]), self.store.log_path(job_id))

    def start_batch_study(self, *, stop_on_error: bool = False) -> dict[str, Any]:
        stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
        batch_dir = self.root / "batch" / "runs" / f"batch_{stamp}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        job = SimulationJob(
            job_id=f"batch_{stamp}_{uuid.uuid4().hex[:6]}",
            job_type="batch",
            title=f"Batch Study ({batch_dir.name})",
            batch_dir=self._rel(batch_dir),
        )
        args = ["--stop-on-error"] if stop_on_error else []
        return self._launch(job, self._command("batch", args), batch_dir / "batch.log", extra_env={"HDD_BATCH_DIR": self._rel(batch_dir)})

    def start_tuning_study(self, *, study_dir: Path, title: str, demonstrator_id: str | None = None) -> dict[str, Any]:
        job = SimulationJob(
            job_id=f"tuning_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}",
            job_type="tuning",
            title=title,
            study_dir=self._rel(study_dir),
            demonstrator_id=demonstrator_id,
            stage_progress=0,
        )
        return self._launch(job, self._command("tune", [str(Path(study_dir).resolve())]), self.store.log_path(job.job_id))

    def _launch(self, job: SimulationJob, argv: list[str], log_file: Path, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
        now = time.time()
        job.started_epoch = job.stage_started_epoch = now
        job.log_path = self._rel(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        env = commands.job_environment(self.root)
        env.update(extra_env or {})
        handle = log_file.open("a", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(self.root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                start_new_session=True,
                env=env,
            )
        except OSError:
            handle.close()
            raise
        job._process = proc
        job.pid = proc.pid
        with self._lock:
            self._jobs[job.job_id] = job
        self._save(job)
        threading.Thread(target=self._consume_process_output, args=(job, handle), daemon=True, name=f"job-{job.job_id}").start()
        self._notify("added", job.job_id)
        return job.to_dict(include_logs=True)

    def cancel_job(self, job_id: str) -> dict[str, Any] | None:
        """Stop a job: SIGTERM to its process group, SIGKILL if it is still alive after the grace period."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        proc = job._process
        if proc is not None and proc.poll() is None:
            _signal_group(proc, signal.SIGTERM)
            timer = threading.Timer(self._kill_grace_sec, lambda: proc.poll() is None and _signal_group(proc, signal.SIGKILL))
            timer.daemon = True
            timer.start()
        changed = False
        with job._lock:
            if job.status == "running":
                now = time.time()
                job.close_stage(now)
                job.status = "cancelled"
                job.finished_epoch = now
                job.finished_at = datetime.now().isoformat()
                job.append_log({"timestamp": datetime.now().strftime("%H:%M:%S"), "level": "WARNING", "message": "Job cancelled by user."})
                changed = True
        if changed:
            self._save(job)
            self._notify("finished", job_id)
        return job.to_dict(include_logs=True)

    def cancel_all(self) -> list[str]:
        """Cancel every running job (used when the application closes)."""
        ids = self.running_jobs()
        for job_id in ids:
            self.cancel_job(job_id)
        return ids

    # ---------------------------------------------------------------- reader
    def _consume_process_output(self, job: SimulationJob, log_handle) -> None:
        proc = job._process
        try:
            for raw_line in proc.stdout:
                line = raw_line.rstrip("\r\n")
                if not line:
                    continue
                try:
                    log_handle.write(line + "\n")
                    log_handle.flush()
                except (OSError, ValueError):
                    pass
                self._apply_line(job, line)
                self._notify("changed", job.job_id)
            exit_code = proc.wait()
        finally:
            try:
                log_handle.close()
            except OSError:
                pass
        with job._lock:
            now = time.time()
            job.close_stage(now)
            job.exit_code = exit_code
            job.pid = None
            job.finished_epoch = now
            job.finished_at = datetime.now().isoformat()
            if job.status != "cancelled":
                job.status = "completed" if exit_code == 0 else "failed"
                if exit_code == 0:
                    job.stage_progress = 100
        self._save(job)
        self._notify("finished", job.job_id)

    @staticmethod
    def _apply_line(job: SimulationJob, line: str) -> None:
        entry = _parse_log_line(line)
        message = entry["message"]
        with job._lock:
            now = time.time()
            job.append_log(entry)
            if job.job_type != "tuning":
                stage = parsing.detect_stage(message)
                if stage:
                    if stage != job.current_stage:
                        job.close_stage(now)
                        job.current_stage = stage
                        job.stage_started_epoch = now
                    job.stage_progress = min(95, int((parsing.STAGE_INDEX.get(stage, 0) + 1) * 18))
            parsing.update_telemetry(job.telemetry, message)
            if job.job_type == "batch":
                parsing.update_batch_progress(job.telemetry, message)
            elif job.job_type == "tuning":
                progress = parsing.update_tuning_progress(job.telemetry, message)
                if progress is not None:
                    job.stage_progress = progress
            result_dir = parsing.result_dir_from(message)
            if result_dir:
                job.result_dir = result_dir
            # Tuning trials may fail individually; only the exit code decides the job status.
            if entry["level"] == "ERROR" and job.error_message is None and job.job_type != "tuning":
                job.error_message = message


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except Exception:
        try:
            proc.send_signal(sig)
        except Exception:
            pass
