import unittest

from hdd.services.jobs.parsing import parse_log_line as _parse_log_line


class ParseLogLineLevelTests(unittest.TestCase):
    def level(self, line: str) -> str:
        return _parse_log_line(line)["level"]

    def test_failed_batch_case_is_error(self):
        line = (
            "  FAILED: ValueError: Unable to coarsen graph into the requested node-count range [1500, 2500]. "
            "The closest accepted coarse graph has 600 nodes, because the requested range could not be reached "
            "before hitting max_levels."
        )
        self.assertEqual(self.level(line), "ERROR")

    def test_failed_inside_info_bracket_is_error(self):
        self.assertEqual(self.level("[21:38:27 INFO] Simulation failed: boom"), "ERROR")

    def test_batch_summary_with_failures_is_error(self):
        self.assertEqual(self.level("Batch finished: 9 of 21 cases FAILED (a, b)"), "ERROR")

    def test_exception_and_traceback_are_error(self):
        self.assertEqual(self.level("RuntimeError: QPU unavailable"), "ERROR")
        self.assertEqual(self.level("Traceback (most recent call last):"), "ERROR")

    def test_warnings_are_warning(self):
        self.assertEqual(
            self.level(
                "/x/pennylane/_grad/grad.py:377: UserWarning: Attempted to differentiate a function with no trainable parameters."
            ),
            "WARNING",
        )
        self.assertEqual(
            self.level("/x/pennylane/devices/device_api.py:207: PennyLaneDeprecationWarning: Setting shots on device is deprecated."),
            "WARNING",
        )
        self.assertEqual(self.level("  warnings.warn("), "WARNING")

    def test_normal_lines_stay_info(self):
        self.assertEqual(self.level("  Result: matrices/matrix_02/results/run_20261104_213827_174075"), "INFO")
        self.assertEqual(self.level("Batch finished: all 21 cases completed"), "INFO")
        self.assertEqual(self.level("[21:38:27 VERBOSE] Permutation check passed with no mismatches"), "VERBOSE")
        self.assertEqual(self.level("[21:38:27 INFO] 0 failed cases"), "INFO")


if __name__ == "__main__":
    unittest.main()
