"""Challenge exact-effect reconciliation after a provider-side race."""
import socket
import unittest

from integrations.openclaw.github_adapter import GitHubMergeAdapter


class ExactEffectReconciliationTests(unittest.TestCase):
    def execute(self, observed_head, merge_result):
        class Transport:
            def __init__(self):
                self.calls = []
                self.responses = [
                    (200, {}, {"merged": False, "mergeable": True, "head": {"sha": "a" * 40}}),
                    merge_result,
                    (200, {}, {"merged": True, "merge_commit_sha": "c" * 40,
                               "head": {"sha": observed_head}}),
                ]

            def request(self, method, path, **kwargs):
                self.calls.append(method)
                response = self.responses.pop(0)
                if isinstance(response, Exception):
                    raise response
                return response

        transport = Transport()
        receipt = GitHubMergeAdapter(transport).execute(
            {"execution": {"owner": "fixture", "repo": "fixture", "pull_number": 1,
                           "expected_head_sha": "a" * 40, "merge_method": "squash"}},
            idempotency_key="exact-effect-audit",
        )
        self.assertEqual(transport.calls, ["GET", "PUT", "GET"])
        return receipt

    def test_timeout_followed_by_different_merged_head_is_not_success(self):
        receipt = self.execute("b" * 40, socket.timeout("response lost"))
        self.assertNotEqual(receipt["status"], "success")
        self.assertFalse(receipt["side_effect_confirmed"])
        self.assertFalse(receipt["retry_safe"])

    def test_conflict_followed_by_different_merged_head_is_not_success(self):
        receipt = self.execute("b" * 40, (409, {}, {"message": "Head changed"}))
        self.assertNotEqual(receipt["status"], "success")
        self.assertFalse(receipt["side_effect_confirmed"])
        self.assertFalse(receipt["retry_safe"])

    def test_missing_observed_head_is_not_success(self):
        receipt = self.execute(None, socket.timeout("response lost"))
        self.assertNotEqual(receipt["status"], "success")
        self.assertFalse(receipt["side_effect_confirmed"])

    def test_matching_head_can_reconcile_lost_response(self):
        receipt = self.execute("a" * 40, socket.timeout("response lost"))
        self.assertEqual(receipt["status"], "success")
        self.assertTrue(receipt["side_effect_confirmed"])
