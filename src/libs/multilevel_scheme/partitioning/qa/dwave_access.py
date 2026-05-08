from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, NoReturn, Sequence

import numpy as np


@lru_cache(maxsize=1)
def _get_dwave_runtime() -> dict[str, Any]:
	try:
		from dwave.cloud.exceptions import SolverNotFoundError
		from dwave.system.composites import EmbeddingComposite, FixedEmbeddingComposite
		from dwave.system.samplers import DWaveSampler
		from minorminer.busclique import busgraph_cache
		from requests.exceptions import RequestException
		from urllib3.exceptions import HTTPError as Urllib3HTTPError

		return {
			"SolverNotFoundError": SolverNotFoundError,
			"RequestException": RequestException,
			"Urllib3HTTPError": Urllib3HTTPError,
			"DWaveSampler": DWaveSampler,
			"EmbeddingComposite": EmbeddingComposite,
			"FixedEmbeddingComposite": FixedEmbeddingComposite,
			"busgraph_cache": busgraph_cache,
		}
	except ImportError as exc:
		raise ImportError(
			"Quantum annealing on D-Wave requires the 'dwave-system' and 'minorminer' packages. "
			"Install them or set simulated=True."
		) from exc


def _format_qpu_selection(
	*,
	qpu_solver_name: str | None,
	qpu_region: str | None,
) -> str:
	details = []
	if qpu_solver_name:
		details.append(f"solver name '{qpu_solver_name}'")
	if qpu_region:
		details.append(f"region '{qpu_region}'")
	else:
		details.append("the current default region")

	detail_text = " in ".join(details[:1])
	if len(details) > 1:
		detail_text += f" for {details[1]}"
	return detail_text


def raise_qpu_solver_not_found_error(
	exc: BaseException,
	*,
	qpu_solver_name: str | None,
	qpu_region: str | None,
) -> NoReturn:
	detail_text = _format_qpu_selection(
		qpu_solver_name=qpu_solver_name,
		qpu_region=qpu_region,
	)
	raise RuntimeError(
		"Requested D-Wave solver is not available "
		f"{detail_text}. If you target Europe, set qpu_region='eu-central-1' "
		"or remove qpu_solver_name and let Leap choose an available QPU in that region."
	) from exc


def raise_qpu_connection_error(
	exc: BaseException,
	*,
	qpu_solver_name: str | None,
	qpu_region: str | None,
) -> NoReturn:
	detail_text = _format_qpu_selection(
		qpu_solver_name=qpu_solver_name,
		qpu_region=qpu_region,
	)
	raise RuntimeError(
		"D-Wave QPU request failed before results were returned: the connection to Leap was interrupted "
		f"({exc}). This is a network/Leap availability issue for {detail_text}, not a partitioning error. "
		"Retry later, reduce num_starts/num_reads, or set simulated=True for a local run."
	) from None


def raise_qpu_runtime_error(
	exc: BaseException,
	*,
	qpu_solver_name: str | None,
	qpu_region: str | None,
	solver_not_found_error: type[BaseException],
	qpu_connection_errors: tuple[type[BaseException], ...],
) -> NoReturn:
	if isinstance(exc, solver_not_found_error):
		raise_qpu_solver_not_found_error(
			exc,
			qpu_solver_name=qpu_solver_name,
			qpu_region=qpu_region,
		)
	if isinstance(exc, qpu_connection_errors):
		raise_qpu_connection_error(
			exc,
			qpu_solver_name=qpu_solver_name,
			qpu_region=qpu_region,
		)
	raise RuntimeError(f"D-Wave QPU request failed: {exc}") from exc


def _build_dwave_sampler_config(
	*,
	qpu_solver_name: str | None = None,
	qpu_region: str | None = None,
) -> dict[str, Any]:
	sampler_config: dict[str, Any] = {"solver": {"qpu": True}}

	if qpu_solver_name is not None and qpu_solver_name.strip():
		sampler_config["solver"]["name"] = qpu_solver_name.strip()
	if qpu_region is not None and qpu_region.strip():
		sampler_config["region"] = qpu_region.strip()

	return sampler_config


def uses_dense_balance_qubo(balance_lambda: float) -> bool:
	return not np.isclose(float(balance_lambda), 0.0)


