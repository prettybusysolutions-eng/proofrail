"""Synthetic negative tests for the optional cross-vendor reliance contract."""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.crypto import sign_record
from proofrail.reliance import assess_reliance


NOW = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
EFFECT = {
    "action_type": "github_merge",
    "target": "example-org/service#123",
    "request_digest": "d" * 64,
}


class RelianceGateTests(unittest.TestCase):
    def setUp(self):
        self.issuer = Ed25519PrivateKey.generate()
        self.observer = Ed25519PrivateKey.generate()
        self.authority = sign_record(
            {
                "kind": "proofrail.reliance.authorization.v0",
                "decision": "allow",
                "issued_at": "2030-01-01T10:00:00Z",
                "expires_at": "2030-01-01T13:00:00Z",
                "signer": {"principal_id": "trusted-authz"},
                "effect": EFFECT,
            },
            self.issuer,
            key_id="issuer-1",
        )
        self.observation = self.sign_observation(
            {
                "kind": "proofrail.reliance.observation.v0",
                "authorization_hash": self.authority["record_hash"],
                "observed_at": "2030-01-01T11:00:00Z",
                "signer": {"principal_id": "trusted-provider"},
                "provider": "github",
                "provider_event_id": "github-event-789",
                "effect": EFFECT,
                "outcome": "applied",
            }
        )
        self.context = {
            "authority_key": self.issuer.public_key(),
            "observer_key": self.observer.public_key(),
            "authority_principal": "trusted-authz",
            "authority_key_id": "issuer-1",
            "observer_principal": "trusted-provider",
            "observer_key_id": "observer-1",
            "expected_effect": EFFECT,
            "expected_provider": "github",
            "now": NOW,
        }

    def sign_observation(self, body):
        return sign_record(body, self.observer, key_id="observer-1")

    def evaluate(self, a=None, o="default", **changes):
        obs = self.observation if o == "default" else o
        context = {**self.context, **changes}
        return assess_reliance(self.authority if a is None else a, obs, **context)

    def test_valid_buyer_pinned_claim_records_are_accepted_with_limits(self):
        result = self.evaluate()
        self.assertTrue(result["accepted"])
        self.assertEqual(result["verdict"], "ACCEPT_RECORDED_OUTCOME")
        self.assertEqual(result["provider_event_id"], "github-event-789")
        self.assertTrue(any("not established" in x for x in result["limits"]))

    def test_missing_observation_is_not_success(self):
        result = self.evaluate(o=None)
        self.assertEqual(result["verdict"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(result["accepted"])

    def test_tampered_authorization_rejected(self):
        modified = copy.deepcopy(self.authority)
        modified["effect"]["target"] = "another/project#9"
        self.assertEqual(self.evaluate(a=modified)["reasons"], ["invalid_authorization_signature"])

    def test_tampered_observation_rejected(self):
        modified = copy.deepcopy(self.observation)
        modified["outcome"] = "applied2"
        self.assertEqual(self.evaluate(o=modified)["reasons"], ["invalid_observation_signature"])

    def test_wrong_authorization_signer_rejected(self):
        self.assertEqual(self.evaluate(authority_principal="different")["reasons"], ["unexpected_authorization_signer"])

    def test_wrong_observer_key_rejected(self):
        self.assertEqual(
            self.evaluate(observer_key=Ed25519PrivateKey.generate().public_key())["reasons"],
            ["invalid_observation_signature"],
        )

    def test_same_key_or_principal_cannot_claim_separation(self):
        self.assertEqual(
            self.evaluate(observer_key=self.issuer.public_key())["reasons"],
            ["separate_signers_required"],
        )
        self.assertEqual(
            self.evaluate(observer_principal="trusted-authz")["reasons"],
            ["separate_signers_required"],
        )

    def test_relying_party_expected_effect_cannot_be_changed(self):
        alternate = {**EFFECT, "target": "other-org/other#4"}
        self.assertEqual(
            self.evaluate(expected_effect=alternate)["reasons"],
            ["authorization_effect_mismatch"],
        )

    def test_signed_observation_for_different_authorization_is_rejected(self):
        modified = {**self.observation}
        modified["authorization_hash"] = "e" * 64
        modified.pop("signature")
        modified.pop("record_hash")
        new = self.sign_observation(modified)
        self.assertEqual(
            self.evaluate(o=new)["reasons"],
            ["observation_authorization_hash_mismatch"],
        )

    def test_wrong_provider_or_effect_is_rejected_even_when_signed(self):
        self.assertEqual(self.evaluate(expected_provider="stripe")["reasons"], ["unexpected_provider"])
        modified = {**self.observation, "effect": {**EFFECT, "target": "other-target"}}
        modified.pop("signature")
        modified.pop("record_hash")
        self.assertEqual(self.evaluate(o=self.sign_observation(modified))["reasons"], ["observation_effect_mismatch"])

    def test_failed_and_unknown_outcomes_never_accepted(self):
        for outcome in ("failed", "unknown"):
            with self.subTest(outcome=outcome):
                modified = {**self.observation, "outcome": outcome}
                modified.pop("signature")
                modified.pop("record_hash")
                result = self.evaluate(o=self.sign_observation(modified))
                self.assertEqual(result["verdict"], "INSUFFICIENT_EVIDENCE")
                self.assertFalse(result["accepted"])

    def test_expired_issuer_authorization_never_accepted(self):
        later = datetime(2030, 1, 1, 14, tzinfo=timezone.utc)
        self.assertEqual(
            self.evaluate(now=later)["reasons"], ["authorization_not_current"]
        )

    def test_invalid_observation_timestamp_rejected_even_when_signed(self):
        modified = {**self.observation, "observed_at": "2030-01-01T11:00:00"}
        modified.pop("signature")
        modified.pop("record_hash")
        self.assertEqual(
            self.evaluate(o=self.sign_observation(modified))["reasons"], ["invalid_observation_time"]
        )

    def test_provider_recorded_future_or_predating_observation_rejected(self):
        for date in ("2030-01-01T09:00:00Z", "2030-01-02T11:00:00Z"):
            with self.subTest(date=date):
                modified = {**self.observation, "observed_at": date}
                modified.pop("signature")
                modified.pop("record_hash")
                self.assertEqual(
                    self.evaluate(o=self.sign_observation(modified))["reasons"],
                    ["observation_outside_observed_interval"],
                )

    def test_missing_trust_keys_or_provider_event_fails_closed(self):
        self.assertEqual(
            self.evaluate(authority_key=b"wrong")["reasons"], ["untrusted_key_material"]
        )
        modified = {**self.observation, "provider_event_id": ""}
        modified.pop("signature")
        modified.pop("record_hash")
        self.assertEqual(
            self.evaluate(o=self.sign_observation(modified))["reasons"],
            ["missing_provider_event_id"],
        )


if __name__ == "__main__":
    unittest.main()
