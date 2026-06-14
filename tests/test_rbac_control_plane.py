import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib import request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.control_plane import ControlPlane
from proofrail.rbac import PILOT_ROLE_PERMISSIONS, AuthorizationError, Principal
from proofrail.server import PilotControlPlane, make_server


class ConfirmedMergeAdapter:
    def __init__(self):
        self.calls = 0
        self.observed_merged = True
        self.observed_merge_sha = "merge123"

    def execute(self, action, *, idempotency_key):
        self.calls += 1
        return {
            "contract": "proofrail.adapter-receipt.v1",
            "idempotency_key": idempotency_key,
            "remote_operation_id": "merge123",
            "status": "success",
            "side_effect_confirmed": True,
            "retry_safe": True,
            "receipt_evidence": {"provider": "github", "observed": True},
        }

    def observe(self, action):
        return {
            "provider": "github",
            "quorum_met": True,
            "threshold": 2,
            "accepted": 2,
            "signers": ["audit", "provider"],
            "observation_root": "9" * 64,
            "http_status": 200,
            "merged": self.observed_merged,
            "merge_commit_sha": self.observed_merge_sha,
            "pull": {
                "number": action["execution"]["pull_number"],
                "merged": self.observed_merged,
                "merge_commit_sha": self.observed_merge_sha,
            },
        }


