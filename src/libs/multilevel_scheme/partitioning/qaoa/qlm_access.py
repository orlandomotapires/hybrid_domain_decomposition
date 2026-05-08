from __future__ import annotations

from functools import lru_cache
import os
from queue import Queue
from threading import Thread
from time import perf_counter, sleep
from typing import Any

from libs.runtime.log import log


DEFAULT_QLM_QPU_NAME = "qat.qpus:QSolidQPU10"


def _default_qlm_job_timeout_seconds() -> float:
	default_timeout_seconds = 1800.0 * 6 # 3 hours
	raw_value = os.environ.get("HDD_QLM_JOB_TIMEOUT_SECONDS", str(default_timeout_seconds)).strip()
	try:
		parsed_value = float(raw_value)
	except ValueError:
		return default_timeout_seconds
	return parsed_value if parsed_value > 0.0 else default_timeout_seconds


DEFAULT_QLM_JOB_TIMEOUT_SECONDS = _default_qlm_job_timeout_seconds()


def _default_qlm_status_poll_interval_seconds() -> float:
	raw_value = os.environ.get("HDD_QLM_STATUS_POLL_INTERVAL_SECONDS", "30")
	try:
		parsed_value = float(raw_value)
	except ValueError:
		return 30.0
	return parsed_value if parsed_value > 0.0 else 30.0


DEFAULT_QLM_STATUS_POLL_INTERVAL_SECONDS = _default_qlm_status_poll_interval_seconds()


@lru_cache(maxsize=1)
def get_qlm_runtime() -> dict[str, Any]:
	try:
		import qat.lang.AQASM as aqasm
		from qat.qlmaas import QLMaaSConnection

		return {
			"Program": aqasm.Program,
			"H": aqasm.H,
			"CNOT": aqasm.CNOT,
			"RX": aqasm.RX,
			"RZ": aqasm.RZ,
			"QLMaaSConnection": QLMaaSConnection,
		}
	except ImportError as exc:
		raise ImportError(
			"QAOA on QLM requires the myQLM/qat packages. "
			"Install and configure myQLM or run with simulated=True for local PennyLane execution."
		) from exc


def get_qlm_qpu(
	*,
	qlm_qpu_name: str | None,
):
	target_name = (qlm_qpu_name or DEFAULT_QLM_QPU_NAME).strip()
	runtime = get_qlm_runtime()
	remote_qpu = runtime["QLMaaSConnection"]().get_qpu(target_name)
	return remote_qpu()


def get_qlm_qpu_api_summary(
	*,
	qlm_qpu_name: str | None = DEFAULT_QLM_QPU_NAME,
) -> dict[str, Any]:
	summary: dict[str, Any] = {}
	target_name = (qlm_qpu_name or DEFAULT_QLM_QPU_NAME).strip()

	try:
		runtime = get_qlm_runtime()
		connection = runtime["QLMaaSConnection"]()
		qpu_factory = connection.get_qpu(target_name)
		qpu = qpu_factory()
		resolved_qpu_name = getattr(qpu, "name", None) or getattr(qpu_factory, "name", None)
		if resolved_qpu_name is not None:
			summary["resolved_qpu_name"] = str(resolved_qpu_name)

		service_type = getattr(qpu, "service_type", None)
		if service_type is not None:
			summary["service_type"] = str(service_type)

		backend_description = (getattr(qpu, "description", None) or "").strip()
		if backend_description:
			summary["backend_description"] = backend_description

		if hasattr(qpu, "get_specs") and callable(qpu.get_specs):
			specs = qpu.get_specs()
			reported_max_qubits = getattr(specs, "nbqbits", None)
			if reported_max_qubits is not None:
				summary["reported_max_qubits"] = reported_max_qubits

			specs_description = getattr(specs, "description", None)
			if specs_description:
				summary["specs_description"] = specs_description

			processing_types = getattr(specs, "processing_types", None)
			if processing_types is not None:
				summary["processing_types"] = str(processing_types)

			topology = getattr(specs, "topology", None)
			if topology is not None:
				summary["topology"] = str(topology)

			meta_data = getattr(specs, "meta_data", None)
			if isinstance(meta_data, dict) and meta_data:
				summary["meta_data"] = meta_data
	except Exception as exc:
		summary["inspection_error"] = f"{type(exc).__name__}: {exc}"

	return summary


def _build_probe_job(num_qubits: int):
	runtime = get_qlm_runtime()
	Program = runtime["Program"]
	prog = Program()
	prog.qalloc(int(num_qubits))
	return prog.to_circ().to_job(nbshots=1)


