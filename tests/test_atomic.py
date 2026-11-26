"""Rewritten files are replaced in one step: a failed write leaves the old content."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from libs.runtime.atomic import atomic_write_json
from libs.runtime.utils import write_json


class AtomicWriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "params.json"
        self.path.write_text('{"old": true}')

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_value_that_cannot_be_serialised_leaves_the_file_intact(self) -> None:
        with self.assertRaises(TypeError):
            write_json(self.path, {"bad": object()})
        self.assertEqual({"old": True}, json.loads(self.path.read_text()))

    def test_a_failure_while_writing_leaves_the_file_intact_and_no_temporary_file(self) -> None:
        with patch("libs.runtime.atomic.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                atomic_write_json(self.path, {"new": True})
        self.assertEqual({"old": True}, json.loads(self.path.read_text()))
        self.assertEqual(["params.json"], [p.name for p in Path(self.tmp.name).iterdir()])

    def test_successful_write_replaces_the_content(self) -> None:
        write_json(self.path, {"new": True})
        self.assertEqual({"new": True}, json.loads(self.path.read_text()))


if __name__ == "__main__":
    unittest.main()