class RBACControlPlaneTests(unittest.TestCase):
    def test_pilot_roles_have_exact_non_overlapping_authority(self):
        self.assertEqual(
            PILOT_ROLE_PERMISSIONS["proposer"],
            {"intent:create", "evidence:create"},
        )
        self.assertIn("permit:mint", PILOT_ROLE_PERMISSIONS["verifier"])
        self.assertNotIn("action:execute", PILOT_ROLE_PERMISSIONS["verifier"])
        self.assertEqual(PILOT_ROLE_PERMISSIONS["learner"], {"proposal:create", "policy:read"})
        self.assertNotIn("policy:activate", PILOT_ROLE_PERMISSIONS["learner"])
        self.assertIn("policy:activate", PILOT_ROLE_PERMISSIONS["governor"])
        with self.assertRaises(AuthorizationError):
            Principal("tenant", "learner", "learner").require("permit:mint")

    def test_http_control_plane_enforces_full_role_separation(self):
        with TemporaryDirectory() as directory:
            adapter = ConfirmedMergeAdapter()
            app = PilotControlPlane(
                database=Path(directory) / "pilot.sqlite3",
                ledger_dir=Path(directory) / "ledgers",
                verifier_private_key=Ed25519PrivateKey.generate(),
                checkpoint_private_key=Ed25519PrivateKey.generate(),
                github_adapter=adapter,
            )
            tenant = app.control.create_tenant("Pilot")
            roles = (
                "proposer",
                "verifier",
                "executor",
                "reconciler",
                "learner",
                "governor",
                "auditor",
            )
            for role in roles:
                app.control.grant_role(tenant, role, role)
            policy = app.control.publish_policy(
                tenant_id=tenant,
                principal_id="governor",
                policy_name="github-merge",
                document={"allowed_action_types": ["github_merge"]},
            )
            app.control.activate_policy(
                tenant_id=tenant,
                principal_id="governor",
                policy_name="github-merge",
                version=policy.version,
            )

            proposer = self.headers(tenant, "proposer")
            verifier = self.headers(tenant, "verifier")
            executor = self.headers(tenant, "executor")
            reconciler = self.headers(tenant, "reconciler")
            auditor = self.headers(tenant, "auditor")

            status, intent, _ = app.request(
                "POST",
                "/intents",
                headers=proposer,
                body={
                    "action_type": "github_merge",
                    "target": "owner/repo#42",
                    "risk": "high",
                    "effect": {
                        "repository": "owner/repo",
                        "pull_number": 42,
                        "expected_head_sha": "abcdef1234567890",
                        "merge_method": "squash",
                    },
                },
            )
            self.assertEqual(status, 201)

            denied_status, _, _ = app.request(
                "POST",
                "/intents",
                headers=verifier,
                body={
                    "action_type": "github_merge",
                    "target": "owner/repo#42",
                    "effect": {},
                },
            )
            self.assertEqual(denied_status, 403)

            status, evidence, _ = app.request(
                "POST",
                "/evidence",
                headers=proposer,
                body={
                    "intent_id": intent["intent_id"],
                    "claims": [{"claim": "checks passed", "source": "github"}],
                },
            )
            self.assertEqual(status, 201)

            status, evaluation, _ = app.request(
                "POST",
                "/evaluate",
                headers=verifier,
                body={
                    "intent_id": intent["intent_id"],
                    "evidence_ids": [evidence["evidence_id"]],
                    "policy_name": "github-merge",
                    "state_root": "3" * 64,
                    "approval_digest": "4" * 64,
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(evaluation["decision"], "permit")

            status, permit, _ = app.request(
                "POST",
                "/permits",
                headers=verifier,
                body={
                    "evaluation_id": evaluation["evaluation_id"],
                    "nonce": "pilot-nonce-0000000001",
                },
            )
            self.assertEqual(status, 201)

            changed_policy = app.control.publish_policy(
                tenant_id=tenant,
                principal_id="governor",
                policy_name="github-merge",
                document={
                    "allowed_action_types": ["github_merge"],
                    "required_review_count": 2,
                },
            )
            app.control.activate_policy(
                tenant_id=tenant,
                principal_id="governor",
                policy_name="github-merge",
                version=changed_policy.version,
            )
            drift_status, drift, _ = app.request(
                "POST",
                "/execute/github-merge",
                headers=executor,
                body={"permit_id": permit["permit_id"]},
            )
            self.assertEqual(drift_status, 400)
            self.assertIn("policy_root_changed", drift["error"])
            self.assertEqual(adapter.calls, 0)
            status, updated_evaluation, _ = app.request(
                "POST",
                "/evaluate",
                headers=verifier,
                body={
                    "intent_id": intent["intent_id"],
                    "evidence_ids": [evidence["evidence_id"]],
                    "policy_name": "github-merge",
                    "state_root": "3" * 64,
                    "approval_digest": "4" * 64,
                },
            )
            self.assertEqual(status, 200)
            status, updated_permit, _ = app.request(
                "POST",
                "/permits",
                headers=verifier,
                body={"evaluation_id": updated_evaluation["evaluation_id"]},
            )
            self.assertEqual(status, 201)

            status, execution, _ = app.request(
                "POST",
                "/execute/github-merge",
                headers=executor,
                body={
                    "permit_id": updated_permit["permit_id"],
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(execution["state"], "CONSUMED")
            self.assertEqual(adapter.calls, 1)

            replay_status, replay, _ = app.request(
                "POST",
                "/execute/github-merge",
                headers=executor,
                body={
                    "permit_id": updated_permit["permit_id"],
                },
            )
            self.assertEqual(replay_status, 400)
            self.assertIn("permit_replayed", replay["error"])
            self.assertEqual(adapter.calls, 1)

            status, reconciliation, _ = app.request(
                "POST",
                "/reconcile/github-merge",
                headers=reconciler,
                body={
                    "execution_id": execution["execution_id"],
                    "observed_merged": False,
                    "observed_merge_sha": "forged-request-claim",
                },
            )
            self.assertEqual(status, 200)
            self.assertEqual(reconciliation["state"], "RECONCILED")
            self.assertEqual(reconciliation["observed_merge_sha"], "merge123")

            ledger_status, ledger, _ = app.request(
                "GET", "/ledger", headers=auditor
            )
            checkpoint_status, checkpoint, _ = app.request(
                "GET", "/checkpoint", headers=auditor
            )
            trust_status, trust_checkpoint, _ = app.request(
                "GET", "/checkpoint?scope=trust", headers=auditor
            )
            audit_status, audit, _ = app.request(
                "GET", "/audit/events?format=permit-lifecycle", headers=auditor
            )
            self.assertEqual(ledger_status, 200)
            self.assertTrue(ledger["verification"]["valid"])
            self.assertEqual(checkpoint_status, 200)
            self.assertEqual(checkpoint["kind"], "proofrail.merkle-checkpoint.v0.3")
            self.assertEqual(trust_status, 200)
            self.assertTrue(trust_checkpoint["verification"]["valid"])
            self.assertEqual(audit_status, 200)
            self.assertEqual(audit["permit_count"], 2)
            self.assertTrue(any(item["replayed"] for item in audit["permits"]))

            proposer_read_status, _, _ = app.request(
                "GET", "/ledger", headers=proposer
            )
            self.assertEqual(proposer_read_status, 403)
            _, reason_summary, _ = app.request(
                "GET", "/audit/events?format=reason-codes", headers=auditor
            )
            self.assertGreaterEqual(
                reason_summary["reason_codes"]["authorization_denied"],
                1,
            )

    def test_learner_cannot_promote_but_governor_can(self):
        with TemporaryDirectory() as directory:
            control = ControlPlane(Path(directory) / "control.sqlite3")
            tenant = control.create_tenant("Pilot")
            control.grant_role(tenant, "learner", "learner")
            control.grant_role(tenant, "governor", "governor")
            candidate = control.publish_policy(
                tenant_id=tenant,
                principal_id="governor",
                policy_name="merge",
                document={"allowed_action_types": ["github_merge"]},
            )
            with self.assertRaises(AuthorizationError):
                control.activate_policy(
                    tenant_id=tenant,
                    principal_id="learner",
                    policy_name="merge",
                    version=candidate.version,
                )
            active = control.activate_policy(
                tenant_id=tenant,
                principal_id="governor",
                policy_name="merge",
                version=candidate.version,
            )
            self.assertTrue(active.active)

    def test_real_http_boundary_routes_authenticated_request(self):
        with TemporaryDirectory() as directory:
            app = PilotControlPlane(
                database=Path(directory) / "pilot.sqlite3",
                ledger_dir=Path(directory) / "ledgers",
                verifier_private_key=Ed25519PrivateKey.generate(),
                checkpoint_private_key=Ed25519PrivateKey.generate(),
            )
            tenant = app.control.create_tenant("HTTP Pilot")
            app.control.grant_role(tenant, "proposer", "proposer")
            server = make_server("127.0.0.1", 0, app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                payload = json.dumps(
                    {
                        "action_type": "github_merge",
                        "target": "owner/repo#7",
                        "effect": {
                            "repository": "owner/repo",
                            "pull_number": 7,
                            "expected_head_sha": "abcdef1234567890",
                            "merge_method": "squash",
                        },
                    }
                ).encode()
                call = request.Request(
                    f"http://127.0.0.1:{server.server_port}/intents",
                    data=payload,
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "X-ProofRail-Tenant": tenant,
                        "X-ProofRail-Principal": "proposer",
                    },
                )
                with request.urlopen(call, timeout=5) as response:
                    result = json.loads(response.read())
                    self.assertEqual(response.status, 201)
                    self.assertEqual(result["action_type"], "github_merge")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    @staticmethod
    def headers(tenant: str, principal: str) -> dict[str, str]:
        return {
            "X-ProofRail-Tenant": tenant,
            "X-ProofRail-Principal": principal,
        }


if __name__ == "__main__":
    unittest.main()
