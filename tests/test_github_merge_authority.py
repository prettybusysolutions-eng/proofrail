import json
import socket
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrations.openclaw.github_adapter import GitHubMergeAdapter
from proofrail.control_plane import ControlPlane
from proofrail.core import ProofRailError
from proofrail.crypto import hash_record, sign_record, verify_signature
from proofrail.permit import (
    PermitError,
    execute_github_merge,
    mint_permit,
    verify_permit,
)


NOW = datetime(2026, 6, 11, 21, 30, tzinfo=timezone.utc)
IDENTITY_ROOT = "1" * 64
EVIDENCE_ROOT = "2" * 64
POLICY_ROOT = "3" * 64
STATE_ROOT = "4" * 64
APPROVAL_DIGEST = "5" * 64
HEAD_SHA = "abcdef1234567890"


class RecordingAdapter:
    def __init__(self, receipt=None):
        self.calls = []
        self.receipt = receipt or {
            "status": "success",
            "side_effect_confirmed": True,
            "remote_operation_id": "merge123",
        }

    def execute(self, action, *, idempotency_key):
        self.calls.append((action, idempotency_key))
        return self.receipt


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, body=None, idempotency_key=None):
        self.calls.append((method, path, body, idempotency_key))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def open_pull(*, head=HEAD_SHA, merged=False, merge_sha=None):
    return {
        "number": 42,
        "state": "closed" if merged else "open",
        "merged": merged,
        "mergeable": True,
        "merge_commit_sha": merge_sha,
        "head": {"sha": head},
        "base": {"sha": "1234567"},
        "html_url": "https://github.com/owner/repo/pull/42",
    }


class GitHubMergeAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()

    def permit(self, **overrides):
        values = {
            "identity_root": IDENTITY_ROOT,
            "evidence_root": EVIDENCE_ROOT,
            "policy_root": POLICY_ROOT,
            "state_root": STATE_ROOT,
            "approval_digest": APPROVAL_DIGEST,
            "repository": "owner/repo",
            "pull_number": 42,
            "expected_head_sha": HEAD_SHA,
            "merge_method": "squash",
            "nonce": "nonce-0000000000000001",
            "expires_at": NOW + timedelta(minutes=5),
            "issuer_principal_id": "verifier:primary",
            "issuer_role": "verifier",
            "private_key": self.private_key,
            "key_id": "verifier-key-1",
            "now": NOW,
        }
        values.update(overrides)
        return mint_permit(**values)

    def execute(self, permit, adapter, registry, **overrides):
        values = {
            "adapter": adapter,
            "registry_path": registry,
            "public_key": self.public_key,
            "expected_identity_root": IDENTITY_ROOT,
            "expected_evidence_root": EVIDENCE_ROOT,
            "expected_policy_root": POLICY_ROOT,
            "expected_state_root": STATE_ROOT,
            "expected_approval_digest": APPROVAL_DIGEST,
            "executor_id": "executor:github",
            "now": NOW,
        }
        values.update(overrides)
        return execute_github_merge(permit, **values)

    def test_merge_requires_a_single_use_signed_permit(self):
        adapter = RecordingAdapter()
        with TemporaryDirectory() as directory:
            registry = Path(directory) / "permits.sqlite3"
            with self.assertRaisesRegex(PermitError, "permit_missing"):
                self.execute(None, adapter, registry)
            self.assertEqual(adapter.calls, [])

            result = self.execute(self.permit(), adapter, registry)
            self.assertEqual(result["authority_state"], "RECONCILED")
            self.assertEqual(result["permit_claim"]["state"], "CONSUMED")
            self.assertEqual(len(adapter.calls), 1)
            action = adapter.calls[0][0]
            self.assertEqual(action["execution"]["expected_head_sha"], HEAD_SHA)
            self.assertEqual(action["execution"]["merge_method"], "squash")

    def test_expired_permit_is_denied_before_adapter_call(self):
        permit = self.permit(expires_at=NOW + timedelta(seconds=1))
        adapter = RecordingAdapter()
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(PermitError, "permit_expired"):
                self.execute(
                    permit,
                    adapter,
                    Path(directory) / "permits.sqlite3",
                    now=NOW + timedelta(seconds=1),
                )
        self.assertEqual(adapter.calls, [])

    def test_pr_head_change_invalidates_bound_state_before_execution(self):
        adapter = RecordingAdapter()
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(PermitError, "state_root_changed"):
                self.execute(
                    self.permit(),
                    adapter,
                    Path(directory) / "permits.sqlite3",
                    expected_state_root="6" * 64,
                )
        self.assertEqual(adapter.calls, [])

    def test_policy_hash_change_invalidates_permit(self):
        with self.assertRaisesRegex(PermitError, "policy_root_changed"):
            verify_permit(
                self.permit(),
                public_key=self.public_key,
                expected_identity_root=IDENTITY_ROOT,
                expected_evidence_root=EVIDENCE_ROOT,
                expected_policy_root="6" * 64,
                expected_state_root=STATE_ROOT,
                expected_approval_digest=APPROVAL_DIGEST,
                repository="owner/repo",
                pull_number=42,
                expected_head_sha=HEAD_SHA,
                merge_method="squash",
                now=NOW,
            )

    def test_approval_scope_change_invalidates_permit(self):
        with self.assertRaisesRegex(PermitError, "approval_scope_changed"):
            verify_permit(
                self.permit(),
                public_key=self.public_key,
                expected_identity_root=IDENTITY_ROOT,
                expected_evidence_root=EVIDENCE_ROOT,
                expected_policy_root=POLICY_ROOT,
                expected_state_root=STATE_ROOT,
                expected_approval_digest="6" * 64,
                repository="owner/repo",
                pull_number=42,
                expected_head_sha=HEAD_SHA,
                merge_method="squash",
                now=NOW,
            )

    def test_consumed_permit_cannot_be_replayed(self):
        permit = self.permit()
        adapter = RecordingAdapter()
        with TemporaryDirectory() as directory:
            registry = Path(directory) / "permits.sqlite3"
            self.execute(permit, adapter, registry)
            with self.assertRaisesRegex(PermitError, "permit_replayed"):
                self.execute(permit, adapter, registry)
        self.assertEqual(len(adapter.calls), 1)

    def test_learner_cannot_mint_or_promote_authority(self):
        with self.assertRaisesRegex(PermitError, "issuer_role_forbidden"):
            self.permit(
                issuer_principal_id="learner:policy",
                issuer_role="learner",
            )
        with TemporaryDirectory() as directory:
            control = ControlPlane(Path(directory) / "control.sqlite3")
            tenant = control.create_tenant("ProofRail")
            control.grant_role(tenant, "governor:primary", "governor")
            control.grant_role(tenant, "learner:policy", "learner")
            candidate = control.publish_policy(
                tenant_id=tenant,
                principal_id="governor:primary",
                policy_name="github-merge",
                document={"allowed_action_types": ["github_merge"]},
            )
            with self.assertRaisesRegex(ProofRailError, "lacks 'policy:activate'"):
                control.activate_policy(
                    tenant_id=tenant,
                    principal_id="learner:policy",
                    policy_name="github-merge",
                    version=candidate.version,
                )

    def test_executor_success_lie_is_caught_by_external_reconciliation(self):
        transport = FakeTransport(
            [
                (200, {}, open_pull()),
                (200, {}, {"merged": True, "sha": "claimed", "message": "merged"}),
                (200, {}, open_pull()),
            ]
        )
        adapter = GitHubMergeAdapter(transport)
        with TemporaryDirectory() as directory:
            result = self.execute(
                self.permit(),
                adapter,
                Path(directory) / "permits.sqlite3",
            )
        self.assertEqual(result["authority_state"], "RECONCILIATION_FAILED")
        self.assertEqual(result["adapter_receipt"]["status"], "unknown")
        self.assertFalse(result["adapter_receipt"]["side_effect_confirmed"])

    def test_ambiguous_execution_consumes_authority_without_replay(self):
        transport = FakeTransport(
            [
                (200, {}, open_pull()),
                socket.timeout("merge timed out"),
                socket.timeout("reconcile timed out"),
            ]
        )
        permit = self.permit()
        with TemporaryDirectory() as directory:
            registry = Path(directory) / "permits.sqlite3"
            result = self.execute(permit, GitHubMergeAdapter(transport), registry)
            self.assertEqual(result["authority_state"], "RECONCILIATION_FAILED")
            with self.assertRaisesRegex(PermitError, "permit_replayed"):
                self.execute(permit, RecordingAdapter(), registry)

    def test_ledger_record_mutation_is_tamper_evident(self):
        record = sign_record(
            {
                "kind": "proofrail.execution-receipt.v0.2",
                "receipt_id": "receipt-1",
                "previous_hash": "0" * 64,
                "outcome": "RECONCILED",
            },
            self.private_key,
            key_id="reconciler-key-1",
        )
        self.assertTrue(verify_signature(record, self.public_key))
        original_hash = hash_record(record)
        mutated = json.loads(json.dumps(record))
        mutated["outcome"] = "RECONCILIATION_FAILED"
        self.assertNotEqual(hash_record(mutated), original_hash)
        with self.assertRaisesRegex(ProofRailError, "Record hash mismatch"):
            verify_signature(mutated, self.public_key)


if __name__ == "__main__":
    unittest.main()
