from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.server import PilotControlPlane
from proofrail.quorum import (
    QuorumObservationAdapter,
    observation_subject,
    sign_attestation,
)

from .common import result


class ObservationAdapter:
    def __init__(self, *, observed_merged: bool, observed_sha: str | None):
        self.observed_merged = observed_merged
        self.observed_sha = observed_sha

    def execute(self, action, *, idempotency_key):
        return {
            "status": "success",
            "side_effect_confirmed": True,
            "remote_operation_id": "merge123",
            "receipt_evidence": {},
        }

    def observe(self, action):
        return {
            "provider": "github",
            "http_status": 200,
            "merged": self.observed_merged,
            "merge_commit_sha": self.observed_sha,
            "pull": {},
        }


class SignedSource:
    def __init__(self, signer_id, key, statement):
        self.signer_id = signer_id
        self.key = key
        self.statement = statement

    def observe(self, action):
        return sign_attestation(
            kind="proofrail.github-observation.v0.5.1",
            subject_digest=observation_subject(action),
            statement=self.statement,
            signer_id=self.signer_id,
            signer_role="observer",
            private_key=self.key,
            key_id=f"{self.signer_id}-key",
        )


def quorum_adapter(*, malicious_merged: bool) -> QuorumObservationAdapter:
    keys = {
        name: Ed25519PrivateKey.generate()
        for name in ("provider", "audit", "checkpoint")
    }
    false_statement = {"merged": False, "merge_commit_sha": None}
    sources = {
        "provider": SignedSource(
            "provider",
            keys["provider"],
            {"merged": malicious_merged, "merge_commit_sha": "merge123"}
            if malicious_merged
            else false_statement,
        ),
        "audit": SignedSource("audit", keys["audit"], false_statement),
        "checkpoint": SignedSource("checkpoint", keys["checkpoint"], false_statement),
    }
    return QuorumObservationAdapter(
        executor_adapter=ObservationAdapter(
            observed_merged=True,
            observed_sha="merge123",
        ),
        observation_sources=sources,
        trusted_observers={
            name: ("observer", key.public_key()) for name, key in keys.items()
        },
        threshold=2,
    )


def _lifecycle(adapter, forged_body: bool) -> dict:
    with TemporaryDirectory() as directory:
        app = PilotControlPlane(
            database=Path(directory) / "pilot.sqlite3",
            ledger_dir=Path(directory) / "ledgers",
            verifier_private_key=Ed25519PrivateKey.generate(),
            checkpoint_private_key=Ed25519PrivateKey.generate(),
            github_adapter=adapter,
        )
        tenant = app.control.create_tenant("Adversarial")
        for role in ("proposer", "verifier", "executor", "reconciler", "governor"):
            app.control.grant_role(tenant, role, role)
        policy = app.control.publish_policy(
            tenant_id=tenant,
            principal_id="governor",
            policy_name="merge",
            document={"allowed_action_types": ["github_merge"]},
        )
        app.control.activate_policy(
            tenant_id=tenant,
            principal_id="governor",
            policy_name="merge",
            version=policy.version,
        )
        headers = lambda role: {
            "X-ProofRail-Tenant": tenant,
            "X-ProofRail-Principal": role,
        }
        _, intent, _ = app.request(
            "POST",
            "/intents",
            headers=headers("proposer"),
            body={
                "action_type": "github_merge",
                "target": "owner/repo#42",
                "effect": {
                    "repository": "owner/repo",
                    "pull_number": 42,
                    "expected_head_sha": "abcdef1234567890",
                    "merge_method": "squash",
                },
            },
        )
        _, evidence, _ = app.request(
            "POST",
            "/evidence",
            headers=headers("proposer"),
            body={"intent_id": intent["intent_id"], "claims": [{"checks": "pass"}]},
        )
        _, evaluation, _ = app.request(
            "POST",
            "/evaluate",
            headers=headers("verifier"),
            body={
                "intent_id": intent["intent_id"],
                "evidence_ids": [evidence["evidence_id"]],
                "policy_name": "merge",
                "state_root": "3" * 64,
                "approval_digest": "4" * 64,
            },
        )
        _, permit, _ = app.request(
            "POST",
            "/permits",
            headers=headers("verifier"),
            body={"evaluation_id": evaluation["evaluation_id"]},
        )
        _, execution, _ = app.request(
            "POST",
            "/execute/github-merge",
            headers=headers("executor"),
            body={"permit_id": permit["permit_id"]},
        )
        body = {"execution_id": execution["execution_id"]}
        if forged_body:
            body.update({"observed_merged": True, "observed_merge_sha": "merge123"})
        _, reconciliation, _ = app.request(
            "POST",
            "/reconcile/github-merge",
            headers=headers("reconciler"),
            body=body,
        )
        return reconciliation


def run() -> list[dict]:
    forged = _lifecycle(
        quorum_adapter(malicious_merged=False),
        forged_body=True,
    )
    compromised = _lifecycle(
        quorum_adapter(malicious_merged=True),
        forged_body=False,
    )
    return [
        result(
            attack_id="RECONCILE-001",
            suite="reconciliation_bypass_suite",
            threat="Reconciler request-body outcome forgery",
            trust_assumption="The control plane ignores caller-asserted provider outcomes.",
            attack="Submit a false merged state and SHA in the reconciliation request.",
            expected="Provider observation overrides the request and reconciliation fails.",
            actual=f"State: {forged['state']}; observed SHA: {forged['observed_merge_sha']}.",
            passed=forged["state"] == "RECONCILIATION_FAILED",
            evidence=["proofrail/server.py:_reconcile_github_merge", "adversarial/reconciliation_bypass_suite.py"],
            residual_risk="A compromised provider observation channel remains authoritative.",
        ),
        result(
            attack_id="RECONCILE-002",
            suite="reconciliation_bypass_suite",
            threat="Compromised provider observation adapter",
            trust_assumption="The adapter and provider response are authentic and independently secured.",
            attack="Return a fabricated but well-formed merged observation from the adapter.",
            expected="A second independent channel prevents false reconciliation.",
            actual=f"State: {compromised['state']}; observed SHA: {compromised['observed_merge_sha']}.",
            passed=compromised["state"] == "RECONCILIATION_FAILED",
            evidence=["proofrail/server.py:_reconcile_github_merge", "adversarial/reconciliation_bypass_suite.py"],
            residual_risk="Compromise of enough observer keys to meet quorum can still falsely reconcile.",
        ),
    ]
