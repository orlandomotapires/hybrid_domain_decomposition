#!/usr/bin/env python3
"""Run a batch study. Usage: ``python -m libs.batch.run_batch [--dry-run] [--nohup] [--stop-on-error]``."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime
import json
import os
from multiprocessing import Process
import subprocess
from pathlib import Path
import sys
import time
import traceback
from typing import Any


from libs.runtime import events, workspace
from libs.runtime.launch import child_environment, module_command
from libs.runtime.matrix_library import resolve_matrix
from libs.runtime.runtime import run_simulation
from libs.runtime.utils import (
    AVAILABLE_SAVE_OUTPUTS,
    validate_and_normalize_simulation_parameters,
    write_json,
)

@dataclass(frozen=True)
class Geometry:
    """A matrix from the shared library (matrices/<key>/). Kept as "geometry" in manifests."""
    key: str


@dataclass(frozen=True)
class CoarseningPreset:
    key: str
    coarsen_inferior_limit: int
    coarsen_superior_limit: int | None = None


@dataclass(frozen=True)
class AlgorithmPreset:
    key: str
    partitioning_strategy: str
    allowed_sizes: tuple[str, ...]
    strategy_parameters: dict[str, Any]


@dataclass(frozen=True)
class BatchCase:
    geometry: Geometry
    coarsening: CoarseningPreset
    algorithm: AlgorithmPreset

    @property
    def case_key(self) -> str:
        return f"{self.geometry.key}__{self.algorithm.key}__{self.coarsening.key}"


def _clone_json_like(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_matrices(configuration: dict[str, Any]) -> tuple[Geometry, ...]:
    """Library matrices to run (``"matrices": [{"key": "<matrix_id>"}]``), de-duplicated in order."""
    seen: list[str] = []
    for entry in configuration.get("matrices", []):
        key = str(entry["key"])
        if key not in seen:
            seen.append(key)
    return tuple(Geometry(key=key) for key in seen)


def _load_batch_configuration() -> dict[str, Any]:
    return parse_batch_configuration(_load_json(workspace.batch_config_path()))


def parse_batch_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    """Validate a raw batch configuration and return it in typed form. Raises KeyError/ValueError/TypeError."""
    return {
        "async_remote_case_keys": tuple(str(key) for key in configuration.get("async_remote_case_keys", [])),
        "summary_percent_bands": tuple(float(value) for value in configuration.get("summary_percent_bands", [])),
        "common_defaults": _clone_json_like(configuration.get("common_defaults", {})),
        "base_parameters": _clone_json_like(configuration.get("base_parameters")),
        "save_output": list(configuration.get("save_output") or sorted(AVAILABLE_SAVE_OUTPUTS)),
        "geometries": _load_matrices(configuration),
        "coarsening_presets": tuple(
            CoarseningPreset(
                key=str(entry["key"]),
                coarsen_inferior_limit=int(entry["coarsen_inferior_limit"]),
                coarsen_superior_limit=None if entry.get("coarsen_superior_limit") is None else int(entry["coarsen_superior_limit"]),
            )
            for entry in configuration.get("coarsening_presets", [])
        ),
        "algorithm_presets": tuple(
            AlgorithmPreset(
                key=str(entry["key"]),
                partitioning_strategy=str(entry["partitioning_strategy"]),
                allowed_sizes=tuple(str(size) for size in entry.get("allowed_sizes", [])),
                strategy_parameters=_clone_json_like(entry.get("strategy_parameters", {})),
            )
            for entry in configuration.get("algorithm_presets", [])
        ),
    }

_CONFIG_NAMES = {
    "ASYNC_REMOTE_CASE_KEYS": lambda c: frozenset(c["async_remote_case_keys"]),
    "SUMMARY_PERCENT_BANDS": lambda c: c["summary_percent_bands"],
    "COMMON_DEFAULTS": lambda c: c["common_defaults"],
    "GEOMETRIES": lambda c: c["geometries"],
    "BASE_PARAMETERS": lambda c: c["base_parameters"],
    "SAVE_OUTPUT": lambda c: c["save_output"],
    "DEFAULT_COARSENING_PRESETS": lambda c: c["coarsening_presets"],
    "DEFAULT_ALGORITHM_PRESETS": lambda c: c["algorithm_presets"],
}
_CONFIG_CACHE: tuple[Path, dict[str, Any]] | None = None  # (workspace root, configuration)


def batch_configuration(*, reload: bool = False) -> dict[str, Any]:
    """The workspace's batch configuration, read on first use (not at import) and per workspace."""
    global _CONFIG_CACHE
    root = workspace.root()
    if _CONFIG_CACHE is None or reload or _CONFIG_CACHE[0] != root:
        _CONFIG_CACHE = (root, _load_batch_configuration())
    return _CONFIG_CACHE[1]


