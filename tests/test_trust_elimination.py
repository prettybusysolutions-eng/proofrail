import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.control_plane import ControlPlane
from proofrail.core import ProofRailError
from proofrail.crypto import sign_record
from proofrail.permit import PermitError, execute_github_merge, mint_permit, verify_permit
from proofrail.quorum import (
    QuorumObservationAdapter,
    observation_subject,
    sign_attestation,
    verify_quorum,
)
from proofrail.trust import (
    EMPTY_ROOT,
    create_trust_checkpoint,
    next_trust_checkpoint,
    replay_registry_root,
)

NOW = datetime(2026, 6, 11, 23, 30, tzinfo=timezone.utc)
ROOTS = tuple(str(index) * 64 for index in range(1, 6))


class Adapter:
    def __init__(self):
        self.calls = 0

    def execute(self, action, *, idempotency_key):
        self.calls += 1
        return {
            "status": "success",
            "side_effect_confirmed": True,
            "remote_operation_id": "merge123",
        }


class SignedObserver:
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


class TrustEliminationTests(unittest.TestCase):
    def setUp(self):
        self.verifier_key = Ed25519PrivateKey.generate()
        self.checkpoint_key = Ed25519PrivateKey.generate()

    def permit(self, checkpoint):
        return mint_permit(
            identity_root=ROOTS[0],
            evidence_root=ROOTS[1],
            policy_root=ROOTS[2],
            state_root=ROOTS[3],
            approval_digest=ROOTS[4],
            repository="owner/repo",
            pull_number=42,
            expected_head_sha="abcdef1234567890",
            merge_method="squash",
            nonce="trust-elimination-nonce-001",
            expires_at=NOW + timedelta(minutes=5),
            issuer_principal_id="verifier",
            issuer_role="verifier",
            private_key=self.verifier_key,
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

    def test_replay_registry_rollback_mismatches_signed_checkpoint(self):
        with TemporaryDirectory() as directory:
            registry = Path(directory) / "registry.sqlite3"
            checkpoint = create_trust_checkpoint(
                replay_root=replay_registry_root(registry),
                epoch=1,
                monotonic_counter=0,
                private_key=self.checkpoint_key,
                key_id="checkpoint-key",
            )
            permit = self.permit(checkpoint)
            adapter = Adapter()
            execute_github_merge(
                permit,
                adapter=adapter,
                registry_path=registry,
                public_key=self.verifier_key.public_key(),
                expected_identity_root=ROOTS[0],
                expected_evidence_root=ROOTS[1],
                expected_policy_root=ROOTS[2],
                expected_state_root=ROOTS[3],
                expected_approval_digest=ROOTS[4],
                executor_id="executor",
                now=NOW,
                trust_checkpoint=checkpoint,
                checkpoint_public_key=self.checkpoint_key.public_key(),
            )
            advanced = next_trust_checkpoint(
                checkpoint,
                registry_path=registry,
                private_key=self.checkpoint_key,
                key_id="checkpoint-key",
            )
            registry.unlink()
            with self.assertRaisesRegex(PermitError, "replay_root_changed"):
                execute_github_merge(
                    permit,
                    adapter=adapter,
                    registry_path=registry,
                    public_key=self.verifier_key.public_key(),
                    expected_identity_root=ROOTS[0],
                    expected_evidence_root=ROOTS[1],
                    expected_policy_root=ROOTS[2],
                    expected_state_root=ROOTS[3],
                    expected_approval_digest=ROOTS[4],
                    executor_id="executor",
                    now=NOW - timedelta(hours=1),
                    trust_checkpoint=advanced,
                    checkpoint_public_key=self.checkpoint_key.public_key(),
                )
            self.assertEqual(adapter.calls, 1)

    def test_checkpoint_progress_blocks_clock_rollback(self):
        with TemporaryDirectory() as directory:
            registry = Path(directory) / "registry.sqlite3"
            checkpoint = create_trust_checkpoint(
                replay_root=replay_registry_root(registry),
                epoch=4,
                monotonic_counter=7,
                private_key=self.checkpoint_key,
                key_id="checkpoint-key",
            )
            permit = self.permit(checkpoint)
            advanced = next_trust_checkpoint(
                checkpoint,
                registry_path=registry,
                private_key=self.checkpoint_key,
                key_id="checkpoint-key",
            )
            with self.assertRaisesRegex(PermitError, "monotonic_counter_changed"):
                verify_permit(
                    permit,
                    public_key=self.verifier_key.public_key(),
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
                    current_checkpoint_epoch=advanced["epoch"],
                    current_monotonic_counter=advanced["monotonic_counter"],
                    expected_replay_root=advanced["roots"]["replay"],
                    expected_checkpoint_root=advanced["record_hash"],
                    expected_observation_root=advanced["roots"]["observation"],
                )

    def test_one_compromised_observer_cannot_satisfy_two_of_three(self):
        action = {
            "action_type": "github_merge",
            "execution": {
                "owner": "owner",
                "repo": "repo",
                "pull_number": 42,
                "expected_head_sha": "abcdef1234567890",
                "merge_method": "squash",
            },
        }
        keys = {name: Ed25519PrivateKey.generate() for name in ("provider", "audit", "checkpoint")}
        sources = {
            "provider": SignedObserver(
                "provider",
                keys["provider"],
                {"merged": True, "merge_commit_sha": "forged"},
            ),
            "audit": SignedObserver(
                "audit",
                keys["audit"],
                {"merged": False, "merge_commit_sha": None},
            ),
            "checkpoint": SignedObserver(
                "checkpoint",
                keys["checkpoint"],
                {"merged": False, "merge_commit_sha": None},
            ),
        }
        quorum = QuorumObservationAdapter(
            executor_adapter=Adapter(),
            observation_sources=sources,
            trusted_observers={
                name: ("observer", key.public_key()) for name, key in keys.items()
            },
            threshold=2,
        ).observe(action)
        self.assertTrue(quorum["quorum_met"])
        self.assertFalse(quorum["merged"])
        self.assertEqual(quorum["accepted"], 2)

    def test_policy_rollback_requires_governor_quorum(self):
        with TemporaryDirectory() as directory:
            control = ControlPlane(Path(directory) / "control.sqlite3")
            tenant = control.create_tenant("Quorum")
            keys = {name: Ed25519PrivateKey.generate() for name in ("g1", "g2", "g3")}
            for governor in keys:
                control.grant_role(tenant, governor, "governor")
            first = control.publish_policy(
                tenant_id=tenant,
                principal_id="g1",
                policy_name="merge",
                document={"level": 1},
            )
            second = control.publish_policy(
                tenant_id=tenant,
                principal_id="g1",
                policy_name="merge",
                document={"level": 2},
            )
            control.activate_policy(
                tenant_id=tenant,
                principal_id="g1",
                policy_name="merge",
                version=second.version,
            )
            with self.assertRaisesRegex(ProofRailError, "rollback quorum"):
                control.activate_policy(
                    tenant_id=tenant,
                    principal_id="g2",
                    policy_name="merge",
                    version=first.version,
                )
            statement = {
                "tenant_id": tenant,
                "policy_name": "merge",
                "version": first.version,
                "policy_digest": first.digest,
                "action": "rollback",
            }
            approval = lambda governor: sign_attestation(
                kind="proofrail.policy-promotion-approval.v0.5.1",
                subject_digest=first.digest,
                statement=statement,
                signer_id=governor,
                signer_role="governor",
                private_key=keys[governor],
                key_id=f"{governor}-key",
            )
            trusted = {
                governor: ("governor", key.public_key())
                for governor, key in keys.items()
            }
            with self.assertRaisesRegex(ProofRailError, "quorum not met"):
                control.activate_policy_with_quorum(
                    tenant_id=tenant,
                    policy_name="merge",
                    version=first.version,
                    approvals=[approval("g1")],
                    trusted_governors=trusted,
                    threshold=2,
                )
            active = control.activate_policy_with_quorum(
                tenant_id=tenant,
                policy_name="merge",
                version=first.version,
                approvals=[approval("g1"), approval("g2")],
                trusted_governors=trusted,
                threshold=2,
            )
            self.assertEqual(active.version, first.version)

    def test_quorum_recomputes_statement_hash(self):
        keys = {name: Ed25519PrivateKey.generate() for name in ("a", "b")}
        subject = "a" * 64
        honest = sign_attestation(
            kind="proofrail.github-observation.v0.5.1",
            subject_digest=subject,
            statement={"merged": True},
            signer_id="a",
            signer_role="observer",
            private_key=keys["a"],
            key_id="a-key",
        )
        forged = sign_record(
            {
                "kind": "proofrail.github-observation.v0.5.1",
                "subject_digest": subject,
                "statement": {"merged": False},
                "statement_hash": honest["statement_hash"],
                "signer": {"principal_id": "b", "role": "observer"},
            },
            keys["b"],
            key_id="b-key",
        )
        quorum = verify_quorum(
            [honest, forged],
            trusted_signers={
                name: ("observer", key.public_key()) for name, key in keys.items()
            },
            threshold=2,
            expected_kind="proofrail.github-observation.v0.5.1",
            expected_subject_digest=subject,
        )
        self.assertFalse(quorum["met"])

    def test_conflicting_qualifying_quorums_fail_closed(self):
        keys = {name: Ed25519PrivateKey.generate() for name in ("a", "b", "c", "d")}
        subject = "b" * 64

        def attestation(signer, merged):
            return sign_attestation(
                kind="proofrail.github-observation.v0.5.1",
                subject_digest=subject,
                statement={"merged": merged},
                signer_id=signer,
                signer_role="observer",
                private_key=keys[signer],
                key_id=f"{signer}-key",
            )

        quorum = verify_quorum(
            [
                attestation("a", True),
                attestation("b", True),
                attestation("c", False),
                attestation("d", False),
            ],
            trusted_signers={
                name: ("observer", key.public_key()) for name, key in keys.items()
            },
            threshold=2,
            expected_kind="proofrail.github-observation.v0.5.1",
            expected_subject_digest=subject,
        )
        self.assertFalse(quorum["met"])
        self.assertTrue(quorum["conflict"])

    def test_equivocal_signer_is_excluded(self):
        keys = {name: Ed25519PrivateKey.generate() for name in ("a", "b")}
        subject = "c" * 64

        def attestation(signer, merged):
            return sign_attestation(
                kind="proofrail.github-observation.v0.5.1",
                subject_digest=subject,
                statement={"merged": merged},
                signer_id=signer,
                signer_role="observer",
                private_key=keys[signer],
                key_id=f"{signer}-key",
            )

        quorum = verify_quorum(
            [
                attestation("a", True),
                attestation("a", False),
                attestation("b", True),
            ],
            trusted_signers={
                name: ("observer", key.public_key()) for name, key in keys.items()
            },
            threshold=2,
            expected_kind="proofrail.github-observation.v0.5.1",
            expected_subject_digest=subject,
        )
        self.assertFalse(quorum["met"])
        self.assertEqual(quorum["equivocal_signers"], ["a"])


if __name__ == "__main__":
    unittest.main()
