"""Adversarial acceptance-ledger checks; no provider writes or real payments."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.acceptance_ledger import SQLiteAcceptanceLedger
from proofrail.crypto import sign_record
from proofrail.reliance import assess_reliance


NOW = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)
EFFECT = {
    "action_type": "github_merge",
    "target": "buyer-org/protected-repo#123",
    "request_digest": "a" * 64,
}


class AcceptanceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="proofrail-ledger-")
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "acceptances.sqlite3"
        self.ledger = SQLiteAcceptanceLedger(self.path)
        self.issuer = Ed25519PrivateKey.generate()
        self.observer = Ed25519PrivateKey.generate()
        self.auth = sign_record({
            "kind": "proofrail.reliance.authorization.v0",
            "decision": "allow",
            "issued_at": "2030-01-01T10:00:00Z",
            "expires_at": "2030-01-01T13:00:00Z",
            "signer": {"principal_id": "buyer-authority"},
            "effect": EFFECT,
        }, self.issuer, key_id="authz-key")
        self.observation = sign_record({
            "kind": "proofrail.reliance.observation.v0",
            "authorization_hash": self.auth["record_hash"],
            "observed_at": "2030-01-01T11:00:00Z",
            "signer": {"principal_id": "provider-observer"},
            "provider": "github",
            "provider_event_id": "event-1",
            "effect": EFFECT,
            "outcome": "applied",
        }, self.observer, key_id="observer-key")

    def evaluate(self, *, observation=None, authorization=None, ledger=None):
        db = ledger or self.ledger
        return assess_reliance(
            authorization=authorization or self.auth,
            observation=self.observation if observation is None else observation,
            authority_key=self.issuer.public_key(),
            observer_key=self.observer.public_key(),
            authority_principal="buyer-authority",
            authority_key_id="authz-key",
            observer_principal="provider-observer",
            observer_key_id="observer-key",
            expected_effect=EFFECT,
            expected_provider="github",
            now=NOW,
            already_accepted=db.replay_guard(
                relying_party="buyer-1", provider="github",
            ),
        )

    def test_verified_claim_is_atomically_reserved_once(self):
        first = self.evaluate()
        second = self.evaluate()
        self.assertEqual(first["verdict"], "ACCEPT_RECORDED_OUTCOME")
        self.assertEqual(second["reasons"], ["evidence_already_relied_on"])

    def test_new_instance_and_process_restart_cannot_reaccept(self):
        self.assertTrue(self.evaluate()["accepted"])
        restarted = SQLiteAcceptanceLedger(self.path)
        self.assertEqual(
            self.evaluate(ledger=restarted)["reasons"],
            ["evidence_already_relied_on"],
        )

    def test_changed_event_id_cannot_consume_one_authorization_twice(self):
        self.assertTrue(self.ledger.reserve("buyer-1", "github", "a" * 64, "event-1"))
        self.assertFalse(self.ledger.reserve("buyer-1", "github", "a" * 64, "event-2"))

    def test_same_provider_event_cannot_be_claimed_with_new_authorization(self):
        self.assertTrue(self.ledger.reserve("buyer-1", "github", "a" * 64, "event-1"))
        self.assertFalse(self.ledger.reserve("buyer-1", "github", "b" * 64, "event-1"))

    def test_two_separate_buyers_can_independently_evaluate(self):
        self.assertTrue(self.ledger.reserve("buyer-1", "github", "a" * 64, "event-1"))
        self.assertTrue(self.ledger.reserve("buyer-2", "github", "a" * 64, "event-1"))

    def test_provider_scope_does_not_override_single_use_of_authorization(self):
        self.assertTrue(self.ledger.reserve("buyer-1", "github", "a" * 64, "event-1"))
        self.assertFalse(self.ledger.reserve("buyer-1", "stripe", "a" * 64, "event-99"))

    def test_competing_connections_have_exactly_one_winner(self):
        hashes = ["e" * 64] * 36
        def attempt(i):
            ledger = SQLiteAcceptanceLedger(self.path)
            return ledger.reserve("buyer-1", "github", hashes[i], f"event-{i}")
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(36)))
        self.assertEqual(sum(results), 1)
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM acceptance_reservations").fetchone()[0], 1)

    def test_competing_auths_for_one_event_have_exactly_one_winner(self):
        def attempt(i):
            ledger = SQLiteAcceptanceLedger(self.path)
            return ledger.reserve("buyer-1", "github", f"{i:064x}", "shared-event")
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(30)))
        self.assertEqual(sum(results), 1)

    def test_after_commit_before_response_is_conservatively_consumed(self):
        # Simulate a lost response by discarding the success return.
        self.ledger.reserve("buyer-1", "github", "a" * 64, "event-1")
        recovered = SQLiteAcceptanceLedger(self.path)
        self.assertFalse(recovered.reserve("buyer-1", "github", "a" * 64, "event-1"))

    def test_unverified_observation_does_not_reserve_anything(self):
        bad = dict(self.observation)
        bad["outcome"] = "failed"
        result = self.evaluate(observation=bad)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reasons"], ["invalid_observation_signature"])
        self.assertTrue(self.evaluate()["accepted"])

    def test_invalid_scope_hash_and_event_fail_closed(self):
        for arguments in (
            (" ", "github", "a" * 64, "event-1"),
            ("buyer-1", "github", "BAD", "event-1"),
            ("buyer-1", "github", "a" * 64, ""),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    self.ledger.reserve(*arguments)

    def test_broken_database_does_not_enable_acceptance(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TABLE acceptance_reservations")
        result = self.evaluate()
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reasons"], ["replay_check_unavailable"])

    def test_ledger_is_not_read_before_signature_validation(self):
        observed_calls = []
        bad = dict(self.auth)
        bad["decision"] = "deny"
        result = assess_reliance(
            authorization=bad, observation=self.observation,
            authority_key=self.issuer.public_key(), observer_key=self.observer.public_key(),
            authority_principal="buyer-authority", authority_key_id="authz-key",
            observer_principal="provider-observer", observer_key_id="observer-key",
            expected_effect=EFFECT, expected_provider="github", now=NOW,
            already_accepted=lambda *_: observed_calls.append(True),
        )
        self.assertFalse(result["accepted"])
        self.assertEqual(observed_calls, [])

    def test_data_is_not_lost_after_reopening_connection(self):
        self.assertTrue(self.ledger.reserve("buyer-1", "github", "a" * 64, "e-1"))
        with sqlite3.connect(self.path) as db:
            record = db.execute(
                "SELECT relying_party, provider, authorization_hash, provider_event_id "
                "FROM acceptance_reservations"
            ).fetchone()
        self.assertEqual(record, ("buyer-1", "github", "a" * 64, "e-1"))


if __name__ == "__main__":
    unittest.main()
