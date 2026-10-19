"""Adapter behaviour against response shapes recorded from the live GitHub API.

Source: evidence/live-github-2026-10-19/results.json. Earlier fixtures assumed
GitHub answers a stale-SHA merge of an already-merged PR with 409. It does not:
it ignores the sha precondition and returns 200 with the *existing* merge.
"""
import json
import unittest
from pathlib import Path

from integrations.openclaw.github_adapter import GitHubMergeAdapter

EVIDENCE = json.loads(
    (Path(__file__).resolve().parents[1] / "evidence/live-github-2026-10-19/results.json").read_text()
)
RACE = EVIDENCE["scenarios"]["C_foreign_head_race"]
RECORDED_PUT = EVIDENCE["observed_github_behaviour"]["put_merge_on_already_merged_pr_with_stale_sha"]


def action(head):
    return {"execution": {"owner": "o", "repo": "r", "pull_number": RACE["pr"],
                          "expected_head_sha": head, "merge_method": "squash"}}


class RecordedTransport:
    """Replays the live sequence: preflight sees the approved head, another actor
    merges a different head, then GitHub answers our merge exactly as recorded."""

    def __init__(self, approved, foreign, merge_sha, put_response):
        self.approved, self.foreign, self.merge_sha = approved, foreign, merge_sha
        self.put_response, self.gets = put_response, 0

    def request(self, method, path, *, body=None, idempotency_key=None):
        if method == "PUT":
            return self.put_response["status"], {}, dict(self.put_response["body"])
        self.gets += 1
        if self.gets == 1:
            return 200, {}, {"merged": False, "mergeable": True, "state": "open",
                             "head": {"sha": self.approved}}
        return 200, {}, {"merged": True, "state": "closed", "merge_commit_sha": self.merge_sha,
                         "head": {"sha": self.foreign}}


class RecordedGitHubResponseTests(unittest.TestCase):
    def test_recorded_put_shape_is_200_success_with_existing_merge(self):
        # Pin the real behaviour so fixtures cannot drift back to an imagined 409.
        self.assertEqual(RECORDED_PUT["status"], 200)
        self.assertIs(RECORDED_PUT["body"]["merged"], True)
        self.assertEqual(RECORDED_PUT["body"]["sha"], RACE["foreign_merge_sha"])

    def test_foreign_head_merge_answered_200_is_not_our_success(self):
        transport = RecordedTransport(RACE["approved_head"], RACE["foreign_head"],
                                      RACE["foreign_merge_sha"], RECORDED_PUT)
        receipt = GitHubMergeAdapter(transport).execute(action(RACE["approved_head"]),
                                                        idempotency_key="k")
        self.assertEqual(receipt["status"], "failed")
        self.assertFalse(receipt["side_effect_confirmed"])
        self.assertFalse(receipt["retry_safe"])
        self.assertEqual(receipt["receipt_evidence"]["reason"], "merged_head_mismatch")

    def test_live_runs_match_expected_verdicts(self):
        s = EVIDENCE["scenarios"]
        self.assertEqual(s["A_happy_path"]["authority_state"], "RECONCILED")
        self.assertEqual(s["A_happy_path"]["github_head_after_merge"], s["A_happy_path"]["approved_head"])
        self.assertEqual(s["B_moved_head"]["authority_state"], "EXECUTION_FAILED")
        self.assertFalse(s["B_moved_head"]["github_merged"])
        self.assertEqual(s["D_replay"], {"pr": s["A_happy_path"]["pr"],
                                         "outcome": "permit_replayed", "github_calls": 0})
        self.assertEqual(s["C_foreign_head_race"]["reason"], "merged_head_mismatch")
        # The pre-#31 adapter falsely confirmed the same live race.
        self.assertEqual(s["C_old_adapter_8e84c17"]["authority_state"], "RECONCILED")
        self.assertNotEqual(s["C_old_adapter_8e84c17"]["github_head_after_merge"],
                            s["C_old_adapter_8e84c17"]["approved_head"])


if __name__ == "__main__":
    unittest.main()
