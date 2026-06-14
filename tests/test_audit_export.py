import json
import unittest

from proofrail.audit_export import (
    ecs_security_events,
    jsonl_audit_export,
    permit_lifecycle_report,
    reason_code_summary,
)


EVENTS = [
    {
        "event_id": "event-1",
        "sequence": 1,
        "observed_at": "2026-06-11T22:00:00Z",
        "tenant_id": "tenant-1",
        "principal_id": "verifier-1",
        "role": "verifier",
        "action": "permit.mint",
        "outcome": "permitted",
        "reason_codes": ["single_use_permit_minted"],
        "object_type": "permit",
        "object_id": "permit-1",
        "permit_hash": "a" * 64,
        "state": "PERMITTED",
        "metadata": {},
    },
    {
        "event_id": "event-2",
        "sequence": 2,
        "observed_at": "2026-06-11T22:01:00Z",
        "tenant_id": "tenant-1",
        "principal_id": "executor-1",
        "role": "executor",
        "action": "github_merge.execute",
        "outcome": "failure",
        "reason_codes": ["reconciliation_failed", "permit_replayed"],
        "object_type": "execution",
        "object_id": "execution-1",
        "permit_hash": "a" * 64,
        "state": "CONSUMED",
        "metadata": {"adapter_status": "unknown"},
    },
    {
        "event_id": "event-3",
        "sequence": 3,
        "observed_at": "2026-06-11T22:02:00Z",
        "tenant_id": "tenant-1",
        "principal_id": "reconciler-1",
        "role": "reconciler",
        "action": "github_merge.reconcile",
        "outcome": "failure",
        "reason_codes": ["provider_outcome_not_confirmed"],
        "object_type": "reconciliation",
        "object_id": "reconciliation-1",
        "permit_hash": "a" * 64,
        "state": "RECONCILIATION_FAILED",
        "metadata": {},
    },
]


class AuditExportTests(unittest.TestCase):
    def test_jsonl_export_is_canonical_and_replayable(self):
        exported = jsonl_audit_export(EVENTS)
        parsed = [json.loads(line) for line in exported.splitlines()]
        self.assertEqual(parsed, EVENTS)
        self.assertTrue(exported.endswith("\n"))

    def test_ecs_export_preserves_security_context(self):
        events = ecs_security_events(EVENTS)
        self.assertEqual(events[0]["ecs.version"], "8.11.0")
        self.assertEqual(events[0]["organization.id"], "tenant-1")
        self.assertEqual(events[1]["event.outcome"], "failure")
        self.assertEqual(events[2]["proofrail.state"], "RECONCILIATION_FAILED")

    def test_reason_code_summary_counts_outcomes_and_denials(self):
        summary = reason_code_summary(EVENTS)
        self.assertEqual(summary["event_count"], 3)
        self.assertEqual(summary["reason_codes"]["permit_replayed"], 1)
        self.assertEqual(summary["outcomes"]["failure"], 2)

    def test_permit_lifecycle_report_groups_states_and_replay(self):
        report = permit_lifecycle_report(EVENTS)
        self.assertEqual(report["permit_count"], 1)
        permit = report["permits"][0]
        self.assertEqual(
            permit["states"],
            ["PERMITTED", "CONSUMED", "RECONCILIATION_FAILED"],
        )
        self.assertEqual(permit["terminal_state"], "RECONCILIATION_FAILED")
        self.assertTrue(permit["replayed"])


if __name__ == "__main__":
    unittest.main()
