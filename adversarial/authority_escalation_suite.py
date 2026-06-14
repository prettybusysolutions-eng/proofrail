from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.control_plane import ControlPlane
from proofrail.permit import mint_permit

from .common import captured_error, result


def run() -> list[dict]:
    with TemporaryDirectory() as directory:
        control = ControlPlane(Path(directory) / "control.sqlite3")
        tenant = control.create_tenant("Adversarial")
        for principal, role in (
            ("learner", "learner"),
            ("executor", "executor"),
            ("governor-a", "governor"),
            ("governor-b", "governor"),
        ):
            control.grant_role(tenant, principal, role)
        first = control.publish_policy(
            tenant_id=tenant,
            principal_id="governor-a",
            policy_name="merge",
            document={"version_intent": "strict"},
        )
        second = control.publish_policy(
            tenant_id=tenant,
            principal_id="governor-a",
            policy_name="merge",
            document={"version_intent": "stricter"},
        )
        control.activate_policy(
            tenant_id=tenant,
            principal_id="governor-a",
            policy_name="merge",
            version=second.version,
        )
        learner_error = captured_error(
            lambda: control.activate_policy(
                tenant_id=tenant,
                principal_id="learner",
                policy_name="merge",
                version=first.version,
            )
        )
        mint_error = captured_error(
            lambda: mint_permit(
                identity_root="1" * 64,
                evidence_root="2" * 64,
                policy_root="3" * 64,
                state_root="4" * 64,
                approval_digest="5" * 64,
                repository="owner/repo",
                pull_number=42,
                expected_head_sha="abcdef1234567890",
                merge_method="squash",
                nonce="executor-escalation-nonce",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                issuer_principal_id="executor",
                issuer_role="executor",
                private_key=Ed25519PrivateKey.generate(),
                key_id="executor-key",
            )
        )
        stale_error = captured_error(
            lambda: control.activate_policy(
                tenant_id=tenant,
                principal_id="governor-b",
                policy_name="merge",
                version=first.version,
            )
        )
        active = control.get_active_policy(
            tenant_id=tenant,
            principal_id="governor-a",
            policy_name="merge",
        )
        normalized_learner_error = (
            learner_error.replace(tenant, "<tenant>") if learner_error else None
        )
    return [
        result(
            attack_id="ESCALATE-001",
            suite="authority_escalation_suite",
            threat="Learner self-promotion",
            trust_assumption="Role assignments are correct and the learner lacks governor authority.",
            attack="Learner activates a policy candidate.",
            expected="Activation is denied.",
            actual=f"Activation error: {normalized_learner_error}.",
            passed=learner_error is not None and "policy:activate" in learner_error,
            evidence=["proofrail/rbac.py", "proofrail/control_plane.py:activate_policy"],
            residual_risk="A learner granted governor credentials is outside this separation boundary.",
        ),
        result(
            attack_id="ESCALATE-002",
            suite="authority_escalation_suite",
            threat="Executor mints its own authority",
            trust_assumption="Permit issuer roles are enforced independently of caller confidence.",
            attack="Executor signs a permit using its own key and role.",
            expected="Minting is denied.",
            actual=f"Mint error: {mint_error}.",
            passed=mint_error is not None and "issuer_role_forbidden" in mint_error,
            evidence=["proofrail/permit.py:mint_permit", "adversarial/authority_escalation_suite.py"],
            residual_risk="Verifier-key compromise bypasses role intent because the key is the authority.",
        ),
        result(
            attack_id="ESCALATE-003",
            suite="authority_escalation_suite",
            threat="Stale policy promotion by split-brain governors",
            trust_assumption="All authorized governors coordinate policy monotonicity externally.",
            attack="A second governor reactivates an older policy version.",
            expected="Stale policy activation is denied without an explicit rollback permit.",
            actual=f"Activation error: {stale_error}; active version: {active.version}.",
            passed=stale_error is not None
            and "rollback quorum" in stale_error
            and active.version == second.version,
            evidence=["proofrail/control_plane.py:activate_policy", "adversarial/authority_escalation_suite.py"],
            residual_risk="Compromise of enough governor keys to meet quorum can still authorize rollback.",
        ),
    ]
