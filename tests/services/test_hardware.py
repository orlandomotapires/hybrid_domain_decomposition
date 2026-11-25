import time
import unittest

from hdd.services import hardware


class HardwareStatusTest(unittest.TestCase):
    def test_local_backends_are_ready_and_status_is_quick(self) -> None:
        started = time.perf_counter()
        status = hardware.environment_status()
        self.assertLess(time.perf_counter() - started, 5.0)
        self.assertEqual({"metis", "qa_emulated", "qa_hardware", "qaoa_emulated", "qaoa_hardware"}, set(status["backends"]))
        self.assertEqual("ready", status["backends"]["metis"]["status"])
        for backend in status["backends"].values():
            self.assertIn(backend["status"], {"ready", "configured", "needs_credentials", "missing_sdk"})
        self.assertNotIn("token", str(status["environment"].get("dwave", {})).replace("token_env_set", "").replace("token_present", ""))


if __name__ == "__main__":
    unittest.main()
