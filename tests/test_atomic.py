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

    def test_permissions_of_the_file_are_kept(self) -> None:
        import os
        import stat

        os.chmod(self.path, 0o664)
        write_json(self.path, {"new": True})
        self.assertEqual(0o664, stat.S_IMODE(self.path.stat().st_mode))
        fresh = Path(self.tmp.name) / "fresh.json"
        write_json(fresh, {})
        self.assertEqual(0o644, stat.S_IMODE(fresh.stat().st_mode))  # not mkstemp's 0600


class AppendLineTest(unittest.TestCase):
    def test_a_line_cut_short_by_a_crash_does_not_swallow_the_next_one(self) -> None:
        from libs.runtime.atomic import append_line

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.jsonl"
            path.write_text('{"a": 1}\n{"b": ')  # a writer died mid-line
            append_line(path, json.dumps({"c": 3}))
            lines = path.read_text().splitlines()
        self.assertEqual({"c": 3}, json.loads(lines[-1]))

    def test_concurrent_appends_keep_every_line_whole(self) -> None:
        import multiprocessing

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "trials.jsonl"
            ctx = multiprocessing.get_context("spawn")
            procs = [ctx.Process(target=_append_many, args=(str(path), n)) for n in range(4)]
            for p in procs:
                p.start()
            for p in procs:
                p.join(60)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(4 * 50, len(rows))


def _append_many(path: str, writer: int) -> None:
    from libs.runtime.atomic import append_line

    for i in range(50):  # large lines: more than one buffer each
        append_line(path, json.dumps({"writer": writer, "i": i, "pad": "x" * 20000}))


if __name__ == "__main__":
    unittest.main()
