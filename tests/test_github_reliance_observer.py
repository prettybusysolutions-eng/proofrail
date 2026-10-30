"""Recorded-response tests for read-only GitHub->Reliance->atomic ledger flow."""
from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.acceptance_ledger import SQLiteAcceptanceLedger
from proofrail.crypto import sign_record
from proofrail.github_observer import observe_github_merge
from proofrail.reliance import assess_reliance


AT = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
A_SHA = "a" * 40
B_SHA = "b" * 40
M_SHA = "c" * 40
EFFECT = {
    "action_type": "github_merge",
    "repository": "example-co/critical",
    "pull_number": 42,
    "expected_head_sha": A_SHA,
    "expected_base_ref": "main",
}


def pull(*, head=A_SHA, merged=True, at="2030-01-01T11:30:00Z",
         repo="example-co/critical", number=42, state=None):
    return {
        "number": number,
        "base": {"repo": {"full_name": repo}, "ref": "main"},
        "head": {"sha": head},
        "merged": merged,
        "state": state or ("closed" if merged else "open"),
        "merged_at": at if merged else None,
        "merge_commit_sha": M_SHA if merged else None,
    }


class FakeReadOnly:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_pull(self, repo, number):
        self.calls.append((repo, number))
        if isinstance(self.payload, Exception):
            raise self.payload
        return copy.deepcopy(self.payload)


