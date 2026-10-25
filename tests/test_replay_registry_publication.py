"""Core replay-registry publication must not expose a partly initialized SQLite file."""
from __future__ import annotations

import errno
import os
import sqlite3
import subprocess
import sys
import time
import unittest
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

from proofrail.core import ProofRailError
from proofrail.trust import (
    ensure_replay_registry,
    replay_claim_exists,
    replay_registry_root,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class ReplayRegistryPublicationTests(unittest.TestCase):
    def test_atomic_publication_is_invisible_until_both_tables_exist(self):
        """A second process may read while the writer is paused just before os.link."""
        with TemporaryDirectory() as d:
            directory = Path(d)
            registry = directory / "registry.sqlite3"
            ready, release = directory / "ready.flag", directory / "release.flag"
            code = """
import os
import sys
import time
from pathlib import Path
import proofrail.trust as trust

registry, ready, release = map(Path, sys.argv[1:])
original = os.link

def delayed_publish(src, dst):
    ready.write_text("ready")
    deadline = time.monotonic() + 10
    while not release.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("publication test was not released")
        time.sleep(.01)
    return original(src, dst)

trust.os.link = delayed_publish
trust.ensure_replay_registry(registry)
"""
            child = subprocess.Popen(
                [sys.executable, "-c", code, str(registry), str(ready), str(release)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ.copy(),
            )
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists(), "publisher did not reach the atomic link")
                self.assertFalse(registry.exists(), "partially initialized DB must be invisible")
                self.assertFalse(replay_claim_exists(registry, "e" * 64))
                # A second publisher wins while the first waits. The first must
                # accept the existing complete database without overwriting it.
                ensure_replay_registry(registry)
                self.assertTrue(registry.exists())
                with sqlite3.connect(f"file:{registry}?mode=ro", uri=True) as db:
                    names = {row[0] for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )}
                self.assertTrue({"permit_claims", "permit_events"} <= names)
                release.write_text("go")
                out, err = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, out + err)
            finally:
                release.write_text("go")
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=10)
            self.assertFalse(replay_claim_exists(registry, "e" * 64))
            self.assertEqual(
                replay_registry_root(registry),
                replay_registry_root(directory / "absent.sqlite3"),
            )
            self.assertFalse(list(directory.glob(".registry.sqlite3.*")))

    def test_existing_damaged_registry_is_not_recreated(self):
        with TemporaryDirectory() as d:
            registry = Path(d) / "registry.sqlite3"
            registry.write_bytes(b"")
            ensure_replay_registry(registry)
            with self.assertRaisesRegex(ProofRailError, "unreadable or corrupt"):
                replay_claim_exists(registry, "e" * 64)
            self.assertEqual(registry.stat().st_size, 0)

    def test_filesystem_without_hard_links_blocks_publication_without_leaving_registry(self):
        """Hard-link unavailability must fail closed, never expose an empty DB."""
        with TemporaryDirectory() as d:
            registry = Path(d) / "registry.sqlite3"
            with mock.patch(
                "proofrail.trust.os.link",
                side_effect=OSError(errno.EOPNOTSUPP, "hard links unsupported"),
            ):
                with self.assertRaises(OSError) as error:
                    ensure_replay_registry(registry)
            self.assertEqual(error.exception.errno, errno.EOPNOTSUPP)
            self.assertFalse(registry.exists())
            self.assertFalse(list(Path(d).glob(".registry.sqlite3.*")))
            self.assertFalse(replay_claim_exists(registry, "e" * 64))

    def test_idempotent_initialization_preserves_existing_claims(self):
        with TemporaryDirectory() as d:
            registry = Path(d) / "registry.sqlite3"
            ensure_replay_registry(registry)
            with sqlite3.connect(registry) as db:
                db.execute(
                    "INSERT INTO permit_claims VALUES (?,?,?,?,?)",
                    ("a" * 64, "unique-nonce", "executor-1", "now", "now"),
                )
            before = registry.read_bytes()
            ensure_replay_registry(registry)
            self.assertTrue(replay_claim_exists(registry, "a" * 64))
            self.assertEqual(registry.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