def _resolve_qlm_job_timeout_seconds(timeout_seconds: float | None) -> float:
	resolved_timeout = DEFAULT_QLM_JOB_TIMEOUT_SECONDS if timeout_seconds is None else float(timeout_seconds)
	if resolved_timeout <= 0.0:
		raise ValueError("QLM job timeout must be > 0 seconds")
	return resolved_timeout


def _run_with_timeout(
	*,
	action_label: str,
	timeout_seconds: float,
	func,
):
	queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

	def _target() -> None:
		try:
			queue.put((True, func()))
		except BaseException as exc:
			queue.put((False, exc))

	thread = Thread(target=_target, name=f"qlm-{action_label}", daemon=True)
	thread.start()
	thread.join(timeout_seconds)
	if thread.is_alive():
		raise TimeoutError(f"Timed out after {timeout_seconds:.1f}s while {action_label}")

	succeeded, payload = queue.get()
	if succeeded:
		return payload
	raise payload


def _extract_qlm_job_id(async_result: Any) -> str | None:
	job_id = getattr(async_result, "job_id", None)
	if job_id is None:
		return None
	job_id_text = str(job_id).strip()
	return job_id_text or None


def _normalize_qlm_status(status_value: Any) -> str:
	return str(status_value).strip().lower()


def _safe_get_qlm_job_info(async_result: Any, timeout_seconds: float) -> Any | None:
	if not hasattr(async_result, "get_info") or not callable(async_result.get_info):
		return None
	try:
		return _run_with_timeout(
			action_label="retrieving QLM job info",
			timeout_seconds=timeout_seconds,
			func=async_result.get_info,
		)
	except Exception:
		return None


def _wait_for_qlm_async_result(
	async_result: Any,
	*,
	job_label: str,
	timeout_seconds: float,
) -> Any:
	job_id = _extract_qlm_job_id(async_result)
	status_poll_interval = DEFAULT_QLM_STATUS_POLL_INTERVAL_SECONDS
	total_started = perf_counter()
	deadline = total_started + timeout_seconds
	last_status = None
	last_logged_message = None
	success_statuses = {"done", "completed", "success", "finished"}
	failure_statuses = {"failed", "error", "cancelled", "canceled", "aborted", "killed"}

	if job_id is not None:
		log("VERBOSE", f"QLM job id for {job_label}: {job_id}")

	while True:
		remaining = deadline - perf_counter()
		if remaining <= 0.0:
			timeout_message = f"Timed out after {timeout_seconds:.1f}s while waiting for {job_label} result"
			if job_id is not None:
				timeout_message += f" (job_id={job_id}"
				if last_status is not None:
					timeout_message += f", last_status={last_status}"
				timeout_message += ")"
			raise TimeoutError(timeout_message)

		api_call_timeout = min(60.0, max(5.0, remaining))
		status_value = _run_with_timeout(
			action_label=f"polling status for {job_label}",
			timeout_seconds=api_call_timeout,
			func=async_result.get_status,
		)
		normalized_status = _normalize_qlm_status(status_value)
		elapsed = perf_counter() - total_started

		if normalized_status != last_status:
			status_message = f"{job_label} status: {normalized_status} after {elapsed:.1f}s"
			if job_id is not None:
				status_message += f" (job_id={job_id})"
			log("VERBOSE", status_message)
			last_status = normalized_status
			last_logged_message = status_message

		if normalized_status in success_statuses:
			result = _run_with_timeout(
				action_label=f"retrieving result for {job_label}",
				timeout_seconds=min(300.0, max(10.0, remaining)),
				func=async_result.get_result,
			)
			log("VERBOSE", f"Received {job_label} result from QLM in {perf_counter() - total_started:.2f}s")
			return result

		if normalized_status in failure_statuses:
			job_info = _safe_get_qlm_job_info(async_result, api_call_timeout)
			failure_message = f"QLM job failed for {job_label} with status {normalized_status}"
			if job_id is not None:
				failure_message += f" (job_id={job_id})"
			if job_info is not None:
				job_message = getattr(job_info, "message", None)
				if job_message:
					failure_message += f": {job_message}"
			raise RuntimeError(failure_message)

		if last_logged_message is None:
			log("VERBOSE", f"Still waiting for {job_label} result from QLM")

		sleep(min(status_poll_interval, 10.0, max(1.0, remaining)))