class GithubRelianceObserverTests(unittest.TestCase):
    def setUp(self):
        self.auth_key = Ed25519PrivateKey.generate()
        self.obs_key = Ed25519PrivateKey.generate()
        self.auth = sign_record({
            "kind": "proofrail.reliance.authorization.v0",
            "decision": "allow",
            "issued_at": "2030-01-01T10:00:00Z",
            "expires_at": "2030-01-01T13:00:00Z",
            "signer": {"principal_id": "buyer-authority"},
            "effect": EFFECT,
        }, self.auth_key, key_id="auth-key-1")
        self.tempdir = tempfile.TemporaryDirectory(prefix="github-reliance-")
        self.addCleanup(self.tempdir.cleanup)
        self.ledger = SQLiteAcceptanceLedger(Path(self.tempdir.name) / "accepted.sqlite3")

    def observe(self, data=None, *, authorization=None, effect=None, at=AT):
        t = FakeReadOnly(pull() if data is None else data)
        result = observe_github_merge(
            authorization=self.auth if authorization is None else authorization,
            authority_key=self.auth_key.public_key(),
            authority_principal="buyer-authority",
            authority_key_id="auth-key-1",
            expected_effect=EFFECT if effect is None else effect,
            observer_key=self.obs_key,
            observer_principal="git-observer-1",
            observer_key_id="observer-key-1",
            transport=t,
            now=at,
        )
        return result, t

    def rely(self, observation):
        return assess_reliance(
            authorization=self.auth,
            observation=observation,
            authority_key=self.auth_key.public_key(),
            observer_key=self.obs_key.public_key(),
            authority_principal="buyer-authority",
            authority_key_id="auth-key-1",
            observer_principal="git-observer-1",
            observer_key_id="observer-key-1",
            expected_effect=EFFECT,
            expected_provider="github",
            now=AT,
            already_accepted=self.ledger.replay_guard(
                relying_party="acquiring-team", provider="github"
            ),
        )

    def test_exact_merged_head_signed_and_accepted_once(self):
        result, t = self.observe(pull())
        self.assertEqual(t.calls, [("example-co/critical", 42)])
        self.assertTrue(result["recorded"])
        self.assertEqual(result["observation"]["outcome"], "applied")
        self.assertEqual(
            result["observation"]["provider_event_id"],
            f"github:example-co/critical#42:{M_SHA}",
        )
        self.assertTrue(self.rely(result["observation"])["accepted"])
        self.assertEqual(self.rely(result["observation"])["reasons"],
                         ["evidence_already_relied_on"])

    def test_merged_at_unapproved_head_is_signed_failed_and_refused(self):
        result, _ = self.observe(pull(head=B_SHA))
        self.assertEqual(result["observation"]["outcome"], "failed")
        self.assertFalse(self.rely(result["observation"])["accepted"])
        self.assertEqual(self.rely(result["observation"])["reasons"],
                         ["outcome_not_confirmed"])

    def test_merge_precedes_authorization_is_signed_failed(self):
        result, _ = self.observe(pull(at="2030-01-01T09:59:59Z"))
        self.assertEqual(result["observation"]["outcome"], "failed")
        self.assertFalse(self.rely(result["observation"])["accepted"])

    def test_open_or_closed_without_merge_cannot_be_accepted(self):
        for state, expected in [("open", "unknown"), ("closed", "failed")]:
            with self.subTest(state=state):
                result, _ = self.observe(pull(merged=False, state=state))
                self.assertEqual(result["observation"]["outcome"], expected)
                self.assertFalse(self.rely(result["observation"])["accepted"])

    def test_wrong_destination_branch_is_not_signed(self):
        data = pull()
        data["base"]["ref"] = "release/production"
        result, _ = self.observe(data)
        self.assertFalse(result["recorded"])
        self.assertEqual(result["reason"], "unexpected_base_branch")

    def test_repository_rename_or_wrong_pr_never_signed(self):
        for data in (pull(repo="renamed/project"), pull(number=87)):
            with self.subTest(data=data):
                result, _ = self.observe(data)
                self.assertFalse(result["recorded"])
                self.assertIsNone(result["observation"])

    def test_api_failure_and_malformed_provider_response_not_signed(self):
        for data in (
            ConnectionError("private token missing"),
            {"message": "permission denied"},
            pull(merged=True, at="nonsense"),
            {**pull(), "merge_commit_sha": None},
        ):
            with self.subTest(data=repr(data)):
                result, _ = self.observe(data)
                self.assertFalse(result["recorded"])
                self.assertIsNone(result["observation"])

    def test_unauthenticated_or_unauthorized_source_never_observed(self):
        auth = copy.deepcopy(self.auth)
        auth["effect"]["expected_head_sha"] = B_SHA
        result, t = self.observe(authorization=auth)
        self.assertFalse(result["recorded"])
        self.assertEqual(t.calls, [])
        deny = sign_record({
            **{k: v for k, v in self.auth.items() if k not in ("signature", "record_hash")},
            "decision": "deny",
        }, self.auth_key, key_id="auth-key-1")
        result, t = self.observe(authorization=deny)
        self.assertFalse(result["recorded"])
        self.assertEqual(t.calls, [])

    def test_uncheckable_effect_constraint_never_signed(self):
        other = {**EFFECT, "merge_method": "squash"}
        auth = sign_record({
            **{k: v for k, v in self.auth.items() if k not in ("signature", "record_hash")},
            "effect": other,
        }, self.auth_key, key_id="auth-key-1")
        result, t = self.observe(authorization=auth, effect=other)
        self.assertFalse(result["recorded"])
        self.assertEqual(result["reason"], "unsupported_or_mismatched_effect")
        self.assertEqual(t.calls, [])

    def test_expired_authorization_never_calls_github(self):
        result, t = self.observe(at=AT+timedelta(days=1))
        self.assertFalse(result["recorded"])
        self.assertEqual(result["reason"], "authorization_not_current")
        self.assertEqual(t.calls, [])

    def test_future_merge_timestamp_refused_without_signature(self):
        result, _ = self.observe(pull(at="2030-01-01T12:05:00Z"))
        self.assertFalse(result["recorded"])
        self.assertEqual(result["reason"], "merge_timestamp_in_future")

    def test_observer_does_not_claim_merge_method_from_get_response(self):
        result, _ = self.observe(pull())
        self.assertNotIn("merge_method", result["observation"]["effect"])
        self.assertNotIn("merge_method", result["observation"])

    def test_event_uniqueness_and_scope_after_realistic_merge(self):
        accepted, _ = self.observe(pull())
        self.assertTrue(self.rely(accepted["observation"])["accepted"])
        other = sign_record({
            **{k: v for k, v in self.auth.items() if k not in ("signature", "record_hash")},
            "issued_at": "2030-01-01T10:00:01Z",
        }, self.auth_key, key_id="auth-key-1")
        # The same GitHub merge event must not justify two different grants.
        self.assertFalse(self.ledger.reserve(
            "acquiring-team", "github", other["record_hash"],
            accepted["observation"]["provider_event_id"],
        ))


if __name__ == "__main__":
    unittest.main()
