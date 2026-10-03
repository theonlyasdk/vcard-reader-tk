"""State persistence tests (isolated via VCARD_READER_STATE)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.state import MAX_RECENT, load_state, save_state, state_path


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("VCARD_READER_STATE")
        os.environ["VCARD_READER_STATE"] = str(Path(self.tmp.name) / "s.json")
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self.prev is None:
            os.environ.pop("VCARD_READER_STATE", None)
        else:
            os.environ["VCARD_READER_STATE"] = self.prev

    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_state(), {"recent": [], "last_dir": ""})

    def test_roundtrip(self):
        save_state(["a.vcf", "b.vcf"], "C:\\tmp")
        self.assertEqual(load_state(),
                         {"recent": ["a.vcf", "b.vcf"], "last_dir": "C:\\tmp"})

    def test_corrupt_file_gives_defaults(self):
        state_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(load_state(), {"recent": [], "last_dir": ""})

    def test_recent_capped(self):
        save_state([f"{i}.vcf" for i in range(10)])
        self.assertEqual(len(load_state()["recent"]), MAX_RECENT)

    def test_non_string_entries_ignored(self):
        state_path().parent.mkdir(parents=True, exist_ok=True)
        state_path().write_text(
            json.dumps({"recent": ["ok.vcf", 42, None], "last_dir": 7}),
            encoding="utf-8")
        self.assertEqual(load_state(), {"recent": ["ok.vcf"], "last_dir": ""})


if __name__ == "__main__":
    unittest.main()
