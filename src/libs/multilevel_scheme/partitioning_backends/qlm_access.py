from __future__ import annotations

from functools import lru_cache
from time import perf_counter
from typing import Any


DEFAULT_QLM_QPU_NAME = "qat.qpus:QSolidQPU10"


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


def submit_qlm_job(
	qpu,
	job,
):
	"""Submit one QLM job and unwrap async results when needed."""
	try:
		result = qpu.submit(job)
		if hasattr(result, "join") and callable(result.join):
			result = result.join()
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