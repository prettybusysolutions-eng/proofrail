"""The live GitHub merge observer must remain read-only and fail closed."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.checkpoint import verify_checkpoint, verify_ledger
from proofrail.permit import mint_permit
from scripts import report_only_github_merges as report


REPO = "prettybusysolutions-eng/proofrail"
HEAD = "a" * 40
ROOTS = dict(identity="1"*64, evidence="2"*64, policy="3"*64, state="4"*64)
APPROVAL = "5"*64


def pull(number=60, head=HEAD, draft=True, base="main", mergeable=True):
    return {
        "number": number, "head": {"sha": head, "ref": "draft-branch"},
        "base": {"sha": "b"*40, "ref": base}, "state": "open",
        "merged": False, "draft": draft, "mergeable": mergeable,
        "updated_at": "2026-10-25T15:00:00Z",
        "html_url": f"https://github.com/{REPO}/pull/{number}",
    }


class ReportOnlyTests(unittest.TestCase):
    def test_without_independent_permit_always_refuses_real_pr_snapshot(self):
        row = report.analyze_one(REPO, pull(), reread=pull())
        self.assertEqual(row["result"], "REPORT_ONLY_REFUSED")
        self.assertIn("independent_authority_not_configured", row["refusal_reasons"])
        self.assertIn("draft_or_unknown", row["refusal_reasons"])
        self.assertEqual(row["provider_write_attempts"], 0)
        self.assertEqual(row["permit_consumptions"], 0)

    def test_head_change_between_readings_is_recorded(self):
        row = report.analyze_one(REPO, pull(), reread=pull(head="f"*40))
        self.assertIn("state_changed_between_reads", row["refusal_reasons"])
        self.assertEqual(row["pr"]["head_sha"], HEAD)
        self.assertEqual(row["pr"]["last_read_head_sha"], "f"*40)

    def test_actual_signed_permit_is_verified_without_spending(self):
        now = datetime.now(timezone.utc)
        signer = Ed25519PrivateKey.generate()
        permit = mint_permit(
            identity_root=ROOTS["identity"], evidence_root=ROOTS["evidence"],
            policy_root=ROOTS["policy"], state_root=ROOTS["state"],
            approval_digest=APPROVAL, repository=REPO, pull_number=60,
            expected_head_sha=HEAD, merge_method="squash", nonce="unique-report-only-0001",
            expires_at=now + timedelta(hours=1), issuer_principal_id="external-verifier",
            issuer_role="verifier", private_key=signer,
            key_id="external-verifier-1", now=now,
        )
        public = signer.public_key().public_bytes(serialization.Encoding.Raw,
                                                   serialization.PublicFormat.Raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "pr-60.json").write_text(json.dumps(permit))
            verified = report.analyze_one(REPO, pull(draft=False), permits_dir=path,
                                          public_key=public,
                                          trust_policy={"roots": ROOTS, "approval_digest": APPROVAL})
            self.assertEqual(verified["permit_verification"], "valid_under_supplied_roots")
            self.assertEqual(verified["result"], "REPORT_ONLY_REFUSED")
            self.assertIn("live_merge_enforcement_not_verified", verified["refusal_reasons"])
            self.assertEqual(verified["permit_consumptions"], 0)
            moved = report.analyze_one(REPO, pull(head="f"*40, draft=False),
                                       permits_dir=path, public_key=public,
                                       trust_policy={"roots": ROOTS, "approval_digest": APPROVAL})
            self.assertEqual(moved["permit_verification"], "refused")
            self.assertIn("pr_head_changed", moved["refusal_reasons"])

    def test_live_api_stub_sees_only_get_and_emits_verifiable_ledger(self):
        calls = []
        def mock_api(repo, path):
            calls.append((repo, path))
            return pull(number=int(path.rsplit("/", 1)[-1]))
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "audit"
            rc = report.main(["--repository", REPO, "--pulls", "60,59",
                              "--output", str(dest)], api=mock_api)
            self.assertEqual(rc, 0)
            self.assertEqual(len(calls), 4)
            self.assertEqual([p for _, p in calls], [
                f"/repos/{REPO}/pulls/60", f"/repos/{REPO}/pulls/60",
                f"/repos/{REPO}/pulls/59", f"/repos/{REPO}/pulls/59",
            ])
            summary = json.loads((dest / "report.json").read_text())
            self.assertEqual(summary["num_authorized_merges"], 0)
            self.assertEqual(summary["write_requests"], 0)
            self.assertEqual(summary["checkpoint_signing"], "unsigned_report")
            self.assertFalse(summary["independent_retention_proven"])
            self.assertTrue(verify_ledger(dest / "report-only-ledger.jsonl")["valid"])

    def test_signed_checkpoint_detects_removed_final_observation(self):
        with tempfile.TemporaryDirectory() as d:
            destination = Path(d)
            row1 = report.analyze_one(REPO, pull(60))
            row2 = report.analyze_one(REPO, pull(59))
            ledger = destination / "ledger.jsonl"
            report.make_ledger([row1, row2], ledger)
            secret = Ed25519PrivateKey.generate()
            signed = report.create_checkpoint(ledger, private_key=secret, key_id="test-key")
            self.assertTrue(verify_checkpoint(signed, ledger, public_key=secret.public_key())["valid"])
            lines = ledger.read_text().splitlines()
            ledger.write_text(lines[0] + "\n")
            self.assertTrue(verify_ledger(ledger)["valid"],
                            "Hash chain alone cannot detect truncation")
            checked = verify_checkpoint(signed, ledger, public_key=secret.public_key())
            self.assertFalse(checked["valid"])
            self.assertIn("checkpoint_entry_count_mismatch", checked["errors"])


if __name__ == "__main__":
    unittest.main()
