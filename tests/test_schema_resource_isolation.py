"""Ensure the authority verifier reads its private packaged schema, not 'schemas'."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class SchemaResourceIsolationTests(unittest.TestCase):
    def test_authority_schema_does_not_drift_from_public_schema_contract(self):
        """The historical public schema is still shipped for compatibility."""
        installed = files("proofrail").joinpath(
            "authority_schemas", "action_authority_envelope.schema.json"
        )
        historical = REPO_ROOT / "schemas" / "action_authority_envelope.schema.json"
        self.assertEqual(
            json.loads(installed.read_text(encoding="utf-8")),
            json.loads(historical.read_text(encoding="utf-8")),
        )

    def test_shadowing_the_global_schemas_package_does_not_replace_authority_schema(self):
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
                cwd=shadow,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
