"""Adversarial tests for repository identity and optional pre-merge status anchors.

All provider interactions are deterministic fake GETs. The suite does not
claim live GitHub App provenance, ruleset enforcement, or provider independence.
"""
from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from proofrail.crypto import sign_record
from proofrail.github_observer import (
    GitHubReadOnlyPullTransport, observe_github_merge,
)

NOW = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
HEAD = "a" * 40
MERGE = "b" * 40
REPO = "example-co/critical"
IDENTITY = 777


def pr(*, repo_id=IDENTITY, head=HEAD, merge_sha=MERGE, merged_at="2030-01-01T11:30:00Z"):
    return {
        "number": 42, "state": "closed", "merged": True,
        "head": {"sha": head},
        "base": {"ref": "main", "repo": {"id": repo_id, "full_name": REPO}},
        "merged_at": merged_at,
        "merge_commit_sha": merge_sha,
    }


class FakeTransport:
    def __init__(self, pull=None, statuses=None):
        self.pull = pr() if pull is None else pull
        self.statuses = statuses if statuses is not None else [[]]
        self.calls = []

    def get_pull(self, repository, number):
        self.calls.append(("GET_PR", repository, number))
        if isinstance(self.pull, Exception):
            raise self.pull
        return copy.deepcopy(self.pull)

    def get_statuses(self, repository, sha, page):
        self.calls.append(("GET_STATUS", repository, sha, page))
        if isinstance(self.statuses, Exception):
            raise self.statuses
        return copy.deepcopy(self.statuses[page - 1] if page <= len(self.statuses) else [])


class ObserverAnchorTests(unittest.TestCase):
    def setUp(self):
        self.issuer = Ed25519PrivateKey.generate()
        self.observer = Ed25519PrivateKey.generate()
        self.effect = {
            "action_type": "github_merge",
            "repository": REPO,
            "repository_id": IDENTITY,
            "pull_number": 42,
            "expected_head_sha": HEAD,
            "expected_base_ref": "main",
        }

    def authorize(self, effect=None, issued="2030-01-01T10:00:00Z"):
        return sign_record({
            "kind": "proofrail.reliance.authorization.v0",
            "decision": "allow", "issued_at": issued,
            "expires_at": "2030-01-01T13:00:00Z",
            "signer": {"principal_id": "issuer"},
            "effect": self.effect if effect is None else effect,
        }, self.issuer, key_id="issuer-k")

    def observe(self, transport, *, effect=None, auth=None):
        effect = self.effect if effect is None else effect
        auth = self.authorize(effect) if auth is None else auth
        return observe_github_merge(
            auth,
            authority_key=self.issuer.public_key(), authority_principal="issuer",
            authority_key_id="issuer-k", expected_effect=effect,
            observer_key=self.observer, observer_principal="observer",
            observer_key_id="observer-k", transport=transport, now=NOW,
        )

    def anchored(self):
        effect = {**self.effect, "pre_merge_anchor": {
            "type": "github_commit_status",
            "context": "proofrail/permit",
            "creator_id": 1234,
        }}
        auth = self.authorize(effect)
        return effect, auth

    @staticmethod
    def status(auth, *, state="success", creator_id=1234,
               description=None, at="2030-01-01T11:20:00Z",
               context="proofrail/permit"):
        return {
            "state": state, "creator": {"id": creator_id},
            "context": context, "created_at": at,
            "description": ("proofrail-auth-sha256:" + auth["record_hash"]
                            if description is None else description),
        }

    def test_repository_id_is_signed_and_enforced(self):
        t = FakeTransport(pr(repo_id=778))
        result = self.observe(t)
        self.assertFalse(result["recorded"])
        self.assertEqual(result["reason"], "unexpected_repository_id")
        self.assertEqual(len(t.calls), 1)

    def test_invalid_or_legacy_repository_identity_never_hits_provider(self):
        for value in (None, True, 0, -1, "777"):
            with self.subTest(value=value):
                effect = dict(self.effect)
                if value is None:
                    del effect["repository_id"]
                else:
                    effect["repository_id"] = value
                t = FakeTransport()
                result = self.observe(t, effect=effect)
                self.assertFalse(result["recorded"])
                self.assertEqual(t.calls, [])

    def test_repository_id_is_more_stable_than_spelling_but_rename_refused(self):
        changed = pr()
        changed["base"]["repo"]["full_name"] = "another-owner/critical"
        result = self.observe(FakeTransport(changed))
        self.assertEqual(result["reason"], "unexpected_repository_or_rename")

    def test_optional_merge_sha_is_compatible_with_both_response_shapes(self):
        for sha in (MERGE, None):
            with self.subTest(sha=sha):
                result = self.observe(FakeTransport(pr(merge_sha=sha)))
                self.assertEqual(result["observation"]["outcome"], "applied")
                self.assertEqual(result["observation"]["provider_event_id"],
                                 "github:repo:777:pr:42:merged")

    def test_malformed_present_merge_sha_is_refused(self):
        result = self.observe(FakeTransport(pr(merge_sha="not-sha")))
        self.assertEqual(result["reason"], "missing_confirmed_merge_identifiers")

    def test_valid_premerge_anchor_allows_recorded_outcome(self):
        effect, auth = self.anchored()
        t = FakeTransport(statuses=[[self.status(auth)]])
        result = self.observe(t, effect=effect, auth=auth)
        self.assertEqual(result["observation"]["outcome"], "applied")
        self.assertEqual(t.calls[-1], ("GET_STATUS", REPO, HEAD, 1))

    def test_no_anchor_causes_signed_failure(self):
        effect, auth = self.anchored()
        t = FakeTransport()
        result = self.observe(t, effect=effect, auth=auth)
        self.assertEqual(result["observation"]["outcome"], "failed")

    def test_spoofed_creator_and_description_refused(self):
        effect, auth = self.anchored()
        for bad in (
            self.status(auth, creator_id=987),
            self.status(auth, creator_id=True),
            self.status(auth, description="looks similar but not the hash"),
            self.status(auth, state="pending"),
            self.status(auth, context="proofrail/other"),
        ):
            with self.subTest(bad=bad):
                result = self.observe(FakeTransport(statuses=[[bad]]),
                                      effect=effect, auth=auth)
                self.assertEqual(result["observation"]["outcome"], "failed")

    def test_revoked_and_superseded_context_is_not_sufficient(self):
        effect, auth = self.anchored()
        older = self.status(auth, at="2030-01-01T11:00:00Z")
        later = self.status(auth, at="2030-01-01T11:22:00Z", state="failure")
        t = FakeTransport(statuses=[[later, older]])
        result = self.observe(t, effect=effect, auth=auth)
        self.assertEqual(result["observation"]["outcome"], "failed")

    def test_same_second_and_concurrent_statuses_fail_closed(self):
        effect, auth = self.anchored()
        for statuses in (
            [self.status(auth, at="2030-01-01T11:30:00Z")],
            [self.status(auth), self.status(auth, state="failure")],
        ):
            result = self.observe(FakeTransport(statuses=[statuses]),
                                  effect=effect, auth=auth)
            self.assertEqual(result["observation"]["outcome"], "failed")

    def test_status_posted_before_issuance_is_not_authorization(self):
        effect, auth = self.anchored()
        old = self.status(auth, at="2030-01-01T09:00:00Z")
        result = self.observe(FakeTransport(statuses=[[old]]),
                              effect=effect, auth=auth)
        self.assertEqual(result["observation"]["outcome"], "failed")

    def test_post_merge_status_cannot_backdate_grant(self):
        effect, auth = self.anchored()
        result = self.observe(FakeTransport(statuses=[[
            self.status(auth, at="2030-01-01T11:31:00Z"),
        ]]), effect=effect, auth=auth)
        self.assertEqual(result["observation"]["outcome"], "failed")

    def test_moved_head_is_not_saved_by_status_on_other_commit(self):
        effect, auth = self.anchored()
        result = self.observe(FakeTransport(
            pull=pr(head="c"*40), statuses=[[self.status(auth)]],
        ), effect=effect, auth=auth)
        self.assertEqual(result["observation"]["outcome"], "failed")

    def test_paginates_full_status_pages(self):
        effect, auth = self.anchored()
        padding = self.status(auth, context="another/context")
        t = FakeTransport(statuses=[[padding] * 100, [self.status(auth)]])
        result = self.observe(t, effect=effect, auth=auth)
        self.assertEqual(result["observation"]["outcome"], "applied")
        self.assertEqual([c[-1] for c in t.calls if c[0] == "GET_STATUS"], [1, 2])

    def test_page_limit_and_transport_error_fail_without_signed_claim(self):
        effect, auth = self.anchored()
        padding = self.status(auth, context="another/context")
        for statuses in ([[padding] * 100 for _ in range(10)], ConnectionError("offline")):
            t = FakeTransport(statuses=statuses)
            result = self.observe(t, effect=effect, auth=auth)
            self.assertEqual(result["reason"], "github_anchor_observation_unavailable")
            self.assertIsNone(result["observation"])

    def test_unsupported_check_run_anchor_and_extra_constraint_fail_preflight(self):
        for anchor in (
            {"type": "github_check_run", "context": "proofrail/permit", "creator_id": 1234},
            {"type": "github_commit_status", "context": "proofrail/permit", "creator_id": 1234, "opaque": 1},
        ):
            effect = {**self.effect, "pre_merge_anchor": anchor}
            t = FakeTransport()
            result = self.observe(t, effect=effect)
            self.assertEqual(result["reason"], "unsupported_pre_merge_anchor")
            self.assertEqual(t.calls, [])


