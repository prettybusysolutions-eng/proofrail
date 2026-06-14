import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from proofrail.core import Ledger, ProofRailError, approve_action, evaluate_action, sign_document


EVIDENCE_SECRET = b"evidence-test-secret"
APPROVAL_SECRET = b"approval-test-secret"
NOW = datetime(2026, 6, 10, 1, 0, tzinfo=timezone.utc)


def claim(status="observed", refs=2, observed_at=None):
    document = {
        "kind": "proofrail.claim.v1",
        "claim_id": "claim-config-valid",
        "claim": "The candidate configuration passed schema validation.",
        "epistemic_status": status,
        "observed_at": (observed_at or NOW).isoformat(),
        "principal": "verifier:test",
        "evidence": [
            {"uri": f"file:///tmp/evidence-{index}.json", "sha256": "a" * 64}
            for index in range(refs)
        ],
    }
    return sign_document(document, EVIDENCE_SECRET, "evidence-test")


def action():
    return {
        "kind": "proofrail.action.v1",
        "action_id": "action-config-1",
        "action_type": "config_change",
        "target": "openclaw.json",
        "risk": "high",
        "reversible": True,
        "claim_ids": ["claim-config-valid"],
        "requested_by": "agent:test",
    }


POLICY = {
    "allowed_action_types": ["config_change"],
    "approval_required_for_risks": ["high", "critical"],
    "require_observed_for_risks": ["high", "critical"],
    "minimum_evidence_refs": {"high": 2},
    "max_evidence_age_seconds": 3600,
}


class ProofRailTests(unittest.TestCase):
    def test_permits_bound_observed_evidence_and_approval(self):
        candidate = action()
        approval = approve_action(
            candidate,
            approved_by="human:kamm",
            scope="Apply the exact validated config change.",
            expires_at=(NOW + timedelta(minutes=30)).isoformat(),
            secret=APPROVAL_SECRET,
            key_id="approval-test",
        )
        approval["approved_at"] = NOW.isoformat()
        approval = sign_document(
            {key: value for key, value in approval.items() if key != "signature"},
            APPROVAL_SECRET,
            "approval-test",
        )
        decision = evaluate_action(
            candidate,
            [claim()],
            POLICY,
            evidence_secret=EVIDENCE_SECRET,
            approval=approval,
            approval_secret=APPROVAL_SECRET,
            now=NOW,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reasons, ())

    def test_denies_tampered_evidence(self):
        tampered = claim()
        tampered["claim"] = "The configuration probably looks fine."
        decision = evaluate_action(
            action(),
            [tampered],
            POLICY,
            evidence_secret=EVIDENCE_SECRET,
            now=NOW,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("invalid_evidence_signature:claim-config-valid", decision.reasons)

    def test_denies_inference_for_high_risk_action(self):
        candidate = action()
        approval = approve_action(
            candidate,
            approved_by="human:kamm",
            scope="Exact action",
            expires_at=(NOW + timedelta(minutes=30)).isoformat(),
            secret=APPROVAL_SECRET,
            key_id="approval-test",
        )
        approval["approved_at"] = NOW.isoformat()
        approval = sign_document(
            {key: value for key, value in approval.items() if key != "signature"},
            APPROVAL_SECRET,
            "approval-test",
        )
        decision = evaluate_action(
            candidate,
            [claim(status="derived")],
            POLICY,
            evidence_secret=EVIDENCE_SECRET,
            approval=approval,
            approval_secret=APPROVAL_SECRET,
            now=NOW,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("claim_not_observed:claim-config-valid", decision.reasons)

    def test_hash_chain_detects_tampering(self):
        candidate = action()
        decision = evaluate_action(
            {**candidate, "risk": "low"},
            [claim(refs=1)],
            {
                **POLICY,
                "approval_required_for_risks": [],
                "require_observed_for_risks": [],
                "minimum_evidence_refs": {"low": 1},
            },
            evidence_secret=EVIDENCE_SECRET,
            now=NOW,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            ledger = Ledger(path)
            ledger.append(
                action={**candidate, "risk": "low"},
                decision=decision,
                outcome="succeeded",
                actor="agent:test",
            )
            self.assertTrue(ledger.verify()["valid"])
            entry = json.loads(path.read_text())
            entry["outcome"] = "fabricated"
            path.write_text(json.dumps(entry) + "\n")
            self.assertFalse(ledger.verify()["valid"])

    def test_receipt_rejects_decision_for_different_action(self):
        candidate = {**action(), "risk": "low"}
        decision = evaluate_action(
            candidate,
            [claim(refs=1)],
            {
                **POLICY,
                "approval_required_for_risks": [],
                "require_observed_for_risks": [],
                "minimum_evidence_refs": {"low": 1},
            },
            evidence_secret=EVIDENCE_SECRET,
            now=NOW,
        )
        with TemporaryDirectory() as directory:
            ledger = Ledger(Path(directory) / "ledger.jsonl")
            with self.assertRaises(ProofRailError):
                ledger.append(
                    action={**candidate, "target": "different-target"},
                    decision=decision,
                    outcome="succeeded",
                    actor="agent:test",
                )


if __name__ == "__main__":
    unittest.main()
