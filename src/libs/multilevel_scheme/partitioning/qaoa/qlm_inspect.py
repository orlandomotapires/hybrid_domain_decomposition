from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
from typing import Any

from .qlm_access import (
	get_qlm_runtime,
	get_qlm_qpu_api_summary,
	probe_qlm_backend_qubit_limit,
)


def _truncate(value: Any, max_length: int = 96) -> str:
	text = str(value)
	if len(text) <= max_length:
		return text
	return text[: max_length - 3] + "..."


def _format_resources(resources: list[Any] | None) -> str:
	if not resources:
		return "-"

	formatted: list[str] = []
	for resource in resources:
		formatted.append(
			(
				f"{resource.qpu} "
				f"(qubits={resource.nbqbits}, jobs={resource.job_count}, nodes={resource.nb_nodes})"
			)
		)
	return "; ".join(formatted)


def _parse_timestamp(value: Any) -> datetime | None:
	if not value:
		return None
	text = str(value).strip()
	if not text:
		return None
	try:
		return datetime.fromisoformat(text)
	except ValueError:
		return None


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
	widths = [len(header) for header in headers]
	for row in rows:
		for index, cell in enumerate(row):
			widths[index] = max(widths[index], len(cell))

	def _format_row(row: list[str]) -> str:
		return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))

	print(_format_row(headers))
	print(_format_row(["-" * width for width in widths]))
	for row in rows:
		print(_format_row(row))


def _print_qpu_summary(connection: Any) -> None:
	qpus = sorted(str(qpu) for qpu in connection.get_qpus())
	print("QLM QPUs")
	print(f"count: {len(qpus)}")
	for qpu in qpus:
		print(f"- {qpu}")


def _print_qpu_details(connection: Any, qpu_name: str) -> None:
	summary = get_qlm_qpu_api_summary(qlm_qpu_name=qpu_name)

	print("QLM QPU")
	print(f"requested_qpu_name: {qpu_name}")
	if "resolved_qpu_name" in summary:
		print(f"resolved_qpu_name: {summary['resolved_qpu_name']}")
	if "inspection_error" in summary:
		print(f"inspection_error: {summary['inspection_error']}")
	if "service_type" in summary:
		print(f"service_type: {summary['service_type']}")
	if "reported_max_qubits" in summary:
		print(f"reported_max_qubits: {summary['reported_max_qubits']}")
	if "specs_description" in summary:
		print(f"specs_description: {summary['specs_description']}")
	if "processing_types" in summary:
		print(f"processing_types: {summary['processing_types']}")
	if "topology" in summary:
		print(f"topology: {summary['topology']}")
	if "meta_data" in summary:
		print(f"meta_data: {json.dumps(summary['meta_data'], sort_keys=True)}")
	if "backend_description" in summary:
		print()
		print("backend_description:")
		print(summary["backend_description"])


def _print_probe_summary(
	qpu_name: str,
	start_qubits: int,
	stop_qubits: int,
	step: int,
) -> None:
	probe = probe_qlm_backend_qubit_limit(
		qlm_qpu_name=qpu_name,
		start_qubits=start_qubits,
		stop_qubits=stop_qubits,
		step=step,
	)

	print("QLM QPU probe")
	print(f"name: {probe['target_name']}")
	print(f"range: {probe['start_qubits']}..{probe['stop_qubits']} step {probe['step']}")
	print(f"last_success_qubits: {probe['last_success_qubits']}")
	print(f"first_failure_qubits: {probe['first_failure_qubits']}")
	print()
	_print_table(
		["qubits", "status", "seconds", "error"],
		[
			[
				str(attempt["num_qubits"]),
				str(attempt["status"]),
				str(attempt["elapsed_seconds"]),
				_truncate(attempt["error"] or "-", 120),
			]
			for attempt in probe["attempts"]
		],
	)


def _print_job_summary(connection: Any, limit: int) -> None:
	jobs = connection.get_jobs()[:limit]
	if not jobs:
		print("\nRecent jobs")
		print("No jobs returned by the QLM API.")
		return

	rows: list[list[str]] = []
	for job in jobs:
		info = job.get_info()
		rows.append(
			[
				str(info.id),
				str(job.get_status()),
				str(info.owner),
				str(info.submission_date),
				_truncate(_format_resources(info.resources), 88),
			]
		)

	print("\nRecent jobs")
	print(f"showing first {len(rows)} jobs returned by the API")
	_print_table(
		["job_id", "status", "owner", "submitted", "resources"],
		rows,
	)


