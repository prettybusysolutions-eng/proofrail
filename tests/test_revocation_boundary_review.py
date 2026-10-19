"""Counterexample tests: passing means the limitation was reproduced.

Full pilot + checkpoint + production adapter + local HTTP provider fixture.
No external account or credentials; not an independent review.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from concurrent.futures import ThreadPoolExecutor
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from proofrail.server import PilotControlPlane
from proofrail.rbac import AuthorizationError
from integrations.openclaw.github_adapter import GitHubMergeAdapter, GitHubTransport
from benchmarks.comparative_github import Provider


class RevocationBoundaryReviewTests(unittest.TestCase):
    def scenario(self, change):
        with TemporaryDirectory() as root:
            provider = Provider(Path(root))
            self.addCleanup(provider.close)
            provider.new()
            reached, release = Event(), Event()
            trace = []

            class PausingTransport(GitHubTransport):
                def request(self, method, path, **kwargs):
                    if method == "PUT":
                        trace.append("provider_write_ready")
                        reached.set()
                        if not release.wait(5):
                            raise RuntimeError("review synchronization timed out")
                        trace.append("provider_write_dispatched")
                    return super().request(method, path, **kwargs)

            adapter = GitHubMergeAdapter(PausingTransport(
                token="synthetic-review-only", api_base=provider.url))
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


            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(post, "/execute/github-merge", "executor",
                                      {"permit_id": permit["permit_id"]})
                try:
                    self.assertTrue(reached.wait(5), "execution did not reach PUT boundary")
                    self.assertEqual(provider.observe(1)[2], 0)
                    if change == "role":
                        app.control.grant_role(tenant, "executor", "learner")
                        with self.assertRaises(AuthorizationError):
                            app.control.authorize(tenant, "executor", "action:execute")
                    else:
                        policy({"allowed_action_types": []})
                    trace.append("governance_change_committed")
                finally:
                    release.set()
                status, response, _ = pending.result(timeout=5)
            self.assertEqual(status, 200, response)
            self.assertEqual(response["adapter_result"]["status"], "success")
            self.assertEqual(provider.observe(1)[2], 1)
            self.assertEqual(trace, ["provider_write_ready", "governance_change_committed",
                                     "provider_write_dispatched"])
            print(json.dumps({"case": change, "trace": trace, "http_status": status,
                              "provider_effects": provider.observe(1)[2],
                              "classification": "revocation_counterexample_reproduced"}))

    def test_role_revoked_before_dispatch_still_allows_effect(self):
        self.scenario("role")

    def test_policy_revoked_before_dispatch_still_allows_effect(self):
        self.scenario("policy")
