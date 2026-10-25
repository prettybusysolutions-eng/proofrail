"""Bounded F-1 regressions for envelope identity and time validation."""
import unittest
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.crypto import sign_record
from proofrail.envelope import _RFC3339_TIMESTAMP, mint_action_authority_envelope, verify_action_authority_envelope
from proofrail.permit import PermitError


NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
ROOTS = {"identity": "1" * 64, "evidence": "2" * 64, "policy": "3" * 64, "state": "4" * 64}
ISSUER = {"principal_id": "verifier:primary", "role": "verifier"}
SUBJECT = {"principal_id": "worker:primary", "role": "executor"}
PARAMS = {"revision": 4}


class EnvelopeIdentityTimeTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.envelope = self.mint(now=NOW)

    def mint(self, *, now):
        return mint_action_authority_envelope(
            roots=ROOTS,
            approval_digest="5" * 64,
            action_type="record_revision",
            target="case:123",
            parameters=PARAMS,
            subject_principal_id=SUBJECT["principal_id"],
            subject_role=SUBJECT["role"],
            issuer_principal_id=ISSUER["principal_id"],
            issuer_role=ISSUER["role"],
            adapter_contract={"name": "demo-adapter", "version": "v1", "idempotency_required": True},
            observation_contract={
                "name": "demo-observation",
                "version": "v1",
                "minimum_confirmations": 1,
                "success_predicate_digest": "6" * 64,
            },
            nonce="unique-nonce-for-test-case-00000001",
            expires_at=NOW + timedelta(minutes=5),
            private_key=self.key,
            key_id="verifier-primary-key",
            now=now,
        )

    def verify(self, record=None, **changes):
        kwargs = dict(
            public_key=self.key.public_key(),
            expected_roots=ROOTS,
            expected_approval_digest="5" * 64,
            action_type="record_revision",
            target="case:123",
            parameters=PARAMS,
            now=NOW,
            expected_issuer=ISSUER,
            expected_subject=SUBJECT,
            expected_key_id="verifier-primary-key",
        )
        kwargs.update(changes)
        return verify_action_authority_envelope(record or self.envelope, **kwargs)

    def resign_with_time(self, field, timestamp):
        unsigned = {k: v for k, v in self.envelope.items() if k not in {"record_hash", "signature"}}
        unsigned[field] = timestamp
        return sign_record(unsigned, self.key, key_id="verifier-primary-key")

    def test_exact_trusted_identities_and_current_envelope_succeed(self):
        self.assertTrue(self.verify())

    def test_signed_authority_does_not_claim_a_different_trusted_issuer(self):
        with self.assertRaisesRegex(PermitError, "issuer_changed"):
            self.verify(expected_issuer={"principal_id": "verifier:other", "role": "verifier"})

    def test_signed_authority_does_not_bind_another_executor(self):
        with self.assertRaisesRegex(PermitError, "subject_changed"):
            self.verify(expected_subject={"principal_id": "worker:other", "role": "executor"})

    def test_signed_authority_does_not_claim_another_trusted_key_id(self):
        with self.assertRaisesRegex(PermitError, "issuer_key_changed"):
            self.verify(expected_key_id="another-approved-key")

    def test_future_dated_authority_is_not_yet_valid(self):
        future = self.mint(now=NOW + timedelta(minutes=1))
        with self.assertRaisesRegex(PermitError, "authority_not_yet_valid"):
            self.verify(future)

    def test_timezone_less_signed_date_is_rejected(self):
        modified = self.resign_with_time("issued_at", "2026-10-23T12:00:00")
        with self.assertRaisesRegex(PermitError, "timezone_required"):
            self.verify(modified)

    def test_malformed_signed_date_is_rejected(self):
        modified = self.resign_with_time("expires_at", "not-a-timestamp")
        with self.assertRaisesRegex(PermitError, "invalid_timestamp"):
            self.verify(modified)

    def test_non_rfc3339_separator_is_rejected(self):
        modified = self.resign_with_time("issued_at", "2026-10-23 12:00:00+00:00")
        with self.assertRaisesRegex(PermitError, "invalid_timestamp"):
            self.verify(modified)

    def test_rfc3339_parser_pattern_rejects_non_ascii_digits(self):
        self.assertIsNone(_RFC3339_TIMESTAMP.fullmatch("٢٠٢٦-10-23T12:00:00Z"))
        self.assertIsNotNone(_RFC3339_TIMESTAMP.fullmatch("2026-10-23T12:00:00Z"))

    def test_timezone_less_mint_expiry_is_rejected(self):
        with self.assertRaisesRegex(PermitError, "timezone_required"):
            mint_action_authority_envelope(
                roots=ROOTS, approval_digest="5" * 64,
                action_type="record_revision", target="case:123", parameters=PARAMS,
                subject_principal_id=SUBJECT["principal_id"], subject_role=SUBJECT["role"],
                issuer_principal_id=ISSUER["principal_id"], issuer_role=ISSUER["role"],
                adapter_contract={"name": "demo-adapter", "version": "v1", "idempotency_required": True},
                observation_contract={
                    "name": "demo-observation", "version": "v1", "minimum_confirmations": 1,
                    "success_predicate_digest": "6" * 64,
                },
                nonce="unique-nonce-for-test-case-00000001",
                expires_at="2026-10-23T12:05:00",
                private_key=self.key, key_id="verifier-primary-key", now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
