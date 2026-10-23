"""Regression for F-3: never resolve security schemas from another package on sys.path."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class SchemaResourceIsolationTests(unittest.TestCase):
    def test_envelope_validator_uses_proofrail_schema_not_shadow_package(self):
        with tempfile.TemporaryDirectory(prefix="proofrail-schema-shadow-") as temp:
            shadow = Path(temp)
            fake_package = shadow / "schemas"
            fake_package.mkdir()
            (fake_package / "__init__.py").write_text("", encoding="utf-8")
            (fake_package / "action_authority_envelope.schema.json").write_text(
                '{"type":"object","properties":{"kind":{"const":"untrusted.schema"}}}',
                encoding="utf-8",
            )
            code = """
import importlib.util
import sys
from pathlib import Path

shadow_package = Path(sys.argv[1]).resolve() / "schemas" / "__init__.py"
resolved_package = Path(importlib.util.find_spec("schemas").origin).resolve()
assert resolved_package == shadow_package, (resolved_package, shadow_package)

from proofrail.envelope import _validator

schema = _validator().schema
assert schema["properties"]["kind"]["const"] == "proofrail.action-authority-envelope.v1", schema
"""
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join(
                part for part in (str(shadow), str(REPO_ROOT), env.get("PYTHONPATH", "")) if part
            )
            result = subprocess.run(
                [sys.executable, "-c", code, str(shadow)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
