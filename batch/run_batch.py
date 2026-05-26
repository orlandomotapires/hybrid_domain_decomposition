#!/usr/bin/env python3
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


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
BATCH_DIR = ROOT_DIR / "batch"
BATCH_RUNS_DIR = BATCH_DIR / "runs"
BATCH_CONFIGURATION_PATH = BATCH_DIR / "batch_configuration.json"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from libs.runtime.runtime import run_simulation
from libs.runtime.utils import (
    resolve_matrix_input_path,
    resolve_parameters_file_path,
    validate_and_normalize_simulation_config,
    validate_and_normalize_simulation_parameters,
    write_json,
)

@dataclass(frozen=True)
class Geometry:
    key: str
    demonstrator_dir: str


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


def _load_batch_configuration() -> dict[str, Any]:
    configuration = _load_json(BATCH_CONFIGURATION_PATH)

    return {
        "async_remote_case_keys": tuple(str(key) for key in configuration.get("async_remote_case_keys", [])),
        "summary_percent_bands": tuple(float(value) for value in configuration.get("summary_percent_bands", [])),
        "common_defaults": _clone_json_like(configuration.get("common_defaults", {})),
        "geometries": tuple(
            Geometry(
                key=str(entry["key"]),
                demonstrator_dir=str(entry["demonstrator_dir"]),
            )
            for entry in configuration.get("geometries", [])
        ),
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

BATCH_CONFIGURATION = _load_batch_configuration()
ASYNC_REMOTE_CASE_KEYS = frozenset(BATCH_CONFIGURATION["async_remote_case_keys"])
SUMMARY_PERCENT_BANDS: tuple[float, ...] = BATCH_CONFIGURATION["summary_percent_bands"]
COMMON_DEFAULTS: dict[str, Any] = BATCH_CONFIGURATION["common_defaults"]
GEOMETRIES: tuple[Geometry, ...] = BATCH_CONFIGURATION["geometries"]
DEFAULT_COARSENING_PRESETS: tuple[CoarseningPreset, ...] = BATCH_CONFIGURATION["coarsening_presets"]
DEFAULT_ALGORITHM_PRESETS: tuple[AlgorithmPreset, ...] = BATCH_CONFIGURATION["algorithm_presets"]

def _apply_common_defaults(parameters: dict[str, Any], coarsening: CoarseningPreset) -> dict[str, Any]:
    updated = _clone_json_like(parameters)

    updated["general_parameters"].update(_clone_json_like(COMMON_DEFAULTS.get("general_parameters", {})))
    updated["coarsening_parameters"].update(_clone_json_like(COMMON_DEFAULTS.get("coarsening_parameters", {})))
    updated["partitioning_parameters"]["common"].update(_clone_json_like(COMMON_DEFAULTS.get("partitioning_common", {})))
    updated["coarsening_parameters"].update(
        {
            "coarsen_inferior_limit": int(coarsening.coarsen_inferior_limit),
            "coarsen_superior_limit": None if coarsening.coarsen_superior_limit is None else int(coarsening.coarsen_superior_limit),
        }
    )

    return updated

def _simulation_paths(geometry: Geometry) -> tuple[Path, Path, Path]:
    demonstrator_dir = ROOT_DIR / geometry.demonstrator_dir
    data_dir = demonstrator_dir / "data"
    config_path = data_dir / "simulation_config.json"
    return demonstrator_dir, data_dir, config_path

def _load_validated_base_inputs(geometry: Geometry) -> tuple[dict[str, Any], dict[str, Any], Path]:
    demonstrator_dir, data_dir, config_path = _simulation_paths(geometry)
    simulation_config = validate_and_normalize_simulation_config(_load_json(config_path))
    parameters_path = resolve_parameters_file_path(data_dir, simulation_config["parameters_file_path"])
    simulation_parameters = validate_and_normalize_simulation_parameters(_load_json(parameters_path))

    matrices_dir = data_dir / "matrices"
    resolve_matrix_input_path(matrices_dir, simulation_config["input_matrices"], key="matrix_k_file_path", label="K")
    resolve_matrix_input_path(matrices_dir, simulation_config["input_matrices"], key="matrix_m_file_path", label="M")
    return simulation_config, simulation_parameters, parameters_path

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
    for geometry in GEOMETRIES:
        for algorithm in DEFAULT_ALGORITHM_PRESETS:
            for coarsening in DEFAULT_COARSENING_PRESETS:
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
    write_json(snapshot_path, _load_json(BATCH_CONFIGURATION_PATH))
    return snapshot_path


def _batch_output_dir() -> Path:
    output_dir = BATCH_RUNS_DIR / datetime.now().strftime("batch_%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir
    


def _resolve_batch_dir() -> Path:
    env_batch_dir = os.environ.get("HDD_BATCH_DIR")
    if env_batch_dir:
        batch_dir = ROOT_DIR / env_batch_dir
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_dir
    return _batch_output_dir()


def _launch_nohup(case_count: int) -> int:
    batch_dir = _resolve_batch_dir()
    log_path = batch_dir / "batch.log"
    child_args = [arg for arg in sys.argv[1:] if arg != "--nohup"]
    child_env = dict(os.environ)
    child_env["HDD_BATCH_DIR"] = str(batch_dir.relative_to(ROOT_DIR))

    with log_path.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), *child_args],
            cwd=str(ROOT_DIR),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=child_env,
        )

    print(f"Started batch in background with PID {process.pid}")
    print(f"Prepared {case_count} batch cases.")
    print(f"Batch directory: {batch_dir.relative_to(ROOT_DIR)}")
    print(f"Batch log: {(batch_dir / 'batch.log').relative_to(ROOT_DIR)}")
    return 0


