"""Synthetic checks for live-runner orchestration and offline re-verification.

No GitHub HTTP traffic. The actual read-only GitHub GET is exercised by
.github/workflows/live-github-observer.yml on a trusted same-repo PR.
"""
from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from scripts.live_github_observer_check import run
from scripts.reverify_live_evidence import verify


REPO = "prettybusysolutions-eng/proofrail"
BASE = "main"
OPEN_BASE = "feat/read-only-github-reliance-observer-20261030"
HEAD = "a" * 40
OTHER = "b" * 40
MERGE = "c" * 40
OPEN_HEAD = "d" * 40


class FakeReadOnly:
    def get_pull(self, repository, number):
        assert repository == REPO
        if number == 39:
            return {
                "number": 39,
                "base": {"repo": {"full_name": REPO}, "ref": BASE},
                "head": {"sha": HEAD},
                "merged": True,
                "state": "closed",
                "merged_at": self.merged_at,
                "merge_commit_sha": MERGE,
            }
        if number == 68:
            return {
                "number": 68,
                "base": {"repo": {"full_name": REPO}, "ref": OPEN_BASE},
                "head": {"sha": OPEN_HEAD},
                "merged": False,
                "state": "open",
                "merged_at": None,
                "merge_commit_sha": None,
            }
        raise AssertionError(f"unexpected PR number {number}")


class LiveTrialSelfCheckTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        head_time = now - timedelta(days=3)
        self.transport = FakeReadOnly()
        self.transport.merged_at = (
            now - timedelta(days=2)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        def pr_git(pr):
            if pr == 39:
                return HEAD, head_time
            if pr == 68:
                return OPEN_HEAD, head_time
            raise AssertionError("wrong git PR")

        args = SimpleNamespace(
            repository=REPO, merged_pr=39, base_ref=BASE,
            open_pr=68, open_base_ref=OPEN_BASE,
        )
        with patch("scripts.live_github_observer_check.pr_head_from_git", side_effect=pr_git):
            with patch("scripts.live_github_observer_check.branch_tip_from_git", return_value=OTHER):
                self.package, self.failures = run(args, transport=self.transport)
        self.args = dict(
            authority_hex=self.package["trust_anchors"]["authority"]["public_key_hex"],
            observer_hex=self.package["trust_anchors"]["observer"]["public_key_hex"],
            repository=REPO, merged_pr=39, merged_head=HEAD,
            base_ref=BASE, open_pr=68, open_base_ref=OPEN_BASE,
        )

    def test_all_five_live_scenarios_and_replay_are_internally_consistent(self):
        self.assertEqual(self.failures, 0)
        self.assertEqual(self.package["summary"], {"scenarios": 5, "failed": 0})
        self.assertEqual(
            [r["scenario"] for r in self.package["results"]],
            ["A_exact_merge_RETROSPECTIVE", "B_wrong_head",
             "C_authorized_after_merge", "D_wrong_base", "E_open_PR"],
        )
        self.assertEqual(
            self.package["results"][0]["replay_reasons"], ["evidence_already_relied_on"]
        )
        ok, issues = verify(self.package, **self.args)
        self.assertTrue(ok, issues)

    def test_wrong_pinned_public_key_fails_reverification(self):
        args = {**self.args, "authority_hex": "f" * 64}
        ok, errors = verify(self.package, **args)
        self.assertFalse(ok)
        self.assertIn("missing_or_unpinned_keys_or_invalid_time", errors)

    def test_mismatched_independent_git_head_fails(self):
        args = {**self.args, "merged_head": OTHER}
        ok, errors = verify(self.package, **args)
        self.assertFalse(ok)
        self.assertIn("unexpected_git_source_merged_pr_head", errors)

    def test_mutated_signed_result_fails(self):
        package = copy.deepcopy(self.package)
        package["results"][0]["observation"]["outcome"] = "failed"
        ok, errors = verify(package, **self.args)
        self.assertFalse(ok)
        self.assertIn("A_exact_merge_RETROSPECTIVE:unexpected_observed_result", errors)

    def test_recorded_pass_flag_or_expected_result_cannot_be_forged(self):
        package = copy.deepcopy(self.package)
        package["results"][1]["expected"]["verdict"] = "REFUSE"
        package["results"][0]["passed"] = False
        ok, errors = verify(package, **self.args)
        self.assertFalse(ok)
        self.assertIn("B_wrong_head:scenario_expectation_changed", errors)
        self.assertIn("A_exact_merge_RETROSPECTIVE:original_test_failed", errors)

    def test_missing_scenario_refuses(self):
        package = copy.deepcopy(self.package)
        package["results"].pop()
        ok, errors = verify(package, **self.args)
        self.assertFalse(ok)
        self.assertIn("missing_scenarios", errors)


if __name__ == "__main__":
    unittest.main()
