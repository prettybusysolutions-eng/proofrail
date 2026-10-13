import copy
import unittest
from scripts.score_adopter_trial import score


def fixture():
    manifest = dict(workflow='synthetic test only', baseline_tools='fixture',
                    assisted_version='fixture', label_approver='fixture', cases=[])
    rows = []
    for i in range(20):
        label = 'needs_review' if i < 10 else 'no_findings'
        manifest['cases'].append(dict(case_id=str(i), expected_label=label, critical=i < 5))
        for arm, seconds, reviewer in [('baseline', 100, i % 2), ('assisted', 60, 1 - i % 2)]:
            rows.append(dict(case_id=str(i), arm=arm, elapsed_seconds=str(seconds),
                             reviewer_id=str(reviewer), observed_label=label))
    return manifest, rows


class TrialScoringTests(unittest.TestCase):
    def test_measured_gate_does_not_establish_sales(self):
        m, rows = fixture()
        result = score(m, rows)
        self.assertTrue(result['proposed_technical_gate_met'])
        self.assertEqual(result['commercial_validation'], 'NOT_ESTABLISHED')

    def test_critical_miss_blocks_fast_results(self):
        m, rows = fixture()
        rows[1]['observed_label'] = 'no_findings'
        self.assertFalse(score(m, rows)['proposed_technical_gate_met'])

    def test_missing_duplicate_and_carryover_results_rejected(self):
        m, rows = fixture()
        variants = [rows[:-1], rows + [rows[0]], copy.deepcopy(rows)]
        variants[-1][1]['reviewer_id'] = rows[0]['reviewer_id']
        for variant in variants:
            with self.assertRaises(ValueError):
                score(m, variant)

    def test_nonfinite_and_invented_blank_times_rejected(self):
        for value in ('nan', 'inf', '-1', '0', ''):
            m, rows = fixture()
            rows[0]['elapsed_seconds'] = value
            with self.assertRaises(ValueError):
                score(m, rows)

    def test_unapproved_labels_rejected(self):
        m, rows = fixture()
        m['cases'][0]['expected_label'] = None
        with self.assertRaises(ValueError):
            score(m, rows)
