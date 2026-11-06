import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from rag import gaps, pseudonym, sessionstore


class PseudonymTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = {k: os.environ.get(k) for k in ("PRIVACY_HASH_KEY", "PRIVACY_KEY_FILE")}
        os.environ.pop("PRIVACY_HASH_KEY", None)
        os.environ["PRIVACY_KEY_FILE"] = str(Path(self.tmp.name) / "key")

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_a_whatsapp_number_cannot_be_found_by_plain_sha256(self):
        number = "wa:4915112345678"
        plain = hashlib.sha256(("session:" + number).encode()).hexdigest()
        self.assertNotEqual(sessionstore.key_hash(number), plain)
        self.assertEqual(sessionstore.legacy_key_hash(number), plain)
        self.assertNotEqual(gaps.key_hash(number), hashlib.sha256(("gap:" + number).encode()).hexdigest()[:12])

    def test_stable_for_one_key_and_different_for_another(self):
        a = sessionstore.key_hash("wa:1")
        self.assertEqual(a, sessionstore.key_hash("wa:1"))
        self.assertNotEqual(a, sessionstore.key_hash("wa:2"))
        os.environ["PRIVACY_HASH_KEY"] = "k" * 40
        self.assertNotEqual(a, sessionstore.key_hash("wa:1"))

    def test_the_key_file_is_made_once_and_kept_private(self):
        first = pseudonym.keyed("x", "y")
        path = Path(os.environ["PRIVACY_KEY_FILE"])
        self.assertTrue(path.exists())
        self.assertGreaterEqual(len(path.read_text().strip()), 32)
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        pseudonym._cache.clear()
        self.assertEqual(pseudonym.keyed("x", "y"), first)  # read back from the file, not made again

    def test_forget_also_removes_records_written_with_the_old_hash(self):
        store = gaps.GapStore(folder=self.tmp.name)
        old = hashlib.sha256(b"gap:wa:49151").hexdigest()[:12]
        store.folder.mkdir(parents=True, exist_ok=True)
        store.path.write_text(f'{{"session": "{old}", "time": "2099-01-01T00:00:00+00:00"}}\n'
                              f'{{"session": "{gaps.key_hash("wa:49151")}", "time": "2099-01-01T00:00:00+00:00"}}\n'
                              '{"session": "other", "time": "2099-01-01T00:00:00+00:00"}\n', encoding="utf-8")
        self.assertEqual(store.forget("wa:49151"), 2)


if __name__ == "__main__":
    unittest.main()
