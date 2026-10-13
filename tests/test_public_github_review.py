import copy
import json
from pathlib import Path
import unittest
from proofrail.core import ProofRailError
from proofrail.public_github_review import review_public_snapshot

ROOT = Path(__file__).resolve().parents[1]


class PublicGitHubReviewTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT / 'evidence/public-github-2026-10-13/snapshot.json').read_text())

    def test_twenty_real_snapshots_remain_provider_observations(self):
        result = review_public_snapshot(self.snapshot)
        self.assertEqual(result['case_count'], 20)
        self.assertEqual(result['provider_states'], {'MERGED_RECORDED': 7, 'CLOSED_UNMERGED': 13})
        self.assertTrue(all(c['authorization'] == 'NOT_ESTABLISHED' for c in result['cases']))

    def test_mutated_merge_claim_missing_commit_rejected(self):
        self.snapshot['cases'][0]['pull']['merge_commit_sha'] = None
        with self.assertRaises(ProofRailError):
            review_public_snapshot(self.snapshot)

    def test_workflow_from_other_head_rejected(self):
        self.snapshot['cases'][0]['runs'][0]['head_sha'] = '0' * 40
        with self.assertRaises(ProofRailError):
            review_public_snapshot(self.snapshot)

    def test_duplicate_case_rejected(self):
        self.snapshot['cases'].append(copy.deepcopy(self.snapshot['cases'][0]))
        with self.assertRaises(ProofRailError):
            review_public_snapshot(self.snapshot)

    def test_merge_before_creation_rejected(self):
        self.snapshot['cases'][0]['pull']['merged_at'] = '2000-01-01T00:00:00Z'
        with self.assertRaises(ProofRailError):
            review_public_snapshot(self.snapshot)

    def test_dismissed_approval_not_counted_and_comment_does_not_approve(self):
        case = self.snapshot['cases'][0]
        review = dict(reviewer='r1', state='APPROVED', id=1, submitted_at='2026-10-01T00:00:00Z', commit_id=case['pull']['head_sha'])
        case['reviews'] = [review, dict(review, id=2, state='DISMISSED', submitted_at='2026-10-02T00:00:00Z'),
                           dict(review, id=3, state='COMMENTED', submitted_at='2026-10-03T00:00:00Z')]
        self.assertEqual(review_public_snapshot(self.snapshot)['cases'][0]['latest_current_head_approvals'], 0)

    def test_latest_rerun_supersedes_prior_failure(self):
        case = self.snapshot['cases'][0]
        run = copy.deepcopy(case['runs'][0])
        run.update(status='completed', conclusion='failure', run_attempt=1)
        case['runs'] = [run, dict(run, conclusion='success', run_attempt=2)]
        self.assertEqual(review_public_snapshot(self.snapshot)['cases'][0]['non_success_or_unfinished_run_ids'], [])

    def test_missing_runs_and_truncation_are_gaps_not_policy_violations(self):
        case = self.snapshot['cases'][0]
        case['runs'] = []
        case['coverage']['runs_truncated'] = True
        result = review_public_snapshot(self.snapshot)['cases'][0]
        self.assertTrue(any('incomplete' in q for q in result['questions']))
        self.assertTrue(any('does not establish' in q for q in result['questions']))
        self.assertEqual(result['authorization'], 'NOT_ESTABLISHED')
