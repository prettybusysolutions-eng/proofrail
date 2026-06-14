import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from integrations.openclaw.bridge import AdapterRegistry, OpenClawProofRailBridge
from proofrail.core import approve_action, sign_document


EVIDENCE_SECRET = b"evidence-secret"
APPROVAL_SECRET = b"approval-secret"
DECISION_SECRET = b"decision-secret"


class CountingAdapter:
    def __init__(self):
        self.calls = 0

    def execute(self, action, *, idempotency_key):
        self.calls += 1
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": "result-1",
            "status": "success",
            "side_effect_confirmed": True,
            "retry_safe": True,
            "receipt_evidence": {"provider_receipt": "receipt-1"},
        }


class InvalidAdapter:
    def execute(self, action, *, idempotency_key):
        return {"status": "success"}


class UnknownAdapter:
    def __init__(self):
        self.calls = 0

    def execute(self, action, *, idempotency_key):
        self.calls += 1
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": None,
            "status": "unknown",
            "side_effect_confirmed": False,
            "retry_safe": False,
            "receipt_evidence": {"timeout_at": "provider boundary"},
        }


def action(risk="high"):
    return {
        "kind": "proofrail.action.v1",
        "action_id": "send-1",
        "action_type": "external_message",
        "target": "customer:1",
        "risk": risk,
        "reversible": True,
        "claim_ids": ["claim-1"],
        "requested_by": "agent:aurex",
        "payload": {"message": "Verified update"},
    }


def evidence():
    return sign_document(
        {
            "kind": "proofrail.claim.v1",
            "claim_id": "claim-1",
            "claim": "The customer requested this update.",
            "epistemic_status": "observed",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "principal": "channel:telegram",
            "evidence": [
                {"uri": "telegram://message/1"},
                {"uri": "session://approval/1"},
            ],
        },
        EVIDENCE_SECRET,
        "evidence-key",
    )


POLICY = {
    "allowed_action_types": ["external_message"],
    "approval_required_for_risks": ["high", "critical"],
    "require_observed_for_risks": ["high", "critical"],
    "minimum_evidence_refs": {"high": 2, "low": 1},
    "max_evidence_age_seconds": 3600,
}


class OpenClawBridgeTests(unittest.TestCase):
    def make_bridge(self, directory, adapter):
        registry = AdapterRegistry()
        registry.register("external_message", adapter)
        return OpenClawProofRailBridge(
            state_db=Path(directory) / "state.sqlite3",
            ledger_path=Path(directory) / "ledger.jsonl",
            registry=registry,
            evidence_secret=EVIDENCE_SECRET,
            approval_secret=APPROVAL_SECRET,
            decision_secret=DECISION_SECRET,
        )

    def test_denied_action_never_reaches_adapter(self):
        adapter = CountingAdapter()
        with TemporaryDirectory() as directory:
            bridge = self.make_bridge(directory, adapter)
            result = bridge.run(
                action=action(),
                evidence=[evidence()],
                policy=POLICY,
                approval=None,
                actor="agent:aurex",
            )
            self.assertEqual(result.status, "denied")
            self.assertEqual(adapter.calls, 0)

    def test_permitted_action_executes_once_and_replay_is_blocked(self):
        adapter = CountingAdapter()
        candidate = action()
        approval = approve_action(
            candidate,
            approved_by="human:kamm",
            scope="Send this exact customer update.",
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            secret=APPROVAL_SECRET,
            key_id="approval-key",
        )
        with TemporaryDirectory() as directory:
            bridge = self.make_bridge(directory, adapter)
            first = bridge.run(
                action=candidate,
                evidence=[evidence()],
                policy=POLICY,
                approval=approval,
                actor="agent:aurex",
            )
            second = bridge.run(
                action=candidate,
                evidence=[evidence()],
                policy=POLICY,
                approval=approval,
                actor="agent:aurex",
            )
            self.assertEqual(first.status, "success")
            self.assertEqual(second.status, "replay_blocked")
            self.assertEqual(adapter.calls, 1)
            audit = bridge.export_audit(first.decision["action_digest"])
            self.assertTrue(audit["ledger"]["valid"])

    def test_invalid_adapter_receipt_is_rejected(self):
        candidate = action(risk="low")
        with TemporaryDirectory() as directory:
            bridge = self.make_bridge(directory, InvalidAdapter())
            with self.assertRaisesRegex(Exception, "missing fields"):
                bridge.run(
                    action=candidate,
                    evidence=[evidence()],
                    policy={**POLICY, "approval_required_for_risks": [], "require_observed_for_risks": []},
                    approval=None,
                    actor="agent:aurex",
                )

    def test_unknown_side_effect_blocks_replay(self):
        adapter = UnknownAdapter()
        candidate = action(risk="low")
        with TemporaryDirectory() as directory:
            bridge = self.make_bridge(directory, adapter)
            first = bridge.run(
                action=candidate,
                evidence=[evidence()],
                policy={**POLICY, "approval_required_for_risks": [], "require_observed_for_risks": []},
                approval=None,
                actor="agent:aurex",
            )
            second = bridge.run(
                action=candidate,
                evidence=[evidence()],
                policy={**POLICY, "approval_required_for_risks": [], "require_observed_for_risks": []},
                approval=None,
                actor="agent:aurex",
            )
            self.assertEqual(first.status, "unknown")
            self.assertEqual(second.status, "replay_blocked")
            self.assertEqual(adapter.calls, 1)


if __name__ == "__main__":
    unittest.main()
