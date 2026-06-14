import socket
import unittest

from integrations.openclaw.bridge import validate_adapter_receipt
from integrations.openclaw.github_adapter import GitHubMergeAdapter


ACTION = {
    "action_id": "merge-pr-42",
    "action_type": "github_merge",
    "target": "owner/repo#42",
    "risk": "high",
    "reversible": False,
    "claim_ids": ["checks-pass"],
    "execution": {
        "owner": "owner",
        "repo": "repo",
        "pull_number": 42,
        "expected_head_sha": "abc123",
        "merge_method": "squash",
    },
}


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, body=None, idempotency_key=None):
        self.calls.append((method, path, body, idempotency_key))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def open_pull(head="abc123"):
    return {
        "number": 42,
        "state": "open",
        "merged": False,
        "mergeable": True,
        "merge_commit_sha": "test-merge-sha",
        "head": {"sha": head},
        "base": {"sha": "base123"},
        "html_url": "https://github.com/owner/repo/pull/42",
    }


class GitHubAdapterTests(unittest.TestCase):
    def test_exact_head_merge_returns_contract_receipt(self):
        transport = FakeTransport(
            [
                (200, {}, open_pull()),
                (200, {}, {"merged": True, "sha": "merge123", "message": "merged"}),
                (
                    200,
                    {},
                    {
                        **open_pull(),
                        "merged": True,
                        "state": "closed",
                        "merge_commit_sha": "merge123",
                    },
                ),
            ]
        )
        receipt = GitHubMergeAdapter(transport).execute(ACTION, idempotency_key="k" * 64)
        validate_adapter_receipt(receipt, expected_idempotency_key="k" * 64)
        self.assertEqual(receipt["status"], "success")
        self.assertEqual(receipt["remote_operation_id"], "merge123")
        self.assertEqual(transport.calls[1][2]["sha"], "abc123")
        self.assertEqual(receipt["receipt_evidence"]["phase"], "reconciliation")

    def test_executor_success_claim_requires_external_reconciliation(self):
        transport = FakeTransport(
            [
                (200, {}, open_pull()),
                (200, {}, {"merged": True, "sha": "claimed", "message": "merged"}),
                (200, {}, open_pull()),
            ]
        )
        receipt = GitHubMergeAdapter(transport).execute(ACTION, idempotency_key="k" * 64)
        self.assertEqual(receipt["status"], "unknown")
        self.assertFalse(receipt["side_effect_confirmed"])
        self.assertFalse(receipt["retry_safe"])

    def test_head_mismatch_blocks_before_merge(self):
        transport = FakeTransport([(200, {}, open_pull(head="changed"))])
        receipt = GitHubMergeAdapter(transport).execute(ACTION, idempotency_key="k" * 64)
        self.assertEqual(receipt["status"], "failed")
        self.assertFalse(receipt["side_effect_confirmed"])
        self.assertEqual(len(transport.calls), 1)

    def test_timeout_reconciles_to_confirmed_merge(self):
        merged = {**open_pull(), "merged": True, "state": "closed", "merge_commit_sha": "merge456"}
        transport = FakeTransport(
            [
                (200, {}, open_pull()),
                socket.timeout("timed out"),
                (200, {}, merged),
            ]
        )
        receipt = GitHubMergeAdapter(transport).execute(ACTION, idempotency_key="k" * 64)
        self.assertEqual(receipt["status"], "success")
        self.assertEqual(receipt["remote_operation_id"], "merge456")
        self.assertEqual(receipt["receipt_evidence"]["phase"], "reconciliation")

    def test_double_timeout_returns_unknown_and_not_retry_safe(self):
        transport = FakeTransport(
            [
                (200, {}, open_pull()),
                socket.timeout("merge timed out"),
                socket.timeout("reconcile timed out"),
            ]
        )
        receipt = GitHubMergeAdapter(transport).execute(ACTION, idempotency_key="k" * 64)
        self.assertEqual(receipt["status"], "unknown")
        self.assertFalse(receipt["retry_safe"])

    def test_observe_reads_provider_state_without_executor_claims(self):
        merged = {
            **open_pull(),
            "merged": True,
            "state": "closed",
            "merge_commit_sha": "merge789",
        }
        transport = FakeTransport([(200, {}, merged)])
        observation = GitHubMergeAdapter(transport).observe(ACTION)
        self.assertTrue(observation["merged"])
        self.assertEqual(observation["merge_commit_sha"], "merge789")
        self.assertEqual(
            transport.calls,
            [("GET", "/repos/owner/repo/pulls/42", None, None)],
        )


if __name__ == "__main__":
    unittest.main()
