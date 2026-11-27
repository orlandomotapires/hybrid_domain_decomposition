"""The job manager: starts jobs as detached processes, follows their logs and keeps their records.

A job writes its output straight to its log file, in its own session, so it keeps
running when the Studio closes. The manager follows that file: one follower thread
per running job reads new lines and applies them under the job's lock. Progress
comes from structured events (``libs.runtime.events``); ordinary lines become the
visible log. When the Studio opens again, jobs whose process is still alive are
followed again, and jobs that ended meanwhile are settled from the ``exit`` event
in their log.

Listeners registered with :meth:`JobManager.subscribe` are called with
``(event, job_id)`` from follower threads, outside every lock; they should only
note the change and let their own thread pull the state with :meth:`get_job`.
"""

from __future__ import annotations

import json
import logging
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

from libs.runtime import events as job_events
from libs.runtime import workspace

from libs.runtime.atomic import atomic_write_json

from .. import catalog, results
from ..errors import Conflict
from . import commands, parsing
from .parsing import _parse_log_line
from .store import JobStore

Listener = Callable[[str, str], None]
CommandFactory = Callable[[str, list[str]], list[str]]
EVENTS = ("added", "changed", "finished", "removed")
MAX_LOG_ENTRIES = 50_000
_log = logging.getLogger("hdd.jobs")

