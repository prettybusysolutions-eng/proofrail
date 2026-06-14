from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.permit import mint_permit, verify_permit
from proofrail.trust import create_trust_checkpoint, replay_registry_root

from .common import captured_error, result

NOW = datetime(2026, 6, 11, 23, 0, tzinfo=timezone.utc)
ROOTS = tuple(str(index) * 64 for index in range(1, 6))


def run() -> list[dict]:
    key = Ed25519PrivateKey.generate()
    checkpoint_key = Ed25519PrivateKey.generate()
    with TemporaryDirectory() as directory:
        checkpoint = create_trust_checkpoint(
            replay_root=replay_registry_root(Path(directory) / "registry.sqlite3"),
            epoch=1,
            monotonic_counter=0,
            private_key=checkpoint_key,
            key_id="checkpoint-key",
        )
    permit = mint_permit(
        identity_root=ROOTS[0],
        evidence_root=ROOTS[1],
        policy_root=ROOTS[2],
        state_root=ROOTS[3],
        approval_digest=ROOTS[4],
        repository="owner/repo",
        pull_number=42,
        expected_head_sha="abcdef1234567890",
        merge_method="squash",
        nonce="validation-forgery-nonce-01",
        expires_at=NOW + timedelta(minutes=5),
        issuer_principal_id="verifier",
        issuer_role="verifier",
        private_key=key,
        key_id="verifier-key",
        now=NOW,
        trust={
            "replay_root": checkpoint["roots"]["replay"],
            "checkpoint_root": checkpoint["record_hash"],
            "observation_root": checkpoint["roots"]["observation"],
            "minimum_checkpoint_epoch": checkpoint["epoch"],
            "monotonic_counter": checkpoint["monotonic_counter"],
        },
    )

    def verify(candidate, *, now=NOW, public_key=key.public_key()):
        return verify_permit(
            candidate,
            public_key=public_key,
            expected_identity_root=ROOTS[0],
            expected_evidence_root=ROOTS[1],
            expected_policy_root=ROOTS[2],
            expected_state_root=ROOTS[3],
            expected_approval_digest=ROOTS[4],
            repository="owner/repo",
            pull_number=42,
            expected_head_sha="abcdef1234567890",
            merge_method="squash",
            now=now,
        )

    mutated = copy.deepcopy(permit)
    mutated["effect"]["expected_head_sha"] = "fedcba0987654321"
    mutation_error = captured_error(lambda: verify(mutated))
    wrong_key_error = captured_error(
        lambda: verify(permit, public_key=Ed25519PrivateKey.generate().public_key())
    )
    clock_skew_error = captured_error(
        lambda: verify_permit(
            permit,
            public_key=key.public_key(),
            expected_identity_root=ROOTS[0],
            expected_evidence_root=ROOTS[1],
            expected_policy_root=ROOTS[2],
            expected_state_root=ROOTS[3],
            expected_approval_digest=ROOTS[4],
            repository="owner/repo",
            pull_number=42,
            expected_head_sha="abcdef1234567890",
            merge_method="squash",
            now=NOW - timedelta(hours=1),
            current_checkpoint_epoch=checkpoint["epoch"] + 1,
            current_monotonic_counter=checkpoint["monotonic_counter"] + 1,
            expected_replay_root=checkpoint["roots"]["replay"],
            expected_checkpoint_root=checkpoint["record_hash"],
            expected_observation_root=checkpoint["roots"]["observation"],
        )
    )
    return [
        result(
            attack_id="FORGE-001",
            suite="permit_forgery_suite",
            threat="Signed permit content mutation",
            trust_assumption="Ed25519 verifier key remains uncompromised.",
            attack="Change the exact PR head after signing.",
            expected="Signature or record-hash verification denies the permit.",
            actual=f"Verification error: {mutation_error}.",
            passed=mutation_error is not None and "invalid_signature" in mutation_error,
            evidence=["proofrail/crypto.py:verify_signature", "adversarial/permit_forgery_suite.py"],
            residual_risk="Compromise of the verifier private key permits valid-looking forged authority.",
        ),
        result(
            attack_id="FORGE-002",
            suite="permit_forgery_suite",
            threat="Permit signed by an untrusted key",
            trust_assumption="The executor resolves the correct verifier public key.",
            attack="Verify a valid permit against a different verifier identity.",
            expected="Signature verification denies the permit.",
            actual=f"Verification error: {wrong_key_error}.",
            passed=wrong_key_error is not None and "invalid_signature" in wrong_key_error,
            evidence=["proofrail/crypto.py:verify_signature", "adversarial/permit_forgery_suite.py"],
            residual_risk="Key-distribution compromise can substitute an attacker's trusted public key.",
        ),
        result(
            attack_id="FORGE-003",
            suite="permit_forgery_suite",
            threat="Expiry bypass through clock rollback",
            trust_assumption="Executor time is trustworthy and monotonic enough for expiry enforcement.",
            attack="Verify after real expiry while supplying a clock one hour behind.",
            expected="Expired authority remains denied despite local clock rollback.",
            actual=f"Verification error: {clock_skew_error}.",
            passed=clock_skew_error is not None
            and "monotonic_counter_changed" in clock_skew_error,
            evidence=["proofrail/permit.py:verify_permit", "adversarial/permit_forgery_suite.py"],
            residual_risk="If checkpoint epoch and counter do not advance, wall-clock expiry still depends on trusted time.",
        ),
    ]