def _setting(name: str) -> Any:
    return _CONFIG_NAMES[name](batch_configuration())


def __getattr__(name: str) -> Any:
    # Module-level names such as GEOMETRIES used to be loaded at import; keep them readable.
    if name == "BATCH_CONFIGURATION":
        return batch_configuration()
    if name in _CONFIG_NAMES:
        return _setting(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _apply_common_defaults(parameters: dict[str, Any], coarsening: CoarseningPreset) -> dict[str, Any]:
    updated = _clone_json_like(parameters)

    updated["general_parameters"].update(_clone_json_like(_setting("COMMON_DEFAULTS").get("general_parameters", {})))
    updated["coarsening_parameters"].update(_clone_json_like(_setting("COMMON_DEFAULTS").get("coarsening_parameters", {})))
    updated["partitioning_parameters"]["common"].update(_clone_json_like(_setting("COMMON_DEFAULTS").get("partitioning_common", {})))
    updated.setdefault("uncoarsening_parameters", {}).update(
        _clone_json_like(_setting("COMMON_DEFAULTS").get("uncoarsening_parameters", {}))
    )
    updated["coarsening_parameters"].update(
        {
            "coarsen_inferior_limit": int(coarsening.coarsen_inferior_limit),
            "coarsen_superior_limit": None if coarsening.coarsen_superior_limit is None else int(coarsening.coarsen_superior_limit),
        }
    )

    return updated

def _load_validated_base_inputs(geometry: Geometry) -> dict[str, Any]:
    """Base simulation parameters for every case (batch "base_parameters"), after checking the matrix exists."""
    resolve_matrix(geometry.key)
    if _setting("BASE_PARAMETERS") is None:
        raise ValueError(
            "batch_configuration.json has no base_parameters; add a full simulation-parameters block under base_parameters"
        )
    return validate_and_normalize_simulation_parameters(_clone_json_like(_setting("BASE_PARAMETERS")))


def _apply_algorithm_preset(parameters: dict[str, Any], case: BatchCase) -> dict[str, Any]:
    updated = _clone_json_like(parameters)
    partitioning = updated["partitioning_parameters"]
    strategies = partitioning["strategies"]

    partitioning["partitioning_strategy"] = case.algorithm.partitioning_strategy

    if case.algorithm.partitioning_strategy == "quantum_annealing":
        qa_params = dict(case.algorithm.strategy_parameters)
        qa_params["qpu_problem_label"] = case.case_key
        strategies["quantum_annealing"] = qa_params
    elif case.algorithm.partitioning_strategy == "quantum_approximation_optimizer":
        strategies["quantum_approximation_optimizer"] = dict(case.algorithm.strategy_parameters)
    elif case.algorithm.partitioning_strategy == "metis_partitioning":
        strategies.setdefault("metis_partitioning", {})
    else:
        raise ValueError(f"Unsupported algorithm preset: {case.algorithm.partitioning_strategy}")

    return updated


def build_cases() -> list[BatchCase]:
    cases: list[BatchCase] = []
    for geometry in _setting("GEOMETRIES"):
        for algorithm in _setting("DEFAULT_ALGORITHM_PRESETS"):
            for coarsening in _setting("DEFAULT_COARSENING_PRESETS"):
                if coarsening.key not in algorithm.allowed_sizes:
                    continue
                cases.append(BatchCase(geometry, coarsening, algorithm))
    return cases


def _build_case_parameters(case: BatchCase, base_parameters: dict[str, Any]) -> dict[str, Any]:
    case_parameters = _apply_common_defaults(base_parameters, case.coarsening)
    case_parameters = _apply_algorithm_preset(case_parameters, case)
    return validate_and_normalize_simulation_parameters(case_parameters)


def _write_batch_configuration_snapshot(batch_dir: Path) -> Path:
    snapshot_path = batch_dir / "batch_configuration.json"
    write_json(snapshot_path, _load_json(workspace.batch_config_path()))
    return snapshot_path


def _batch_output_dir() -> Path:
    output_dir = workspace.batch_runs_dir() / datetime.now().strftime("batch_%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir
    


def _resolve_batch_dir() -> Path:
    env_batch_dir = os.environ.get("HDD_BATCH_DIR")
    if env_batch_dir:
        batch_dir = workspace.root() / env_batch_dir
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_dir
    return _batch_output_dir()


def _launch_nohup(case_count: int) -> int:
    batch_dir = _resolve_batch_dir()
    log_path = batch_dir / "batch.log"
    child_args = [arg for arg in sys.argv[1:] if arg != "--nohup"]
    child_env = child_environment({"HDD_BATCH_DIR": str(batch_dir.relative_to(workspace.root()))})

    with log_path.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            module_command("libs.batch.run_batch", child_args, unbuffered=False),
            cwd=str(workspace.root()),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=child_env,
        )

    print(f"Started batch in background with PID {process.pid}")
    print(f"Prepared {case_count} batch cases.")
    print(f"Batch directory: {batch_dir.relative_to(workspace.root())}")
    print(f"Batch log: {(batch_dir / 'batch.log').relative_to(workspace.root())}")
    return 0


def _case_simulation_config(case: BatchCase) -> dict[str, Any]:
    return {
        "parameters_file_path": "simulation_parameters.json",
        "input_matrix": case.geometry.key,
        "save_output": list(_setting("SAVE_OUTPUT")),
    }


def _case_run_kwargs(case: BatchCase, batch_dir: Path) -> dict[str, Any]:
    """Arguments for run_simulation: in-memory config, results under batch/runs/<batch>/cases/<case_key>/."""
    return {
        "simulation_config_override": _case_simulation_config(case),
        "results_dir_override": str((batch_dir / "cases" / case.case_key).relative_to(workspace.root())),
        "run_label": case.case_key,
    }

def _run_one_case(case: BatchCase, simulation_parameters: dict[str, Any], batch_dir: Path) -> Path:
    return run_simulation(
        None,
        simulation_parameters_override=simulation_parameters,
        **_case_run_kwargs(case, batch_dir),
    )


def _run_one_case_worker(run_kwargs: dict[str, Any], simulation_parameters: dict[str, Any], output_json: Path, log_path: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", buffering=1) as handle:
        with redirect_stdout(handle), redirect_stderr(handle):
            try:
                result_dir = run_simulation(None, simulation_parameters_override=simulation_parameters, **run_kwargs)
                write_json(
                    output_json,
                    {
                        "status": "completed",
                        "result_dir": str(result_dir.relative_to(workspace.root())),
                    },
                )
            except Exception as exc:
                traceback.print_exc()
                write_json(
                    output_json,
                    {
                        "status": "failed",
                        "error": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                            "traceback": traceback.format_exc(),
                        },
                    },
                )


def _case_to_manifest_entry(case: BatchCase) -> dict[str, Any]:
    return {
        "case_key": case.case_key,
        "geometry": case.geometry.key,
        "matrix": case.geometry.key,
        "algorithm": case.algorithm.key,
        "partitioning_strategy": case.algorithm.partitioning_strategy,
        "coarsening_size": case.coarsening.key,
        "coarsen_inferior_limit": case.coarsening.coarsen_inferior_limit,
        "coarsen_superior_limit": case.coarsening.coarsen_superior_limit,
        "parameters_source": "in_memory",
        "status": "pending",
        "started_at": None,
        "finished_at": None,
        "result_dir": None,
        "async_log_file": None,
        "worker_output_json": None,
        "pid": None,
        "error": None,
    }


def _write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    write_json(manifest_path, manifest)


def _should_run_async(case: BatchCase) -> bool:
    return case.algorithm.key in _setting("ASYNC_REMOTE_CASE_KEYS")


def _async_case_log_path(batch_dir: Path, case: BatchCase) -> Path:
    return batch_dir / "case_logs" / f"{case.case_key}.log"


def _async_case_output_path(batch_dir: Path, case: BatchCase) -> Path:
    return batch_dir / "async_results" / f"{case.case_key}.json"


def _launch_async_case(
    *,
    batch_dir: Path,
    manifest: dict[str, Any],
    manifest_path: Path,
    record: dict[str, Any],
) -> dict[str, Any]:
    case: BatchCase = record["case"]
    entry: dict[str, Any] = record["entry"]
    simulation_parameters: dict[str, Any] = record["simulation_parameters"]
    async_log_path = _async_case_log_path(batch_dir, case)
    async_output_path = _async_case_output_path(batch_dir, case)
    if async_output_path.exists():
        async_output_path.unlink()

    process = Process(
        target=_run_one_case_worker,
        args=(_case_run_kwargs(case, batch_dir), simulation_parameters, async_output_path, async_log_path),
        daemon=False,
    )
    process.start()

    entry["started_at"] = datetime.now().isoformat()
    entry["status"] = "running_async"
    entry["async_log_file"] = str(async_log_path.relative_to(workspace.root()))
    entry["worker_output_json"] = str(async_output_path.relative_to(workspace.root()))
    entry["pid"] = int(process.pid or 0)
    _write_manifest(manifest_path, manifest)
    print(f"[{record['index']:02d}/{record['case_count']}] Launched async {case.case_key} with PID {process.pid}")
    events.emit("batch_case", index=record["index"], total=record["case_count"], case=case.case_key)
    print(f"  Async log: {entry['async_log_file']}")
    return {
        "entry": entry,
        "process": process,
        "output_path": async_output_path,
    }


def _finalize_async_case(
    *,
    active_async: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
) -> bool:
    process: Process = active_async["process"]
    if process.is_alive():
        return False

    process.join(timeout=0)
    entry = active_async["entry"]
    entry["finished_at"] = datetime.now().isoformat()
    entry["pid"] = None
    output_path: Path = active_async["output_path"]

    payload: dict[str, Any] | None = None
    if output_path.exists():
        try:
            payload = _load_json(output_path)
        except (OSError, ValueError) as exc:
            payload = {"status": "failed", "error": {"type": type(exc).__name__,
                                                     "message": f"Unreadable worker output: {exc}", "traceback": None}}
    if payload is not None:
        if payload.get("status") == "completed":
            entry["status"] = "completed"
            entry["result_dir"] = payload.get("result_dir")
            entry["error"] = None
            print(f"  Result: {entry['result_dir']}")
            events.emit("batch_done", case=entry.get("case_key"), status="completed")
        else:
            entry["status"] = "failed"
            entry["error"] = payload.get("error")
            message = entry["error"].get("message") if isinstance(entry.get("error"), dict) else f"worker exited with code {process.exitcode}"
            print(f"  FAILED: {message}")
            events.emit("batch_done", case=entry.get("case_key"), status="failed")
    else:
        entry["status"] = "failed"
        entry["error"] = {
            "type": "RuntimeError",
            "message": f"Async worker exited with code {process.exitcode} without producing {output_path.relative_to(workspace.root())}",
            "traceback": None,
        }
        print(f"  FAILED: {entry['error']['message']}")
        events.emit("batch_done", case=entry.get("case_key"), status="failed")

    _write_manifest(manifest_path, manifest)
    return True


def _maybe_poll_async_case(
    *,
    active_async: dict[str, Any] | None,
    manifest: dict[str, Any],
    manifest_path: Path,
    block: bool,
) -> dict[str, Any] | None:
    if active_async is None:
        return None

    while True:
        if _finalize_async_case(active_async=active_async, manifest=manifest, manifest_path=manifest_path):
            return None
        if not block:
            return active_async
        time.sleep(5)


def _async_record(
    *,
    case: BatchCase,
    entry: dict[str, Any],
    simulation_parameters: dict[str, Any],
    index: int,
    case_count: int,
) -> dict[str, Any]:
    return {
        "case": case,
        "entry": entry,
        "simulation_parameters": simulation_parameters,
        "index": index,
        "case_count": case_count,
    }


def _extract_summary_metrics(run_metrics: dict[str, Any]) -> dict[str, Any]:
    metrics = run_metrics.get("matrix", {})
    structural = metrics.get("structural_metrics", {})
    original = structural.get("original", {})
    permuted = structural.get("permuted", {})
    permutation_check = metrics.get("permutation_check", {})

    summary_metrics = {
        "bandwidth_original": original.get("bandwidth"),
        "bandwidth_permuted": permuted.get("bandwidth"),
        "avg_bandwidth_original": original.get("avg_bandwidth"),
        "avg_bandwidth_permuted": permuted.get("avg_bandwidth"),
        "nnz_original": original.get("nnz"),
        "nnz_permuted": permuted.get("nnz"),
        "permutation_mismatches": permutation_check.get("mismatches"),
        "permutation_max_abs_err": permutation_check.get("max_abs_err"),
    }

    for percent in _setting("SUMMARY_PERCENT_BANDS"):
        percent_label = f"{percent:.1f}%" if float(percent).is_integer() else f"{percent}%"
        percent_key = str(percent).replace(".", "_")
        metric_key = f"frac_within_|i-j|<={percent_label}_of_n"
        summary_metrics[f"frac_{percent_key}pct_original"] = original.get(metric_key)
        summary_metrics[f"frac_{percent_key}pct_permuted"] = permuted.get(metric_key)

    return summary_metrics


def _build_batch_summary(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    summary_rows: list[dict[str, Any]] = []
    for entry in manifest.get("cases", []):
        row: dict[str, Any] = {
            "case_key": entry.get("case_key"),
            "geometry": entry.get("geometry"),
            "algorithm": entry.get("algorithm"),
            "partitioning_strategy": entry.get("partitioning_strategy"),
            "coarsening_size": entry.get("coarsening_size"),
            "coarsen_inferior_limit": entry.get("coarsen_inferior_limit"),
            "coarsen_superior_limit": entry.get("coarsen_superior_limit"),
            "status": entry.get("status"),
            "result_dir": entry.get("result_dir"),
            "parameters_source": entry.get("parameters_source"),
            "error_type": None,
            "error_message": None,
        }

        error = entry.get("error")
        if isinstance(error, dict):
            row["error_type"] = error.get("type")
            row["error_message"] = error.get("message")

        result_dir = entry.get("result_dir")
        if isinstance(result_dir, str) and result_dir:
            metrics_path = workspace.root() / result_dir / "run_metrics.json"
            if metrics_path.exists():
                try:  # one unreadable file must not cost the summary of every other case
                    row.update(_extract_summary_metrics(_load_json(metrics_path)))
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    row["error_type"] = row["error_type"] or type(exc).__name__
                    row["error_message"] = row["error_message"] or f"Unreadable {metrics_path.name}: {exc}"

        summary_rows.append(row)

    return summary_rows


def _write_batch_summary(batch_dir: Path, manifest: dict[str, Any]) -> Path:
    summary_rows = _build_batch_summary(manifest)
    json_path = batch_dir / "batch_summary.json"

    write_json(json_path, {"rows": summary_rows})

    return json_path


def _finalize_batch(batch_dir: Path, manifest_path: Path, manifest: dict[str, Any]) -> None:
    manifest["batch_finished_at"] = datetime.now().isoformat()
    summary_json = _write_batch_summary(batch_dir, manifest)
    manifest["summary_json"] = str(summary_json.relative_to(workspace.root()))
    _write_manifest(manifest_path, manifest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and run the configured batch study from batch/batch_configuration.json.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List the generated cases without executing them")
    parser.add_argument("--nohup", action="store_true", help="Run the batch in the background and write all printed output to batch.log inside the batch folder")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop the batch immediately if one case fails")
    return parser.parse_args(argv)


_CURRENT_BATCH: dict[str, Any] = {}
_UNFINISHED = ("pending", "running", "running_async")


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except BaseException as exc:  # cancelled (SIGTERM -> SystemExit), Ctrl+C or a crash
        _close_interrupted_batch(exc)
        raise
    finally:
        _CURRENT_BATCH.clear()


def _close_interrupted_batch(exc: BaseException) -> None:
    """Mark the cases that did not finish and write the summary, so the batch folder is consistent."""
    if not _CURRENT_BATCH:
        return
    manifest = _CURRENT_BATCH["manifest"]
    reason = "cancelled" if isinstance(exc, (SystemExit, KeyboardInterrupt)) else "failed"
    now = datetime.now().isoformat()
    for entry in manifest.get("cases", []):
        if entry.get("status") in _UNFINISHED:
            entry["status"] = reason
            entry["finished_at"] = now
            entry["pid"] = None
    manifest["interrupted"] = reason
    try:
        _finalize_batch(_CURRENT_BATCH["batch_dir"], _CURRENT_BATCH["manifest_path"], manifest)
        print(f"Batch {reason}: unfinished cases marked in {_CURRENT_BATCH['manifest_path'].name}")
    except Exception as finalize_error:  # never hide the original reason
        print(f"Could not finalize the interrupted batch: {finalize_error}")


def _main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = build_cases()

    if not cases:
        print("No cases matched the selected defaults.")
        return 1

    if args.nohup:
        return _launch_nohup(len(cases))

    print(f"Prepared {len(cases)} batch cases.")
    for index, case in enumerate(cases, start=1):
        print(f"{index:02d}. {case.case_key}")

    if args.dry_run:
        return 0

    events.emit("batch", total=len(cases))
    batch_dir = _resolve_batch_dir()
    manifest_path = batch_dir / "batch_manifest.json"
    batch_configuration_snapshot = _write_batch_configuration_snapshot(batch_dir)
    manifest: dict[str, Any] = {
        "batch_started_at": datetime.now().isoformat(),
        "batch_directory": str(batch_dir.relative_to(workspace.root())),
        "batch_configuration": str(batch_configuration_snapshot.relative_to(workspace.root())),
        "log_file": str((batch_dir / "batch.log").relative_to(workspace.root())),
        "cases": [],
    }
    # Seen by main() if the batch is interrupted (cancelled), to close the manifest properly.
    _CURRENT_BATCH.update(batch_dir=batch_dir, manifest_path=manifest_path, manifest=manifest)
    active_async: dict[str, Any] | None = None
    deferred_async_records: list[dict[str, Any]] = []
    stop_requested = False

    for index, case in enumerate(cases, start=1):
        active_async = _maybe_poll_async_case(
            active_async=active_async,
            manifest=manifest,
            manifest_path=manifest_path,
            block=False,
        )
        if stop_requested:
            break

        try:
            base_parameters = _load_validated_base_inputs(case.geometry)
            simulation_parameters = _build_case_parameters(case, base_parameters)
        except Exception as exc:
            entry = _case_to_manifest_entry(case)
            entry["finished_at"] = datetime.now().isoformat()
            entry["status"] = "failed"
            entry["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
            manifest["cases"].append(entry)
            _write_manifest(manifest_path, manifest)
            print(f"[{index:02d}/{len(cases)}] Running {case.case_key}")
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            events.emit("batch_case", index=index, total=len(cases), case=case.case_key)
            events.emit("batch_done", case=case.case_key, status="failed")
            if args.stop_on_error:
                stop_requested = True
            continue
        entry = _case_to_manifest_entry(case)
        manifest["cases"].append(entry)
        _write_manifest(manifest_path, manifest)
        record = _async_record(
            case=case,
            entry=entry,
            simulation_parameters=simulation_parameters,
            index=index,
            case_count=len(cases),
        )

        if _should_run_async(case):
            if active_async is None:
                active_async = _launch_async_case(
                    batch_dir=batch_dir,
                    manifest=manifest,
                    manifest_path=manifest_path,
                    record=record,
                )
            else:
                deferred_async_records.append(record)
                print(f"[{index:02d}/{len(cases)}] Deferred async {case.case_key} until the current remote QLM case completes")
            continue

        print(f"[{index:02d}/{len(cases)}] Running {case.case_key}")
        events.emit("batch_case", index=index, total=len(cases), case=case.case_key)
        entry["started_at"] = datetime.now().isoformat()
        entry["status"] = "running"
        _write_manifest(manifest_path, manifest)

        try:
            result_dir = _run_one_case(case, simulation_parameters, batch_dir)
        except Exception as exc:
            entry["finished_at"] = datetime.now().isoformat()
            entry["status"] = "failed"
            entry["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            _write_manifest(manifest_path, manifest)
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            events.emit("batch_done", case=case.case_key, status="failed")
            if args.stop_on_error:
                stop_requested = True
            continue

        entry["finished_at"] = datetime.now().isoformat()
        entry["status"] = "completed"
        entry["result_dir"] = str(result_dir.relative_to(workspace.root()))
        _write_manifest(manifest_path, manifest)
        print(f"  Result: {entry['result_dir']}")
        events.emit("batch_done", case=case.case_key, status="completed")

    if stop_requested and active_async is not None:
        print("Waiting for the active async remote QLM case to finish before stopping the batch")

    while active_async is not None or deferred_async_records:
        if active_async is None and deferred_async_records and not stop_requested:
            record = deferred_async_records.pop(0)
            active_async = _launch_async_case(
                batch_dir=batch_dir,
                manifest=manifest,
                manifest_path=manifest_path,
                record=record,
            )
        active_async = _maybe_poll_async_case(
            active_async=active_async,
            manifest=manifest,
            manifest_path=manifest_path,
            block=True,
        )
        if stop_requested and active_async is None:
            break

    _CURRENT_BATCH.clear()
    _finalize_batch(batch_dir, manifest_path, manifest)
    print(f"Batch manifest: {manifest_path.relative_to(workspace.root())}")
    print(f"Batch summary: {(batch_dir / 'batch_summary.json').relative_to(workspace.root())}")
    case_entries = manifest.get("cases", [])
    failed_keys = [str(entry.get("case_key")) for entry in case_entries if entry.get("status") == "failed"]
    if failed_keys:
        print(f"Batch finished: {len(failed_keys)} of {len(case_entries)} cases FAILED ({', '.join(failed_keys)})")
        return 1
    print(f"Batch finished: all {len(case_entries)} cases completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
