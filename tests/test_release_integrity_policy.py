"""Release-policy regression tests, including targeted fail-open mutations.

These inspect only the reviewed release-job YAML subset; the real action must
still be witnessed on a new version before signed provenance can be claimed.
No PyYAML dependency is required for these narrowly scoped policy checks.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/pilot-release.yml"

PINNED_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",  # v7
    "actions/setup-python": "6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",  # v7
    "actions/attest": "1e69f48acb82d1966a394da916b4c1698aa569d6",  # v4
}

SIGN = "Sign build provenance of every release asset"
VERIFY = "Verify every release asset's signed provenance before publishing"
PUBLISH = "Publish idempotent exact-commit pilot release"


def release_steps(workflow: str) -> tuple[str, list[tuple[str, str]]]:
    """Extract the release job and its top-level steps by YAML indentation.

    Fail closed on changes to the expected structure; this small parser is
    deliberately limited to the file's stable two-space indentation scheme.
    """
    lines = workflow.splitlines()
    matches = [i for i, line in enumerate(lines) if line == "  publish-pilot:"]
    if len(matches) != 1:
        raise ValueError("one publish-pilot job required")
    beginning = matches[0]
    ending = next((i for i in range(beginning + 1, len(lines))
                   if re.match(r"^  [A-Za-z_-][\w-]*:", lines[i])), len(lines))
    job_lines = lines[beginning:ending]
    if job_lines.count("    steps:") != 1:
        raise ValueError("expected one publish-pilot steps block")
    first = job_lines.index("    steps:")
    before_steps = "\n".join(job_lines[:first])
    bodies: list[tuple[str, str]] = []
    current_name = None
    current_lines: list[str] = []
    for line in job_lines[first + 1:]:
        if line.startswith("      - "):
            if current_name is not None:
                bodies.append((current_name, "\n".join(current_lines)))
            current_lines = [line]
            match = re.fullmatch(r"      - name: (.+)", line)
            current_name = match.group(1) if match else f"<unnamed:{len(bodies)}>"
        elif current_name is not None:
            current_lines.append(line)
        elif line.strip():
            raise ValueError("content before first release step")
    if current_name is not None:
        bodies.append((current_name, "\n".join(current_lines)))
    return before_steps, bodies


def assert_secure_release_workflow(workflow: str) -> None:
    """Raise AssertionError on known publication bypass patterns.

    This is a narrow static guardrail, not proof of all YAML/bash semantics.
    """
    assert re.search(r"(?m)^on:\n  workflow_dispatch:\n", workflow), "manual dispatch required"
    assert not re.search(r"(?m)^on:\n  push:", workflow), "no release on push"
    job, steps = release_steps(workflow)
    assert re.search(r"(?m)^    if: github.ref == 'refs/heads/main'$", job), "main-only job"
    for permission in ("contents: write", "id-token: write",
                       "attestations: write", "artifact-metadata: write"):
        assert permission in job, f"missing permission: {permission}"

    # Do not allow the workflow to mark any failing release step successful.
    assert not re.search(r"(?m)^\s*continue-on-error\s*:", workflow), "continue-on-error forbidden"
    assert not re.search(r"(?m)^\s*if\s*:\s*(false|\$\{\{\s*false\s*\}\})", job), "release job disabled"
    # Ignore YAML comments but never conceal failed shell commands.
    code = "\n".join(line for line in workflow.splitlines()
                     if not line.lstrip().startswith("#"))
    assert not re.search(r"\|\|\s*(true|:|exit\s+0)\b", code), "masked failure"
    assert not re.search(r"(?m)^\s*set\s+\+e\b", code), "errexit disabled"

    by_name = {name: body for name, body in steps}
    assert len(by_name) == len(steps), "duplicate step names"
    names = [name for name, _ in steps]
    must_run_in_order = [
        "Build and test installed release artifact",
        "Record source and checksums",
        SIGN,
        VERIFY,
        PUBLISH,
    ]
    assert all(name in by_name for name in must_run_in_order), "required release step missing"
    assert [names.index(name) for name in must_run_in_order] == sorted(
        names.index(name) for name in must_run_in_order
    ), "release steps out of order"

    # The actual step, not just stray text, must invoke the expected action SHA.
    uses = {}
    for _, body in steps:
        for match in re.finditer(r"(?m)^        uses: ([\w./-]+)@([^\s#]+)", body):
            repo, sha = match.groups()
            assert re.fullmatch(r"[a-f0-9]{40}", sha), f"mutable action reference {repo}@{sha}"
            uses[repo] = sha
    assert uses == PINNED_ACTIONS, f"unexpected signing-job action refs {uses}"

    signer = by_name[SIGN]
    verifier = by_name[VERIFY]
    publisher = by_name[PUBLISH]
    for name, body in ((SIGN, signer), (VERIFY, verifier), (PUBLISH, publisher)):
        assert not re.search(r"(?m)^        if\s*:", body), f"{name} can be skipped"
        assert not re.search(r"(?m)^        continue-on-error\s*:", body), f"{name} can ignore failure"
    assert f"uses: actions/attest@{PINNED_ACTIONS['actions/attest']}" in signer
    assert re.search(r"(?m)^          subject-path: 'dist/\*'$", signer)

    # Every asset must be verified in an unmasked, fail-fast loop.
    assert "        run: |" in verifier
    assert re.search(r"(?m)^          set -euo pipefail$", verifier)
    assert "for asset in dist/*; do" in verifier
    assert 'test -f "$asset"' in verifier
    assert 'gh attestation verify "$asset" --repo "$GITHUB_REPOSITORY"' in verifier
    assert '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/pilot-release.yml"' in verifier
    assert '--source-ref "refs/heads/main"' in verifier
    assert '--source-digest "$GITHUB_SHA"' in verifier
    assert "        run: |" in publisher
    assert "          set -euo pipefail" in publisher
    assert "gh release create" in publisher
    assert 'if git rev-parse --verify --quiet "refs/tags/$tag"' in publisher
    assert 'test "$GITHUB_REF" = \'refs/heads/main\'' in publisher
    assert '"build==1.3.0"' in workflow
    assert '"setuptools==84.0.0"' in workflow
    assert '"wheel==0.45.1"' in workflow


class ReleaseWorkflowPolicyTests(unittest.TestCase):
    def test_release_job_meets_fail_closed_policy(self):
        assert_secure_release_workflow(WORKFLOW.read_text())

    def test_fail_open_single_line_mutations_are_detected(self):
        baseline = WORKFLOW.read_text()
        assert_secure_release_workflow(baseline)
        mutations = {
            "ignored_verify_failure": baseline.replace(
                "      - name: " + VERIFY,
                "      - name: " + VERIFY + "\n        continue-on-error: true", 1),
            "skipped_signer": baseline.replace(
                "      - name: " + SIGN,
                "      - name: " + SIGN + "\n        if: false", 1),
            "masked_shell_failure": baseline.replace(
                '--source-digest "$GITHUB_SHA"',
                '--source-digest "$GITHUB_SHA" || true', 1),
        }
        for case, changed in mutations.items():
            with self.subTest(case=case):
                self.assertNotEqual(changed, baseline)
                with self.assertRaises(AssertionError):
                    assert_secure_release_workflow(changed)

    def test_documentation_does_not_claim_signed_historical_release(self):
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
