import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_adapter_e2e as rule  # noqa: E402


ADAPTER = "class WidgetAdapter:\n    def execute(self, action, *, idempotency_key):\n        return {}\n"
TEST = ("import unittest\nfrom integrations.widget import WidgetAdapter\n\n"
        "class WidgetTests(unittest.TestCase):\n    def test_real(self):\n        WidgetAdapter()\n")


def tree(directory, *, adapter=ADAPTER, test=TEST, registry=None):
    root = Path(directory)
    for d in ("proofrail", "integrations", "tests"):
        (root / d).mkdir(exist_ok=True)
    (root / "integrations" / "widget.py").write_text(adapter)
    (root / "tests" / "test_widget.py").write_text(test)
    reg = {"adapters": {}, "excluded": {}} if registry is None else registry
    path = root / "tests" / "adapter_e2e_registry.json"
    path.write_text(json.dumps(reg))
    return root


DECLARED = {"adapters": {"integrations/widget.py:WidgetAdapter": {
    "real_component": "a real widget service",
    "tests": ["tests/test_widget.py::WidgetTests::test_real"]}}, "excluded": {}}


class AdapterE2ERuleTests(unittest.TestCase):
    def test_repository_satisfies_the_rule(self):
        self.assertEqual(rule.check(), [])

    def test_undeclared_adapter_fails(self):
        with TemporaryDirectory() as d:
            errors = rule.check(tree(d))
        self.assertTrue(any("undeclared adapter" in e for e in errors), errors)

    def test_declared_adapter_with_real_test_passes(self):
        with TemporaryDirectory() as d:
            self.assertEqual(rule.check(tree(d, registry=DECLARED)), [])

    def test_missing_test_method_fails(self):
        reg = json.loads(json.dumps(DECLARED))
        reg["adapters"]["integrations/widget.py:WidgetAdapter"]["tests"] = [
            "tests/test_widget.py::WidgetTests::test_gone"]
        with TemporaryDirectory() as d:
            errors = rule.check(tree(d, registry=reg))
        self.assertTrue(any("test method missing" in e for e in errors), errors)

    def test_test_that_never_references_the_adapter_fails(self):
        unrelated = TEST.replace("WidgetAdapter", "SomethingElse")
        with TemporaryDirectory() as d:
            errors = rule.check(tree(d, test=unrelated, registry=DECLARED))
        self.assertTrue(any("never references WidgetAdapter" in e for e in errors), errors)

    def test_unnamed_real_component_fails(self):
        reg = json.loads(json.dumps(DECLARED))
        reg["adapters"]["integrations/widget.py:WidgetAdapter"]["real_component"] = " "
        with TemporaryDirectory() as d:
            errors = rule.check(tree(d, registry=reg))
        self.assertTrue(any("real_component is not named" in e for e in errors), errors)

    def test_stale_registry_entry_fails(self):
        with TemporaryDirectory() as d:
            errors = rule.check(tree(d, adapter="X = 1\n", registry=DECLARED))
        self.assertTrue(any("no longer exists" in e for e in errors), errors)

    def test_protocols_are_not_adapters(self):
        protocol = ("from typing import Protocol\n"
                    "class WidgetAdapter(Protocol):\n    def execute(self): ...\n")
        with TemporaryDirectory() as d:
            self.assertEqual(rule.check(tree(d, adapter=protocol)), [])


if __name__ == "__main__":
    unittest.main()