def _run_one_case(case: BatchCase, simulation_parameters: dict[str, Any]) -> Path:
    return run_simulation(case.geometry.demonstrator_dir, simulation_parameters_override=simulation_parameters)


def _run_one_case_worker(demonstrator_dir: str, simulation_parameters: dict[str, Any], output_json: Path, log_path: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", buffering=1) as handle:
        with redirect_stdout(handle), redirect_stderr(handle):
            try:
                result_dir = run_simulation(demonstrator_dir, simulation_parameters_override=simulation_parameters)
                write_json(
                    output_json,
                    {
                        "status": "completed",
                        "result_dir": str(result_dir.relative_to(ROOT_DIR)),
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
        "demonstrator_dir": case.geometry.demonstrator_dir,
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
    return case.algorithm.key in ASYNC_REMOTE_CASE_KEYS


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
        args=(case.geometry.demonstrator_dir, simulation_parameters, async_output_path, async_log_path),
        daemon=False,
    )
    process.start()

    entry["started_at"] = datetime.now().isoformat()
    entry["status"] = "running_async"
    entry["async_log_file"] = str(async_log_path.relative_to(ROOT_DIR))
    entry["worker_output_json"] = str(async_output_path.relative_to(ROOT_DIR))
    entry["pid"] = int(process.pid or 0)
    _write_manifest(manifest_path, manifest)
    print(f"[{record['index']:02d}/{record['case_count']}] Launched async {case.case_key} with PID {process.pid}")
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

    if output_path.exists():
        payload = _load_json(output_path)
        if payload.get("status") == "completed":
            entry["status"] = "completed"
            entry["result_dir"] = payload.get("result_dir")
            entry["error"] = None
            print(f"  Result: {entry['result_dir']}")
        else:
            entry["status"] = "failed"
            entry["error"] = payload.get("error")
            message = entry["error"].get("message") if isinstance(entry.get("error"), dict) else f"worker exited with code {process.exitcode}"
            print(f"  FAILED: {message}")
    else:
        entry["status"] = "failed"
        entry["error"] = {
            "type": "RuntimeError",
            "message": f"Async worker exited with code {process.exitcode} without producing {output_path.relative_to(ROOT_DIR)}",
            "traceback": None,
        }
        print(f"  FAILED: {entry['error']['message']}")

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


def _extract_summary_metrics(run_metrics: dict[str, Any], matrix_name: str) -> dict[str, Any]:
    metrics = run_metrics.get(matrix_name, {})
    structural = metrics.get("structural_metrics", {})
    original = structural.get("original", {})
    permuted = structural.get("permuted", {})
    permutation_check = metrics.get("permutation_check", {})

    summary_metrics = {
        f"{matrix_name}_bandwidth_original": original.get("bandwidth"),
        f"{matrix_name}_bandwidth_permuted": permuted.get("bandwidth"),
        f"{matrix_name}_avg_bandwidth_original": original.get("avg_bandwidth"),
        f"{matrix_name}_avg_bandwidth_permuted": permuted.get("avg_bandwidth"),
        f"{matrix_name}_nnz_original": original.get("nnz"),
        f"{matrix_name}_nnz_permuted": permuted.get("nnz"),
        f"{matrix_name}_permutation_mismatches": permutation_check.get("mismatches"),
        f"{matrix_name}_permutation_max_abs_err": permutation_check.get("max_abs_err"),
    }

    for percent in SUMMARY_PERCENT_BANDS:
        percent_label = f"{percent:.1f}%" if float(percent).is_integer() else f"{percent}%"
        percent_key = str(percent).replace(".", "_")
        metric_key = f"frac_within_|i-j|<={percent_label}_of_n"
        summary_metrics[f"{matrix_name}_frac_{percent_key}pct_original"] = original.get(metric_key)
        summary_metrics[f"{matrix_name}_frac_{percent_key}pct_permuted"] = permuted.get(metric_key)

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
            metrics_path = ROOT_DIR / result_dir / "run_metrics.json"
            if metrics_path.exists():
                run_metrics = _load_json(metrics_path)
                row.update(_extract_summary_metrics(run_metrics, "K"))
                row.update(_extract_summary_metrics(run_metrics, "M"))

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
    manifest["summary_json"] = str(summary_json.relative_to(ROOT_DIR))
    _write_manifest(manifest_path, manifest)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and run the configured batch study from batch/batch_configuration.json.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List the generated cases without executing them")
    parser.add_argument("--nohup", action="store_true", help="Run the batch in the background and write all printed output to batch.log inside the batch folder")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop the batch immediately if one case fails")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
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

    batch_dir = _resolve_batch_dir()
    manifest_path = batch_dir / "batch_manifest.json"
    batch_configuration_snapshot = _write_batch_configuration_snapshot(batch_dir)
    manifest: dict[str, Any] = {
        "batch_started_at": datetime.now().isoformat(),
        "batch_directory": str(batch_dir.relative_to(ROOT_DIR)),
        "batch_configuration": str(batch_configuration_snapshot.relative_to(ROOT_DIR)),
        "log_file": str((batch_dir / "batch.log").relative_to(ROOT_DIR)),
        "cases": [],
    }
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

        _, base_parameters, _ = _load_validated_base_inputs(case.geometry)
        simulation_parameters = _build_case_parameters(case, base_parameters)
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
        entry["started_at"] = datetime.now().isoformat()
        entry["status"] = "running"
        _write_manifest(manifest_path, manifest)

        try:
            result_dir = _run_one_case(case, simulation_parameters)
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
            if args.stop_on_error:
                stop_requested = True
            continue

        entry["finished_at"] = datetime.now().isoformat()
        entry["status"] = "completed"
        entry["result_dir"] = str(result_dir.relative_to(ROOT_DIR))
        _write_manifest(manifest_path, manifest)
        print(f"  Result: {entry['result_dir']}")

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

    _finalize_batch(batch_dir, manifest_path, manifest)
    print(f"Batch manifest: {manifest_path.relative_to(ROOT_DIR)}")
    print(f"Batch summary: {(batch_dir / 'batch_summary.json').relative_to(ROOT_DIR)}")
    if any(entry.get("status") == "failed" for entry in manifest.get("cases", [])):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
