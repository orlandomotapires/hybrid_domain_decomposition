"""Job processes never import code from the workspace they run in."""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hdd.services.jobs.commands import job_command, job_environment

PLANTED = "from pathlib import Path\nPath(__file__).with_name('IMPORTED').write_text('x')\nraise SystemExit(3)\n"


class SafeLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "json.py").write_text(PLANTED)  # job_entry imports json first thing

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_plain_module_run_would_import_the_planted_file(self) -> None:
        # Control: shows the planted file is a real threat with ``python -m``.
        env = {k: v for k, v in job_environment(self.root).items() if k != "PYTHONSAFEPATH"}
        subprocess.run([sys.executable, "-m", "libs.runtime.job_entry", "--help"], cwd=self.root, env=env,
                       capture_output=True, timeout=60)
        self.assertTrue((self.root / "IMPORTED").exists())

    def test_job_command_ignores_modules_in_the_workspace(self) -> None:
        out = subprocess.run(job_command("single", ["--help"]), cwd=self.root, env=job_environment(self.root),
                             capture_output=True, text=True, timeout=60)
        self.assertFalse((self.root / "IMPORTED").exists())
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertIn("simulation_dir", out.stdout)


if __name__ == "__main__":
    unittest.main()