def _print_usage_summary(connection: Any, qpu_filter: str | None, usage_limit: int) -> None:
	jobs_info = list(connection.get_jobs_info())
	if qpu_filter:
		needle = qpu_filter.strip().lower()
		jobs_info = [
			info for info in jobs_info
			if any(str(getattr(resource, "qpu", "")).strip().lower() == needle for resource in (info.resources or []))
		]

	if usage_limit > 0:
		jobs_info = jobs_info[:usage_limit]

	print("QLM usage summary")
	if qpu_filter:
		print(f"qpu_filter: {qpu_filter}")
	if usage_limit > 0:
		print(f"job_limit: {usage_limit}")

	if not jobs_info:
		print("No matching jobs returned by the QLM API.")
		return

	total_runtime_seconds = 0.0
	total_resource_qubits = 0
	total_resource_job_count = 0
	per_qpu_stats: dict[str, dict[str, float]] = defaultdict(lambda: {"jobs": 0.0, "qubits": 0.0, "resource_jobs": 0.0, "runtime_seconds": 0.0})

	for info in jobs_info:
		resources = list(info.resources or [])
		start_dt = _parse_timestamp(getattr(info, "starting_date", None))
		end_dt = _parse_timestamp(getattr(info, "ending_date", None))
		runtime_seconds = 0.0
		if start_dt is not None and end_dt is not None:
			runtime_seconds = max(0.0, (end_dt - start_dt).total_seconds())
		total_runtime_seconds += runtime_seconds

		if not resources:
			per_qpu_stats["unknown"]["jobs"] += 1.0
			per_qpu_stats["unknown"]["runtime_seconds"] += runtime_seconds
			continue

		for resource in resources:
			qpu_name = str(getattr(resource, "qpu", "unknown"))
			nbqbits = int(getattr(resource, "nbqbits", 0) or 0)
			job_count = int(getattr(resource, "job_count", 0) or 0)
			total_resource_qubits += nbqbits
			total_resource_job_count += job_count
			per_qpu_stats[qpu_name]["jobs"] += 1.0
			per_qpu_stats[qpu_name]["qubits"] += float(nbqbits)
			per_qpu_stats[qpu_name]["resource_jobs"] += float(job_count)
			per_qpu_stats[qpu_name]["runtime_seconds"] += runtime_seconds

	print(f"jobs_returned: {len(jobs_info)}")
	print(f"total_runtime_seconds: {round(total_runtime_seconds, 3)}")
	print(f"total_reported_qubits: {total_resource_qubits}")
	print(f"total_reported_job_count: {total_resource_job_count}")
	print("credit_note: QLM API does not expose remaining credits in this environment; this is a usage summary only.")
	print()

	rows = []
	for qpu_name, stats in sorted(per_qpu_stats.items(), key=lambda item: (-item[1]["jobs"], item[0])):
		rows.append(
			[
				qpu_name,
				str(int(stats["jobs"])),
				str(int(stats["qubits"])),
				str(int(stats["resource_jobs"])),
				str(round(stats["runtime_seconds"], 3)),
			]
		)

	_print_table(
		["qpu", "jobs", "reported_qubits", "reported_job_count", "runtime_seconds"],
		rows,
	)


def _find_job(connection: Any, job_id: str) -> Any:
	for job in connection.get_jobs():
		if job.job_id == job_id:
			return job
	raise SystemExit(f"Job not found: {job_id}")


def _print_resource_details(resources: list[Any] | None) -> None:
	if not resources:
		print("resources: none")
		return

	print("resources:")
	for resource in resources:
		print(
			(
				f"- qpu={resource.qpu}, qubits={resource.nbqbits}, jobs={resource.job_count}, "
				f"nodes={resource.nb_nodes}, memory_mb={resource.mem_necessary_biggest_job_mb}"
			)
		)


def _print_result_preview(job: Any, sample_limit: int) -> None:
	result = job.get_result()
	raw_data = list(result.raw_data or [])

	print("\nResult preview")
	print(f"nbqbits: {result.nbqbits}")
	print(f"samples: {len(raw_data)}")
	print(f"meta_data: {json.dumps(result.meta_data or {}, sort_keys=True)}")

	for index, sample in enumerate(raw_data[:sample_limit], start=1):
		print(
			(
				f"sample_{index}: state={sample.state}, probability={sample.probability}, "
				f"err={sample.err}"
			)
		)


