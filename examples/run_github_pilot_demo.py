#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from integrations.openclaw.bridge import AdapterRegistry, OpenClawProofRailBridge
from integrations.openclaw.github_adapter import GitHubMergeAdapter
from integrations.siem import to_ecs_event
from proofrail.core import approve_action, sign_document


EVIDENCE_SECRET = b"pilot-evidence-secret"
APPROVAL_SECRET = b"pilot-approval-secret"
DECISION_SECRET = b"pilot-decision-secret"

ACTION = {
    "kind": "proofrail.action.v1",
    "action_id": "pilot-merge-42",
    "action_type": "github_merge",
    "target": "acme/platform#42",
    "risk": "high",
    "reversible": False,
    "claim_ids": ["checks-pass"],
    "requested_by": "agent:pilot",
    "execution": {
        "owner": "acme",
        "repo": "platform",
        "pull_number": 42,
        "expected_head_sha": "abc123",
        "merge_method": "squash",
    },
}

POLICY = {
    "allowed_action_types": ["github_merge"],
    "approval_required_for_risks": ["high", "critical"],
    "require_observed_for_risks": ["high", "critical"],
    "minimum_evidence_refs": {"high": 2},
    "max_evidence_age_seconds": 3600,
}


class DemoTransport:
    def __init__(self, *, head_sha: str, permit_merge: bool = False):
        self.head_sha = head_sha
        self.permit_merge = permit_merge
        self.calls: list[str] = []

    def request(self, method, path, *, body=None, idempotency_key=None):
        self.calls.append(f"{method} {path}")
        if method == "GET":
            return 200, {}, {
                "number": 42,
                "state": "open",
                "merged": False,
                "mergeable": True,
                "merge_commit_sha": None,
                "head": {"sha": self.head_sha},
                "base": {"sha": "base123"},
                "html_url": "https://github.com/acme/platform/pull/42",
            }
        if method == "PUT" and self.permit_merge:
            return 200, {}, {
                "merged": True,
                "sha": "merge789",
                "message": "Pull Request successfully merged",
            }
        raise AssertionError("Unexpected demo transport call")


def evidence() -> dict:
    return sign_document(
        {
            "kind": "proofrail.claim.v1",
            "claim_id": "checks-pass",
            "claim": "Required branch protection checks passed for abc123.",
            "epistemic_status": "observed",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "principal": "github:checks",
            "evidence": [
                {"uri": "github://acme/platform/check-runs/1001"},
                {"uri": "github://acme/platform/pull/42/head/abc123"},
            ],
        },
        EVIDENCE_SECRET,
        "pilot-evidence",
    )


def approval() -> dict:
    return approve_action(
        ACTION,
        approved_by="human:pilot-approver",
        scope="Merge acme/platform#42 only at head abc123.",
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        secret=APPROVAL_SECRET,
        key_id="pilot-approval",
    )


def bridge(directory: str, transport: DemoTransport) -> OpenClawProofRailBridge:
    registry = AdapterRegistry()
    registry.register("github_merge", GitHubMergeAdapter(transport))
    return OpenClawProofRailBridge(
        state_db=Path(directory) / "state.sqlite3",
        ledger_path=Path(directory) / "ledger.jsonl",
        registry=registry,
        evidence_secret=EVIDENCE_SECRET,
        approval_secret=APPROVAL_SECRET,
        decision_secret=DECISION_SECRET,
    )


def run_demo() -> dict:
    report: dict = {"kind": "proofrail.github-pilot-demo.v1", "scenarios": []}

    with TemporaryDirectory() as directory:
        transport = DemoTransport(head_sha="abc123")
        result = bridge(directory, transport).run(
            action=ACTION,
            evidence=[evidence()],
            policy=POLICY,
            approval=None,
            actor="agent:pilot",
        )
        report["scenarios"].append(
            {
                "scenario": "insufficient_approval",
                "result": result.status,
                "github_calls": transport.calls,
            }
        )

    with TemporaryDirectory() as directory:
        transport = DemoTransport(head_sha="changed456")
        result = bridge(directory, transport).run(
            action=ACTION,
            evidence=[evidence()],
            policy=POLICY,
            approval=approval(),
            actor="agent:pilot",
        )
        report["scenarios"].append(
            {
                "scenario": "approved_sha_changed",
                "result": result.status,
                "github_calls": transport.calls,
                "adapter": result.execution,
            }
        )

    with TemporaryDirectory() as directory:
        transport = DemoTransport(head_sha="abc123", permit_merge=True)
        governed_bridge = bridge(directory, transport)
        result = governed_bridge.run(
            action=ACTION,
            evidence=[evidence()],
            policy=POLICY,
            approval=approval(),
            actor="agent:pilot",
        )
        audit = governed_bridge.export_audit(result.decision["action_digest"])
        report["scenarios"].append(
            {
                "scenario": "approved_exact_sha",
                "result": result.status,
                "github_calls": transport.calls,
                "remote_operation_id": result.execution["remote_operation_id"],
                "ledger_valid": audit["ledger"]["valid"],
                "siem_event": to_ecs_event(audit, tenant_id="pilot-tenant"),
            }
        )

    return report


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, sort_keys=True))
