"""Remote quantum calls survive transient network errors, a bounded number of times."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from libs.runtime.retry import call_with_retries


class Flaky:
    """Raises ``errors`` in turn, then returns ``value``."""

    def __init__(self, errors, value="ok"):
        self.errors, self.value, self.calls = list(errors), value, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.value


@patch("libs.runtime.retry.log")
class CallWithRetriesTest(unittest.TestCase):
    def test_transient_errors_are_retried_with_the_given_waits(self, log) -> None:
        fn, waits = Flaky([ConnectionError("reset"), ConnectionError("reset")]), []
        self.assertEqual("ok", call_with_retries(fn, retry_on=(ConnectionError,), what="x", delays=(1, 2), sleep=waits.append))
        self.assertEqual((3, [1, 2]), (fn.calls, waits))
        self.assertEqual(2, log.call_count)

    def test_gives_up_after_the_last_attempt(self, log) -> None:
        fn = Flaky([ConnectionError("a"), ConnectionError("b"), ConnectionError("c")])
        with self.assertRaisesRegex(ConnectionError, "c"):
            call_with_retries(fn, retry_on=(ConnectionError,), what="x", delays=(0, 0), sleep=lambda s: None)

    def test_other_errors_are_not_retried(self, log) -> None:
        fn = Flaky([ValueError("bad problem")])
        with self.assertRaises(ValueError):
            call_with_retries(fn, retry_on=(ConnectionError,), what="x", delays=(0, 0), sleep=lambda s: None)
        self.assertEqual(1, fn.calls)


@patch("libs.multilevel_scheme.partitioning.qaoa.qlm_access.log")
@patch("libs.multilevel_scheme.partitioning.qaoa.qlm_access.sleep")
@patch("libs.runtime.retry.QPU_RETRY_DELAYS", (0.0, 0.0))
class QlmPollingTest(unittest.TestCase):
    def _job(self, status, result=None):
        return SimpleNamespace(job_id="J1", get_status=status, get_result=result or (lambda: "R"))

    def test_status_polling_survives_network_errors(self, sleep, log) -> None:
        from libs.multilevel_scheme.partitioning.qaoa.qlm_access import _wait_for_qlm_async_result

        status = Flaky([OSError("reset"), TimeoutError("slow")], value="done")
        result = Flaky([ConnectionError("reset")], value="R")
        self.assertEqual("R", _wait_for_qlm_async_result(self._job(status, result), job_label="step", timeout_seconds=60))
        self.assertEqual((3, 2), (status.calls, result.calls))

    def test_status_polling_gives_up_after_repeated_failures(self, sleep, log) -> None:
        from libs.multilevel_scheme.partitioning.qaoa.qlm_access import _wait_for_qlm_async_result

        status = Flaky([OSError(str(i)) for i in range(10)], value="done")
        with self.assertRaises(OSError):
            _wait_for_qlm_async_result(self._job(status), job_label="step", timeout_seconds=60)
        self.assertEqual(4, status.calls)


@patch("libs.runtime.retry.log")
@patch("libs.runtime.retry.QPU_RETRY_DELAYS", (0.0, 0.0))
class DWaveSubmissionTest(unittest.TestCase):
    def test_a_dropped_connection_is_retried(self, log) -> None:
        from requests.exceptions import RequestException

        from libs.multilevel_scheme.partitioning.qa import dwave_access

        sample = Flaky([RequestException("connection reset")], value=SimpleNamespace(
            first=SimpleNamespace(sample={"a": 0, "b": 1}, energy=-1.0)))

        class Sampler:
            def __init__(self, **config):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        runtime = {
            "DWaveSampler": Sampler,
            "EmbeddingComposite": lambda qpu: SimpleNamespace(sample_qubo=sample),
            "FixedEmbeddingComposite": None,
            "SolverNotFoundError": type("SolverNotFoundError", (Exception,), {}),
            "RequestException": RequestException,
            "Urllib3HTTPError": type("HTTPError", (Exception,), {}),
        }
        with patch.object(dwave_access, "_get_dwave_runtime", return_value=runtime):
            best, energy = dwave_access.sample_qubo_on_dwave_qpu(
                {("a", "b"): 1.0}, logical_variables=["a", "b"], balance_lambda=0.0, num_reads=1)
        self.assertEqual(({"a": 0, "b": 1}, -1.0), (best, energy))
        self.assertEqual(2, sample.calls)


if __name__ == "__main__":
    unittest.main()