INTERRUPTED_MESSAGE ="The job ended while the Studio was closed and did not report a result."
NO_RESULT_MESSAGE = "The job ended without reporting a result (it may have been killed)."
DISMISSED_FILE = "dismissed_runs.json"  # in .hdd/: run folders removed from the jobs list
POLL_SEC = 0.1
# Fields written to a job record (everything else is runtime state).
_RECORD_EXCLUDE = {"logs", "parameters_override"}
_RECORD_PATH_FIELDS = ("log_path", "result_dir", "batch_dir", "study_dir", "demonstrator_dir")


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
    pid_start: int | None = None  # start time of the process, to tell it from a later process with the same pid
    exit_code: int | None = None
    exit_reported: int | None = None  # code from the job's own ``exit`` event
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
        self._dismiss_lock = threading.Lock()
        self._listeners: list[Listener] = []
        self._listeners_lock = threading.Lock()
        self._closed = threading.Event()
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
        except (OSError, ValueError) as exc:
            # The job goes on, but without a record the next session cannot follow or settle it.
            _log.error("Could not save the record of job %s: %s", job.job_id, exc)
            with job._lock:
                if not job.telemetry.get("record_error"):
                    job.telemetry["record_error"] = str(exc)
                    job.append_log({"timestamp": datetime.now().strftime("%H:%M:%S"), "level": "WARNING",
                                    "message": f"Could not save the job record ({exc}); the job will not be "
                                               "followed after the Studio restarts."})

    def _inside_workspace(self, value: Any, *, follow_links: bool) -> str | None:
        """``value`` if it is a relative path that stays inside the workspace, else None.

        Paths the Studio only reads or shows are checked lexically, so folders symlinked to
        another disk keep working. A path it writes to (the log) must also resolve inside.
        """
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            return None
        if os.path.normpath(value).split(os.sep)[0] == os.pardir:
            return None
        if follow_links:
            try:
                (self.root / value).resolve().relative_to(self.root)
            except (ValueError, OSError):
                return None
        return value

    def _sanitize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Records come from the workspace, which may be someone else's: keep their paths inside it."""
        record = dict(record)
        for key in _RECORD_PATH_FIELDS:
            if record.get(key) is not None:
                safe = self._inside_workspace(record[key], follow_links=key == "log_path")
                if safe is None:
                    _log.warning("Job %s: ignoring %s %r (outside the workspace)", record.get("job_id"), key, record[key])
                record[key] = safe
        for key in ("pid", "pid_start"):
            value = record.get(key)
            record[key] = value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
        return record

    def _load_records(self) -> None:
        for record in self.store.load_all():
            try:
                self._load_record(record)
            except Exception:  # one bad record must not keep the workspace from opening
                _log.exception("Skipping unreadable job record %r", record.get("job_id"))
                self._jobs.pop(str(record.get("job_id")), None)

    def _load_record(self, record: dict[str, Any]) -> None:
        job = SimulationJob.from_record(self._sanitize_record(record))
        job.to_dict(include_logs=False)  # fail here, not later in the UI, on wrongly typed fields
        self._jobs[job.job_id] = job
        if job.status != "running":
            return
        # The job was running when the Studio last closed: rebuild its state from its log.
        job.logs, job.logs_dropped, job.telemetry, job._logs_loaded = [], 0, {}, True
        job.exit_reported = None
        if job.log_path and _pid_alive(job.pid, job.pid_start):
            self._start_follower(job, self._replay(job))
        else:
            self._follow(job, 0, settle=True)

    def _replay(self, job: SimulationJob) -> int:
        """Apply the complete lines already in the job's log; return the offset to follow from."""
        path = self.root / job.log_path
        try:
            data = path.read_bytes()
        except OSError:
            return 0
        end = data.rfind(b"\n") + 1
        for raw in data[:end].split(b"\n"):
            self._apply_raw(job, raw)
        return end

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
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:  # deleted or unreadable since it was listed
                job.append_log({"timestamp": stamp, "level": "WARNING", "message": f"The job's log could not be read: {exc}"})
                return
            for raw in text.splitlines():
                if raw.strip() and job_events.parse(raw) is None:
                    entry = _parse_log_line(raw, default_hms=stamp)
                    job.append_log(entry)
                    parsing.update_telemetry(job.telemetry, entry["message"])  # graph sizes etc. from the log

    def _dismissed_path(self) -> Path:
        return self.store.directory.parent / DISMISSED_FILE

    def _dismissed(self) -> set[str]:
        """Run folders the user removed from the list (keeping the files): not listed again."""
        try:
            data = json.loads(self._dismissed_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        return {str(item) for item in data} if isinstance(data, list) else set()

    def _dismiss(self, run_dir: str) -> None:
        with self._dismiss_lock:  # read-modify-write: concurrent removals must not lose an entry
            dismissed = self._dismissed() | {run_dir}
            try:
                atomic_write_json(self._dismissed_path(), sorted(dismissed))
            except OSError as exc:
                _log.warning("Could not record the removed run %s: %s", run_dir, exc)

    @staticmethod
    def _run_folder(job: SimulationJob) -> str | None:
        """The run folder a job stands for: its result, or for a listed failed run, its log's folder."""
        if job.result_dir:
            return job.result_dir
        if job.job_id.startswith("hist_") and job.log_path:
            return str(Path(job.log_path).parent)
        return None

    def _load_historical_runs(self) -> None:
        dem_root = self.root / "simulations"
        recorded = {j.result_dir for j in self._jobs.values() if j.result_dir}
        dismissed = self._dismissed()
        if not dem_root.exists():
            return
        for dem_dir in sorted(dem_root.iterdir()):
            results_dir = dem_dir / "results"
            if not results_dir.is_dir():
                continue
            for run_dir in sorted(results_dir.iterdir()):
                if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
                    continue
                rel_res = f"simulations/{dem_dir.name}/results/{run_dir.name}"
                if rel_res in recorded or rel_res in dismissed:
                    continue  # known from its job record, or removed from the list by the user
                try:
                    job = self._historical_job(dem_dir, run_dir, rel_res)
                except OSError as exc:  # the folder went away or cannot be read: skip it
                    _log.warning("Skipping run folder %s: %s", rel_res, exc)
                    continue
                self._jobs[job.job_id] = job

    def _historical_job(self, dem_dir: Path, run_dir: Path, rel_res: str) -> SimulationJob:
        """A finished job rebuilt from a run folder; its log is read only when someone asks for it."""
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
                    strategy_str = f" ({catalog.method_label(strat, run_meta['simulated'], short=True)})"
                k_t = p.get("partitioning_parameters", {}).get("common", {}).get("k_target")
                if k_t is not None:
                    telemetry["coarse_parts"] = int(k_t)
            except (OSError, ValueError, TypeError, AttributeError):
                pass  # an unreadable parameters file only costs the title's method label

        metrics_file = run_dir / "run_metrics.json"
        if metrics_file.exists():
            try:
                k_m = json.loads(metrics_file.read_text(encoding="utf-8")).get("matrix", {})
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
            except (OSError, ValueError, TypeError, AttributeError):
                pass

        mtime = run_dir.stat().st_mtime
        created_iso = datetime.fromtimestamp(mtime).isoformat()
        default_hms = datetime.fromtimestamp(mtime).strftime("%H:%M:%S")

        # The same rule as the project tree (results.run_outcome): a run without metrics that
        # never logged its result was cut short, even if it logged no error (an OOM kill).
        outcome, error = results.run_outcome(run_dir, metrics_file.exists())
        completed = outcome == "completed"
        run_log = run_dir / "run_log"
        job = SimulationJob(
            job_id=f"hist_{dem_dir.name}_{run_dir.name}",
            job_type="single",
            title=f"{dem_dir.name}{strategy_str}",
            demonstrator_dir=f"simulations/{dem_dir.name}",
            status="completed" if completed else "failed",
            current_stage="permutation" if completed else "initialization",
            stage_progress=100 if completed else 15,
            created_at=created_iso,
            finished_at=created_iso,
            started_epoch=mtime,
            finished_epoch=mtime,
            result_dir=rel_res if completed else None,  # "Show result" only for runs that have one
            exit_code=0 if completed else 1,
            error_message=None if completed else (error or NO_RESULT_MESSAGE),
            telemetry=telemetry,
            logs=[] if run_log.exists() else [
                {"timestamp": default_hms, "level": "INFO", "message": f"Loaded historical run from {rel_res}"}
            ],
            demonstrator_id=dem_dir.name,
            **run_meta,
        )
        if run_log.exists():
            job.log_path = f"{rel_res}/run_log"
            job._logs_loaded = False  # read on first request, not for every run at startup
        return job

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
        run_folder = self._run_folder(job)
        if run_folder and not delete_files:
            self._dismiss(run_folder)  # its run folder must not come back as a historical job
        if delete_files and job.result_dir:
            target = (self.root / job.result_dir).resolve()
            try:
                target.relative_to((self.root / "simulations").resolve())
            except ValueError:
                pass  # only run folders under simulations/ are ever deleted
            else:
                if target.is_dir() and target.name.startswith("run_"):
                    try:
                        shutil.rmtree(target)
                    except OSError as exc:
                        self._dismiss(job.result_dir)  # the folder stays; keep it off the list anyway
                        self._notify("removed", job_id)
                        raise Conflict(f"The job was removed, but its files could not be deleted: {exc}") from exc
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
        strategy = (f" ({catalog.method_label(meta['partitioning_strategy'], meta['simulated'], short=True)})"
                    if parameters_override and meta["partitioning_strategy"] else "")
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
        position = log_file.stat().st_size if log_file.exists() else 0
        with log_file.open("ab") as handle:
            # The child owns its output: nothing breaks when the Studio closes.
            proc = subprocess.Popen(
                argv,
                cwd=str(self.root),
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
        job._process = proc
        job.pid = proc.pid
        job.pid_start = _process_start(proc.pid)
        with self._lock:
            self._jobs[job.job_id] = job
        self._save(job)
        self._start_follower(job, position)
        self._notify("added", job.job_id)
        return job.to_dict(include_logs=True)

    def cancel_job(self, job_id: str) -> dict[str, Any] | None:
        """Stop a job: SIGTERM to its process group, SIGKILL if it is still alive after the grace period."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return None
        proc = job._process
        unverified = False
        if proc is not None:
            if proc.poll() is None:
                _signal_group(proc.pid, signal.SIGTERM)
                self._after_grace(lambda: proc.poll() is None and _signal_group(proc.pid, signal.SIGKILL))
        elif _pid_verified(job.pid, job.pid_start):  # followed again after a restart: not our child
            pid, start = job.pid, job.pid_start
            _signal_group(pid, signal.SIGTERM)
            self._after_grace(lambda: _pid_verified(pid, start) and _signal_group(pid, signal.SIGKILL))
        elif _pid_alive(job.pid, job.pid_start):
            # Followed again after a restart, but the process cannot be proven to be this job (no
            # start time, or no /proc): the pid may belong to an unrelated process by now, so it
            # is never signalled, and the job stays "running" until that process ends.
            unverified = True
        changed = False
        with job._lock:
            stamp = datetime.now().strftime("%H:%M:%S")
            if unverified and job.status == "running":
                job.append_log({"timestamp": stamp, "level": "WARNING", "message": (
                    f"Process {job.pid} could not be verified as this job, so it was not stopped. "
                    "Stop it from a terminal if it is this job; the job is followed until it ends.")})
                changed = True
            elif job.status == "running":
                now = time.time()
                job.close_stage(now)
                job.status = "cancelled"
                job.finished_epoch = now
                job.finished_at = datetime.now().isoformat()
                job.append_log({"timestamp": stamp, "level": "WARNING", "message": "Job cancelled by user."})
                changed = True
        if changed:
            self._save(job)
            self._notify("changed" if unverified else "finished", job_id)
        return job.to_dict(include_logs=True)

    def _after_grace(self, fn: Callable[[], Any]) -> None:
        timer = threading.Timer(self._kill_grace_sec, fn)
        timer.daemon = True
        timer.start()

    def cancel_all(self) -> list[str]:
        """Cancel every running job."""
        ids = self.running_jobs()
        for job_id in ids:
            self.cancel_job(job_id)
        return ids

    def close(self) -> None:
        """Stop following the jobs. Their processes keep running; the next manager picks them up."""
        self._closed.set()

    # -------------------------------------------------------------- follower
    def _start_follower(self, job: SimulationJob, position: int) -> None:
        threading.Thread(target=self._follow, args=(job, position), daemon=True, name=f"job-{job.job_id}").start()

    def _follow(self, job: SimulationJob, position: int, settle: bool = False) -> None:
        """Apply the job's log from ``position`` on until its process ends (or the manager closes).

        ``settle`` reads a job whose process is already gone, to rebuild its final state. Whatever
        goes wrong, the job reaches a final state: a dead follower must not leave it "running".
        """
        try:
            self._follow_log(job, position, settle)
        except Exception as exc:
            _log.exception("Lost track of job %s", job.job_id)
            self._lose(job, exc)

    def _lose(self, job: SimulationJob, exc: Exception) -> None:
        with job._lock:
            if job.status != "running":
                return
            pid = job.pid
            job.status = "failed"
            job.error_message = f"The Studio lost track of this job ({exc})."
            if pid and (job._process is None or job._process.poll() is None):
                job.error_message += f" Its process ({pid}) may still be running."
            now = time.time()
            job.close_stage(now)
            job.finished_epoch = now
            job.finished_at = datetime.fromtimestamp(now).isoformat()
            job.append_log({"timestamp": datetime.now().strftime("%H:%M:%S"), "level": "ERROR", "message": job.error_message})
        self._save(job)
        self._notify("finished", job.job_id)

    def _follow_log(self, job: SimulationJob, position: int, settle: bool) -> None:
        path = self.root / job.log_path if job.log_path else None
        buffer = b""
        handle = path.open("rb") if path is not None and path.exists() else None
        try:
            if handle is not None:
                handle.seek(position)
            while True:
                if not settle and self._closed.is_set():
                    return  # checked every round: a job that logs nonstop must not keep a closed manager reading
                chunk = handle.read(65536) if handle is not None else b""
                if chunk:
                    buffer += chunk
                    *lines, buffer = buffer.split(b"\n")
                    for raw in lines:
                        self._apply_raw(job, raw)
                    if lines and not settle:
                        self._notify("changed", job.job_id)
                    continue
                ended, code = (True, None) if settle else self._process_ended(job)
                if ended:
                    if handle is not None:
                        buffer += handle.read()
                    for raw in buffer.split(b"\n"):
                        self._apply_raw(job, raw)
                    when = path.stat().st_mtime if settle and path is not None and path.exists() else None
                    self._finish(job, code, when=when, interrupted=settle)
                    return
                if self._closed.is_set():
                    return
                time.sleep(POLL_SEC)
        finally:
            if handle is not None:
                handle.close()

    @staticmethod
    def _process_ended(job: SimulationJob) -> tuple[bool, int | None]:
        proc = job._process
        if proc is not None:
            code = proc.poll()
            return code is not None, code
        return not _pid_alive(job.pid, job.pid_start), None

    def _finish(self, job: SimulationJob, code: int | None, *, when: float | None = None, interrupted: bool = False) -> None:
        note = None
        with job._lock:
            now = when or time.time()
            job.close_stage(now)
            if code is None:
                code = job.exit_reported
            job.exit_code = code
            job.pid = None
            job.finished_epoch = now
            job.finished_at = datetime.fromtimestamp(now).isoformat()
            if job.status != "cancelled":
                if code is None:
                    job.status = "failed"
                    job.error_message = INTERRUPTED_MESSAGE if interrupted else NO_RESULT_MESSAGE
                    note = job.error_message
                    job.append_log({"timestamp": datetime.fromtimestamp(now).strftime("%H:%M:%S"), "level": "WARNING", "message": note})
                else:
                    job.status = "completed" if code == 0 else "failed"
                    if code == 0:
                        job.stage_progress = 100
                    elif job.error_message is None:
                        job.error_message = f"Stopped by signal {-code}." if code < 0 else f"Exited with code {code}."
        if note and job.log_path:
            try:
                with (self.root / job.log_path).open("a", encoding="utf-8") as handle:
                    handle.write(f"[{datetime.now():%H:%M:%S} WARNING] {note}\n")
            except OSError:
                pass
        self._save(job)
        self._notify("finished", job.job_id)

    def _apply_raw(self, job: SimulationJob, raw: bytes) -> None:
        line = raw.decode("utf-8", errors="replace").rstrip("\r")
        if line.strip():
            self._apply_line(job, line)

    def _apply_line(self, job: SimulationJob, line: str) -> None:
        event = job_events.parse(line)
        with job._lock:
            if event is not None:
                try:
                    self._apply_event(job, event)
                    return
                except (KeyError, TypeError, ValueError) as exc:
                    # A malformed event must not stop the follower; keep the line for the user.
                    _log.warning("Ignoring malformed event of job %s: %s (%s)", job.job_id, line, exc)
                    line = f"[{datetime.now():%H:%M:%S} WARNING] Ignored a malformed progress event: {line}"
            entry = _parse_log_line(line)
            job.append_log(entry)
            parsing.update_telemetry(job.telemetry, entry["message"])
            # Tuning trials may fail individually; only the exit code decides the job status.
            if entry["level"] == "ERROR" and job.error_message is None and job.job_type != "tuning":
                job.error_message = entry["message"]

    def _apply_event(self, job: SimulationJob, event: dict[str, Any]) -> None:
        """Update the job from one progress event (under the job's lock)."""
        kind, t = event["event"], job.telemetry
        if kind == "exit":
            job.exit_reported = int(event.get("code", 1))
        elif kind == "result" and event.get("result_dir"):
            job.result_dir = self._rel(self.root / event["result_dir"])
        elif job.job_type == "single" and kind in ("stage", "progress"):
            # Batch cases and tuning trials run the pipeline too; their own counters measure progress.
            if kind == "stage" and event.get("stage") in parsing.STAGE_INDEX:
                if event["stage"] != job.current_stage:
                    now = time.time()
                    job.close_stage(now)
                    job.current_stage = event["stage"]
                    job.stage_started_epoch = now
                fraction = 0.0
            elif kind == "progress":
                fraction = float(event.get("fraction") or 0.0)
            else:
                return
            count = len(parsing.PIPELINE_STAGES)
            job.stage_progress = max(1, min(99, int(100 * (parsing.STAGE_INDEX.get(job.current_stage, 0) + fraction) / count)))
        elif kind == "batch":
            t["batch_total"] = int(event.get("total", 0))
            t.setdefault("batch_done", 0)
            t.setdefault("batch_failed", 0)
        elif kind == "batch_case":
            t["batch_index"], t["batch_total"], t["batch_case"] = int(event["index"]), int(event["total"]), event.get("case")
        elif kind == "batch_done":
            t["batch_done"] = int(t.get("batch_done", 0)) + 1
            if event.get("status") == "failed":
                t["batch_failed"] = int(t.get("batch_failed", 0)) + 1
            job.stage_progress = min(99, int(100 * t["batch_done"] / max(int(t.get("batch_total", 0)), 1)))
        elif kind == "tuning":
            t["tuning_total"] = int(event.get("total", 0))
            t.setdefault("tuning_done", 0)
        elif kind == "trial":
            done, total = int(event["done"]), int(event["total"])
            t["tuning_done"], t["tuning_total"] = done, total
            key = f"tuning_{event.get('status', 'ok')}"
            t[key] = int(t.get(key, 0)) + 1
            job.stage_progress = min(99, int(100 * done / max(total, 1)))


def _process_start(pid: int | None) -> int | None:
    """Start time of a process in clock ticks since boot (Linux), or None when unknown."""
    if not pid:
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return int(stat[stat.rindex(")") + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _pid_alive(pid: int | None, start: int | None = None) -> bool:
    """Whether ``pid`` is still the process that was started (not a zombie, not a reused pid)."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields_after = stat[stat.rindex(")") + 2:].split()
        if fields_after[0] == "Z":
            return False
        if start is not None and int(fields_after[19]) != start:
            return False
    except (OSError, ValueError, IndexError):
        pass  # no /proc: the process exists, which is all that can be said
    return True


def _pid_verified(pid: int | None, start: int | None) -> bool:
    """Whether ``pid`` is alive and provably the process started at ``start`` (safe to signal)."""
    if not pid or start is None:
        return False
    return _process_start(pid) == start and _pid_alive(pid, start)


def _signal_group(pid: int, sig: int) -> bool:
    """Signal the job's process group. Jobs lead their own session, so the group id is the pid.

    No fallback to signalling the pid alone: if the group is gone, so is the job, and a bare pid
    may already belong to another process.
    """
    try:
        os.killpg(pid, sig)
        return True
    except OSError:
        return False