def _print_job_details(connection: Any, job_id: str, show_result: bool, sample_limit: int) -> None:
	job = _find_job(connection, job_id)
	info = job.get_info()

	print("QLM job")
	print(f"id: {info.id}")
	print(f"status: {job.get_status()}")
	print(f"owner: {info.owner}")
	print(f"type: {info.type}")
	print(f"submission_date: {info.submission_date}")
	print(f"starting_date: {info.starting_date}")
	print(f"ending_date: {info.ending_date}")
	print(f"queue_pos: {info.queue_pos}")
	print(f"message: {info.message}")
	print(f"job_file: {info.job_file}")
	print(f"result_file: {info.result_file}")
	print(f"session_id: {info.session_id}")
	print(f"meta_data: {json.dumps(info.meta_data or {}, sort_keys=True)}")
	_print_resource_details(info.resources)

	if show_result:
		_print_result_preview(job, sample_limit)


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="Inspect available QLM QPUs and recent QLM jobs from this repository environment."
	)
	parser.add_argument(
		"--limit-jobs",
		type=int,
		default=25,
		help="Number of jobs to display in the summary table.",
	)
	parser.add_argument(
		"--job-id",
		help="Show detailed information for one QLM job id.",
	)
	parser.add_argument(
		"--qpu",
		help="Show detailed specs for one QLM QPU name, for example qat.qpus:QSolidQPU10.",
	)
	parser.add_argument(
		"--probe-qpu",
		help="Probe a QLM QPU by submitting tiny jobs for increasing qubit counts.",
	)
	parser.add_argument(
		"--probe-start",
		type=int,
		default=20,
		help="Starting qubit count for --probe-qpu.",
	)
	parser.add_argument(
		"--probe-stop",
		type=int,
		default=30,
		help="Final qubit count for --probe-qpu.",
	)
	parser.add_argument(
		"--probe-step",
		type=int,
		default=1,
		help="Step size for --probe-qpu.",
	)
	parser.add_argument(
		"--usage-summary",
		action="store_true",
		help="Summarize historic QLM usage from get_jobs_info().",
	)
	parser.add_argument(
		"--usage-qpu",
		help="Restrict --usage-summary to one QPU name.",
	)
	parser.add_argument(
		"--usage-limit",
		type=int,
		default=0,
		help="Maximum number of jobs from get_jobs_info() to include in --usage-summary; 0 means all returned jobs.",
	)
	parser.add_argument(
		"--show-result",
		action="store_true",
		help="When used with --job-id, include a compact result preview.",
	)
	parser.add_argument(
		"--sample-limit",
		type=int,
		default=5,
		help="Maximum number of result samples to print in the result preview.",
	)
	parser.add_argument(
		"--skip-qpus",
		action="store_true",
		help="Skip the QPU list in the summary output.",
	)
	parser.add_argument(
		"--skip-jobs",
		action="store_true",
		help="Skip the recent jobs table in the summary output.",
	)
	return parser


def cli_main(argv: list[str] | None = None) -> None:
	parser = _build_parser()
	args = parser.parse_args(argv)

	if args.limit_jobs < 0:
		raise SystemExit("--limit-jobs must be >= 0")
	if args.sample_limit < 0:
		raise SystemExit("--sample-limit must be >= 0")
	if args.probe_start <= 0:
		raise SystemExit("--probe-start must be > 0")
	if args.probe_stop < args.probe_start:
		raise SystemExit("--probe-stop must be >= --probe-start")
	if args.probe_step <= 0:
		raise SystemExit("--probe-step must be > 0")
	if args.usage_limit < 0:
		raise SystemExit("--usage-limit must be >= 0")

	runtime = get_qlm_runtime()
	connection = runtime["QLMaaSConnection"]()

	if args.usage_summary:
		_print_usage_summary(connection, args.usage_qpu, args.usage_limit)
		return

	if args.probe_qpu:
		_print_probe_summary(args.probe_qpu, args.probe_start, args.probe_stop, args.probe_step)
		return

	if args.qpu:
		_print_qpu_details(connection, args.qpu)
		return

	if args.job_id:
		_print_job_details(connection, args.job_id, args.show_result, args.sample_limit)
		return

	if not args.skip_qpus:
		_print_qpu_summary(connection)
	if not args.skip_jobs:
		_print_job_summary(connection, args.limit_jobs)


if __name__ == "__main__":
	cli_main()