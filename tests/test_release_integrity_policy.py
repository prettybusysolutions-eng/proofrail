"""Regression checks for release-publication and documentation safeguards.

These tests inspect a proposed workflow. They cannot demonstrate that a real
Sigstore attestation has been minted: only a witnessed future release can.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pilot-release.yml"


class ReleaseWorkflowPolicyTests(unittest.TestCase):
    def test_no_automatic_release_trigger_or_non_main_publishing(self):
        text = WORKFLOW.read_text()
        self.assertRegex(text, r"(?m)^on:\n  workflow_dispatch:\n")
        self.assertNotRegex(text, r"(?m)^on:\n  push:")
        self.assertIn("if: github.ref == 'refs/heads/main'", text)
        self.assertIn("test \"$GITHUB_REF\" = 'refs/heads/main'", text)

    def test_attest_and_verify_all_assets_before_publication(self):
        text = WORKFLOW.read_text()
        self.assertIn("id-token: write", text)
        self.assertIn("attestations: write", text)
        self.assertIn("artifact-metadata: write", text)
        self.assertIn("uses: actions/attest@v4", text)
        self.assertIn("subject-path: 'dist/*'", text)
        self.assertIn("gh attestation verify \"$asset\"", text)
        self.assertIn("--source-ref \"refs/heads/main\"", text)
        self.assertIn('--source-digest "$GITHUB_SHA"', text)
        self.assertIn("--signer-workflow", text)
        self.assertIn('if git rev-parse --verify --quiet "refs/tags/$tag"', text)
        order = [
            "Build and test installed release artifact",
            "Record source and checksums",
            "Sign build provenance of every release asset",
            "Verify every release asset's signed provenance before publishing",
            "Publish idempotent exact-commit pilot release",
        ]
        positions = [text.index(x) for x in order]
        self.assertEqual(positions, sorted(positions))

    def test_governance_documents_are_present_and_do_not_claim_a_signed_prior_release(self):
        for path in ("CONTRIBUTING.md", "CHANGELOG.md", "MAINTAINERS.md",
                     "SECURITY.md", "RELEASING.md",
                     "docs/VERIFY_RELEASE_ATTESTATIONS.md"):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())
        changelog = (ROOT / "CHANGELOG.md").read_text()
        self.assertIn("unsigned", changelog)
        self.assertIn("v0.6.1", changelog)
        self.assertIn("[Unreleased]", changelog)
        security = (ROOT / "SECURITY.md").read_text()
        self.assertIn("7 calendar days", security)
        self.assertIn("not an SLA or a guarantee", security)


if __name__ == "__main__":
    unittest.main()
