"""Deterministic interleavings at the pilot execution-lock boundary."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from proofrail.server import PilotControlPlane


class ExecutionAdmissionTests(unittest.TestCase):
    def scenario(self, change):
        class Adapter:
            calls = 0

            def execute(self, action, *, idempotency_key):
                self.calls += 1
                return {"status": "success", "side_effect_confirmed": True,
                        "remote_operation_id": "fixture-only"}

        with TemporaryDirectory() as root:
            adapter = Adapter()
            app = PilotControlPlane(
                database=Path(root) / "control.sqlite", ledger_dir=Path(root) / "ledger",
                verifier_private_key=Ed25519PrivateKey.generate(),
                checkpoint_private_key=Ed25519PrivateKey.generate(), github_adapter=adapter,
            )
            tenant = app.control.create_tenant("fixture")
            for role in ("governor", "proposer", "verifier", "executor"):
                app.control.grant_role(tenant, role, role)

            def policy(document):
                published = app.control.publish_policy(
                    tenant_id=tenant, principal_id="governor", policy_name="merge", document=document)
                app.control.activate_policy(tenant_id=tenant, principal_id="governor",
                                           policy_name="merge", version=published.version)

            policy({"allowed_action_types": ["github_merge"]})

            def post(path, role, body):
                return app.request("POST", path, headers={"X-ProofRail-Tenant": tenant,
                                   "X-ProofRail-Principal": role}, body=body)

            status, intent, _ = post("/intents", "proposer", {
                "action_type": "github_merge", "target": "fixture/fixture#1", "risk": "high",
                "effect": {"repository": "fixture/fixture", "pull_number": 1,
                           "expected_head_sha": "a" * 40, "merge_method": "squash"}})
            self.assertEqual(status, 201)
            status, evidence, _ = post("/evidence", "proposer", {
                "intent_id": intent["intent_id"], "claims": [{"claim": "synthetic", "source": "fixture"}]})
            self.assertEqual(status, 201)
            status, evaluation, _ = post("/evaluate", "verifier", {
                "intent_id": intent["intent_id"], "evidence_ids": [evidence["evidence_id"]],
                "policy_name": "merge", "state_root": "3" * 64, "approval_digest": "4" * 64})
            self.assertEqual(status, 200)
            status, permit, _ = post("/permits", "verifier", {"evaluation_id": evaluation["evaluation_id"]})
            self.assertEqual(status, 201)

            # Model a completed governance change while execution is waiting
            # to enter its critical section, without timing-dependent sleeps.
            class AdmissionHook:
                def __enter__(self):
                    if change == "role":
                        app.control.grant_role(tenant, "executor", "learner")
                    else:
                        policy({"allowed_action_types": []})

                def __exit__(self, *args):
                    return False

            app._trust_lock = AdmissionHook()
            status, response, _ = post("/execute/github-merge", "executor", {"permit_id": permit["permit_id"]})
            return status, response, adapter.calls

    def test_role_removed_before_lock_admission_blocks_execution(self):
        status, response, calls = self.scenario("role")
        self.assertEqual(calls, 0, response)
        self.assertEqual(status, 403)

    def test_policy_changed_before_lock_admission_blocks_execution(self):
        status, response, calls = self.scenario("policy")
        self.assertEqual(calls, 0, response)
        self.assertEqual(status, 400)
        self.assertIn("policy_root_changed", response["error"])
