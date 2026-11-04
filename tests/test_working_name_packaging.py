"""Prevent accidentally distributing this project as someone else's PyPI name."""
from __future__ import annotations

import importlib.metadata
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkingNamePackagingTests(unittest.TestCase):
    def test_distribution_has_distinct_name(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["name"], "grantifold")
        self.assertNotEqual(data["project"]["name"], "proofrail")

    def test_new_cli_and_legacy_aliases_dispatch_same_implementation(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]
        self.assertEqual(scripts["grantifold"], "proofrail.cli:main")
        self.assertEqual(scripts["grantifold-server"], "proofrail.server:main")
        self.assertEqual(scripts["grantifold"], scripts["proofrail"])
        self.assertEqual(scripts["grantifold-server"], scripts["proofrail-server"])

    def test_brand_doc_explicitly_disallows_wrong_install(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        migration = (ROOT / "docs/BRAND_AND_PACKAGE_MIGRATION.md").read_text(encoding="utf-8")
        self.assertIn("pip install proofrail", readme)
        self.assertIn("does not install this", migration)
        self.assertIn("No trademark ownership", migration)
        self.assertIn("repository slug remain", readme)


if __name__ == "__main__":
    unittest.main()
