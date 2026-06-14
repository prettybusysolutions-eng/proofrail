import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.generate_validation_report import generate


class AdversarialValidationTests(unittest.TestCase):
    def test_validation_report_preserves_attack_evidence(self):
        with TemporaryDirectory() as directory:
            report = Path(directory) / "VALIDATION_REPORT.md"
            evidence = Path(directory) / "validation-results.json"
            summary = generate(report, evidence)
            results = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual(summary["passed"], 13)
            self.assertEqual(summary["failed"], 0)
            self.assertEqual(summary["attacks"], len(results))
            self.assertIn("internally authored", report.read_text(encoding="utf-8"))
            self.assertIn("REPLAY-002", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
