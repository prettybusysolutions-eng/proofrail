import copy
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.envelope import (
    mint_action_authority_envelope,
    verify_action_authority_envelope,
)
from proofrail.permit import PermitError


NOW = datetime(2026, 6, 14, 16, 0, tzinfo=timezone.utc)
ROOTS = {
    "identity": "1" * 64,
    "evidence": "2" * 64,
    "policy": "3" * 64,
    "state": "4" * 64,
}
APPROVAL = "5" * 64


class ActionAuthorityEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()

    def envelope(self, action_type, target, parameters):
        return mint_action_authority_envelope(
            roots=ROOTS,
            approval_digest=APPROVAL,
            action_type=action_type,
            target=target,
            parameters=parameters,
            subject_principal_id="agent:executor",
            subject_role="executor",
            issuer_principal_id="verifier:primary",
            issuer_role="verifier",
            adapter_contract={
                "name": "proofrail.adapter-receipt",
                "version": "v1",
                "idempotency_required": True,
            },
            observation_contract={
                "name": "proofrail.provider-observation",
                "version": "v1",
                "minimum_confirmations": 1,
                "success_predicate_digest": "6" * 64,
            },
            nonce="authority-envelope-nonce-0001",
            expires_at=NOW + timedelta(minutes=5),
            private_key=self.private_key,
            key_id="verifier-key",
            now=NOW,
        )

    def verify(self, envelope, action_type, target, parameters, **overrides):
        values = {
            "public_key": self.public_key,
            "expected_roots": ROOTS,
            "expected_approval_digest": APPROVAL,
            "action_type": action_type,
            "target": target,
            "parameters": parameters,
            "now": NOW,
        }
        values.update(overrides)
        return verify_action_authority_envelope(envelope, **values)

    def test_same_envelope_primitive_covers_two_execution_domains(self):
        cases = [
            (
                "github_merge",
                "github:owner/repo#42",
                {"expected_head_sha": "abcdef1234567890", "merge_method": "squash"},
            ),
            (
                "database_migration",
                "sqlite:customer-primary",
                {"migration_digest": "7" * 64, "target_version": 2},
            ),
        ]
        for action_type, target, parameters in cases:
            with self.subTest(action_type=action_type):
                envelope = self.envelope(action_type, target, parameters)
                self.assertTrue(self.verify(envelope, action_type, target, parameters))
                self.assertTrue(envelope["failure_semantics"]["consume_before_effect"])

    def test_parameter_expansion_is_denied(self):
        parameters = {"expected_head_sha": "abcdef1234567890", "merge_method": "squash"}
        envelope = self.envelope("github_merge", "github:owner/repo#42", parameters)
        expanded = {**parameters, "delete_branch": True}
        with self.assertRaisesRegex(PermitError, "parameters_changed"):
            self.verify(envelope, "github_merge", "github:owner/repo#42", expanded)

    def test_signed_effect_mutation_is_denied(self):
        parameters = {"migration_digest": "7" * 64, "target_version": 2}
        envelope = self.envelope(
            "database_migration",
            "sqlite:customer-primary",
            parameters,
        )
        tampered = copy.deepcopy(envelope)
        tampered["effect"]["parameters"]["target_version"] = 3
        with self.assertRaisesRegex(PermitError, "invalid_envelope"):
            self.verify(
                tampered,
                "database_migration",
                "sqlite:customer-primary",
                parameters,
            )
    def test_expired_envelope_is_denied(self):
        parameters = {"migration_digest": "7" * 64, "target_version": 2}
        envelope = self.envelope(
            "database_migration",
            "sqlite:customer-primary",
            parameters,
        )
        with self.assertRaisesRegex(PermitError, "permit_expired"):
            self.verify(
                envelope,
                "database_migration",
                "sqlite:customer-primary",
                parameters,
                now=NOW + timedelta(minutes=5),
            )

    def test_failure_semantics_cannot_be_weakened(self):
        parameters = {"migration_digest": "7" * 64, "target_version": 2}
        envelope = self.envelope(
            "database_migration",
            "sqlite:customer-primary",
            parameters,
        )
        weakened = copy.deepcopy(envelope)
        weakened["failure_semantics"]["retry"] = "AUTOMATIC"
        with self.assertRaisesRegex(PermitError, "invalid_envelope"):
            self.verify(
                weakened,
                "database_migration",
                "sqlite:customer-primary",
                parameters,
            )