class Response:
    status = 200

    def __init__(self, obj):
        self.data = json.dumps(obj).encode()

    def read(self, size):
        return self.data[:size]


class FakeConnection:
    instances = []

    def __init__(self, host, timeout=None):
        self.host, self.timeout = host, timeout
        self.request_details = None
        self.closed = False
        FakeConnection.instances.append(self)

    def request(self, method, path, headers=None):
        self.request_details = (method, path, headers)

    def getresponse(self):
        path = self.request_details[1]
        return Response([] if "/statuses?" in path else pr(merge_sha=None))

    def close(self):
        self.closed = True


class TransportProtocolTests(unittest.TestCase):
    def test_only_allowlisted_get_endpoints_both_api_versions(self):
        with patch("proofrail.github_observer.http.client.HTTPSConnection",
                   FakeConnection):
            for version in ("2022-11-28", "2026-03-10"):
                t = GitHubReadOnlyPullTransport("dummy-test-token", api_version=version)
                self.assertEqual(t.get_pull(REPO, 42)["base"]["repo"]["id"], 777)
                self.assertEqual(t.get_statuses(REPO, HEAD, 1), [])
                for conn in FakeConnection.instances[-2:]:
                    method, path, headers = conn.request_details
                    self.assertEqual(method, "GET")
                    self.assertEqual(conn.host, "api.github.com")
                    self.assertEqual(headers["X-GitHub-Api-Version"], version)
                    self.assertTrue(conn.closed)
                    self.assertTrue(path.startswith("/repos/example-co/critical/"))
            with self.assertRaises(ValueError):
                GitHubReadOnlyPullTransport("token", api_version="2031-01-01")


if __name__ == "__main__":
    unittest.main()