def submit_qlm_job(
	qpu,
	job,
	*,
	job_label: str | None = None,
	timeout_seconds: float | None = None,
):
	"""Submit one QLM job and unwrap async results when needed."""
	resolved_timeout = _resolve_qlm_job_timeout_seconds(timeout_seconds)
	resolved_job_label = (job_label or "QLM job").strip()
	try:
		log("VERBOSE", f"Submitting {resolved_job_label} to QLM (timeout: {resolved_timeout:.1f}s)")
		submit_started = perf_counter()
		result = _run_with_timeout(
			action_label=f"submitting {resolved_job_label}",
			timeout_seconds=resolved_timeout,
			func=lambda: qpu.submit(job),
		)
		log("VERBOSE", f"Submitted {resolved_job_label} to QLM in {perf_counter() - submit_started:.2f}s")
		if hasattr(result, "get_status") and callable(result.get_status) and hasattr(result, "get_result") and callable(result.get_result):
			log("VERBOSE", f"Waiting for {resolved_job_label} result from QLM (timeout: {resolved_timeout:.1f}s)")
			result = _wait_for_qlm_async_result(
				result,
				job_label=resolved_job_label,
				timeout_seconds=resolved_timeout,
			)
		elif hasattr(result, "join") and callable(result.join):
			log("VERBOSE", f"Waiting for {resolved_job_label} result from QLM (timeout: {resolved_timeout:.1f}s)")
			join_started = perf_counter()
			result = _run_with_timeout(
				action_label=f"waiting for {resolved_job_label} result",
				timeout_seconds=resolved_timeout,
				func=result.join,
			)
			log("VERBOSE", f"Received {resolved_job_label} result from QLM in {perf_counter() - join_started:.2f}s")
		else:
			log("VERBOSE", f"{resolved_job_label} returned synchronously from QLM")
		return result
	except Exception as exc:
		raise RuntimeError(f"QLM submit failed: {type(exc).__name__}: {exc}") from exc


def probe_qlm_backend_qubit_limit(
	*,
	qlm_qpu_name: str | None = DEFAULT_QLM_QPU_NAME,
	start_qubits: int = 20,
	stop_qubits: int = 30,
	step: int = 1,
) -> dict[str, Any]:
	if start_qubits <= 0:
		raise ValueError("start_qubits must be > 0")
	if stop_qubits < start_qubits:
		raise ValueError("stop_qubits must be >= start_qubits")
	if step <= 0:
		raise ValueError("step must be > 0")

	target_name = (qlm_qpu_name or DEFAULT_QLM_QPU_NAME).strip()
	qpu = get_qlm_qpu(qlm_qpu_name=qlm_qpu_name)
	attempts: list[dict[str, Any]] = []
	last_success_qubits = None
	first_failure_qubits = None

	for num_qubits in range(int(start_qubits), int(stop_qubits) + 1, int(step)):
		start_time = perf_counter()
		try:
			job = _build_probe_job(num_qubits)
			submit_qlm_job(qpu, job)
			attempts.append(
				{
					"num_qubits": num_qubits,
					"status": "ok",
					"elapsed_seconds": round(perf_counter() - start_time, 3),
					"error": None,
				}
			)
			last_success_qubits = num_qubits
		except Exception as exc:
			attempts.append(
				{
					"num_qubits": num_qubits,
					"status": "failed",
					"elapsed_seconds": round(perf_counter() - start_time, 3),
					"error": f"{type(exc).__name__}: {exc}",
				}
			)
			first_failure_qubits = num_qubits
			break

	return {
		"target_name": target_name,
		"start_qubits": int(start_qubits),
		"stop_qubits": int(stop_qubits),
		"step": int(step),
		"last_success_qubits": last_success_qubits,
		"first_failure_qubits": first_failure_qubits,
		"attempts": attempts,
	}


def validate_qlm_problem_size(
	*,
	n: int,
	qlm_qpu_name: str | None,
) -> None:
	target_name = (qlm_qpu_name or DEFAULT_QLM_QPU_NAME).strip()
	summary = get_qlm_qpu_api_summary(qlm_qpu_name=qlm_qpu_name)
	if summary.get("inspection_error"):
		raise RuntimeError(f"QLM backend inspection failed for {target_name}: {summary['inspection_error']}")

	capacity = summary.get("reported_max_qubits")
	if capacity is not None and int(n) > int(capacity):
		backend_name = str(summary.get("resolved_qpu_name") or target_name)
		raise ValueError(
			f"QAOA bipartition with n={n} exceeds the API-reported capacity {capacity} of {backend_name}."
		)