@lru_cache(maxsize=8)
def get_qpu_dense_clique_capacity(
	qpu_solver_name: str | None,
	qpu_region: str | None,
) -> tuple[str, int]:
	runtime = _get_dwave_runtime()
	DWaveSampler = runtime["DWaveSampler"]
	busgraph_cache = runtime["busgraph_cache"]

	sampler_config = _build_dwave_sampler_config(
		qpu_solver_name=qpu_solver_name,
		qpu_region=qpu_region,
	)
	with DWaveSampler(**sampler_config) as qpu_sampler:
		solver_name = getattr(qpu_sampler.solver, "name", None) or qpu_solver_name or "configured solver"
		largest_clique = busgraph_cache(qpu_sampler.to_networkx_graph()).largest_clique()
		return solver_name, int(len(largest_clique))


def raise_if_dense_qubo_exceeds_qpu_capacity(
	logical_var_count: int,
	*,
	qpu_solver_name: str | None,
	qpu_region: str | None,
) -> None:
	solver_name, clique_capacity = get_qpu_dense_clique_capacity(
		qpu_solver_name,
		qpu_region,
	)
	if int(logical_var_count) <= int(clique_capacity):
		return

	raise ValueError(
		"QPU submission skipped before Leap execution: the balanced-cut QUBO is dense, "
		f"so this problem requires a clique embedding with {logical_var_count} logical variables, "
		f"but solver {solver_name} supports at most {clique_capacity}. "
		"Coarsen more before partitioning, reduce the coarse problem size, or set simulated=True."
	)


def _build_dense_qubo_embedding(
	qpu_sampler,
	logical_variables: Sequence[Any],
	*,
	qpu_solver_name: str | None,
) -> Mapping[Any, Sequence[int]]:
	runtime = _get_dwave_runtime()
	busgraph_cache = runtime["busgraph_cache"]

	embedding_cache = busgraph_cache(qpu_sampler.to_networkx_graph())
	embedding = embedding_cache.find_clique_embedding(list(logical_variables))
	if len(embedding) != len(logical_variables):
		solver_name = getattr(qpu_sampler.solver, "name", None) or qpu_solver_name or "configured solver"
		largest_clique = len(embedding_cache.largest_clique())
		raise ValueError(
			"QPU submission skipped before Leap execution: the balanced-cut QUBO is dense, "
			f"so this problem requires a clique embedding with {len(logical_variables)} logical variables, "
			f"but solver {solver_name} supports at most {largest_clique}. "
			"Coarsen more before partitioning, reduce the coarse problem size, or set simulated=True."
		)
	return embedding


def sample_qubo_on_dwave_qpu(
	Q: Mapping[tuple[Any, Any], float],
	*,
	logical_variables: Sequence[Any],
	balance_lambda: float,
	num_reads: int,
	qpu_solver_name: str | None = None,
	qpu_region: str | None = None,
	qpu_problem_label: str | None = None,
) -> tuple[dict[Any, int], float]:
	"""Submit a QUBO to a D-Wave QPU and return the best sample and energy."""
	runtime = _get_dwave_runtime()
	DWaveSampler = runtime["DWaveSampler"]
	EmbeddingComposite = runtime["EmbeddingComposite"]
	FixedEmbeddingComposite = runtime["FixedEmbeddingComposite"]
	solver_not_found_error = runtime["SolverNotFoundError"]
	qpu_connection_errors = (
		runtime["RequestException"],
		runtime["Urllib3HTTPError"],
		ConnectionError,
	)
	handled_errors = (solver_not_found_error, *qpu_connection_errors)

	sampler_config = _build_dwave_sampler_config(
		qpu_solver_name=qpu_solver_name,
		qpu_region=qpu_region,
	)
	variables = list(logical_variables)

	try:
		with DWaveSampler(**sampler_config) as qpu_sampler:
			if uses_dense_balance_qubo(balance_lambda):
				embedding = _build_dense_qubo_embedding(
					qpu_sampler,
					variables,
					qpu_solver_name=qpu_solver_name,
				)
				sampler = FixedEmbeddingComposite(qpu_sampler, embedding)
			else:
				sampler = EmbeddingComposite(qpu_sampler)

			best = sampler.sample_qubo(
				dict(Q),
				num_reads=int(num_reads),
				label=qpu_problem_label,
			).first
	except handled_errors as exc:
		raise_qpu_runtime_error(
			exc,
			qpu_solver_name=qpu_solver_name,
			qpu_region=qpu_region,
			solver_not_found_error=solver_not_found_error,
			qpu_connection_errors=qpu_connection_errors,
		)

	return dict(best.sample), float(best.energy)