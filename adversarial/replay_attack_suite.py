from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.permit import execute_github_merge, mint_permit
from proofrail.trust import (
    create_trust_checkpoint,
    next_trust_checkpoint,
    replay_registry_root,
)

from .common import captured_error, result

NOW = datetime(2026, 6, 11, 23, 0, tzinfo=timezone.utc)
ROOTS = tuple(str(index) * 64 for index in range(1, 6))


class Adapter:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, action, *, idempotency_key):
        self.calls += 1
        return {
            "status": "success",
            "side_effect_confirmed": True,
            "remote_operation_id": f"merge-{self.calls}",
        }


def run() -> list[dict]:
    key = Ed25519PrivateKey.generate()
    checkpoint_key = Ed25519PrivateKey.generate()
    adapter = Adapter()
    with TemporaryDirectory() as directory:
        registry = Path(directory) / "registry.sqlite3"
        checkpoint = create_trust_checkpoint(
            replay_root=replay_registry_root(registry),
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
            nonce="validation-replay-nonce-0001",
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

        def execute(active_checkpoint) -> None:
            execute_github_merge(
                permit,
                adapter=adapter,
                registry_path=registry,
                public_key=key.public_key(),
                expected_identity_root=ROOTS[0],
                expected_evidence_root=ROOTS[1],
                expected_policy_root=ROOTS[2],
                expected_state_root=ROOTS[3],
                expected_approval_digest=ROOTS[4],
                executor_id="executor",
                now=NOW,
                trust_checkpoint=active_checkpoint,
                checkpoint_public_key=checkpoint_key.public_key(),
            )

        execute(checkpoint)
        advanced = next_trust_checkpoint(
            checkpoint,
            registry_path=registry,
            private_key=checkpoint_key,
            key_id="checkpoint-key",
        )
        replay_error = captured_error(lambda: execute(advanced))
        replay_passed = replay_error is not None and "permit_replayed" in replay_error
        replay = result(
            attack_id="REPLAY-001",
            suite="replay_attack_suite",
            threat="Consumed permit replay",
            trust_assumption="The replay registry persists and is consulted atomically.",
            attack="Execute the same signed permit twice against one registry.",
            expected="Second execution is denied before the adapter call.",
            actual=f"Second execution error: {replay_error}; adapter calls: {adapter.calls}.",
            passed=replay_passed and adapter.calls == 1,
            evidence=["proofrail/permit.py:consume_permit", "adversarial/replay_attack_suite.py"],
            residual_risk="Registry durability and backup integrity remain operational dependencies.",
        )

        registry.unlink()
        registry_loss_error = captured_error(lambda: execute(advanced))
        registry_loss = result(
            attack_id="REPLAY-002",
            suite="replay_attack_suite",
            threat="Replay after replay-registry loss",
            trust_assumption="The replay registry cannot be deleted, rolled back, or restored stale.",
            attack="Delete the replay registry after consumption, then replay the permit.",
            expected="Replay remains denied after recovery-state loss.",
            actual=f"Execution error: {registry_loss_error}; adapter calls: {adapter.calls}.",
            passed=registry_loss_error is not None
            and "replay_root_changed" in registry_loss_error
            and adapter.calls == 1,
            evidence=["proofrail/permit.py:consume_permit", "adversarial/replay_attack_suite.py"],
            residual_risk="Loss of both replay state and the independently held trust checkpoint can still erase replay evidence.",
        )
    return [replay, registry_loss]
