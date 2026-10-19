import copy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from proofrail.audit_review import review_events


def lifecycle():
    common = {'tenant_id': 'tenant-a', 'permit_hash': 'a' * 64,
              'observed_at': '2026-10-12T19:00:00Z'}
    return [dict(common, sequence=1, event_id='mint', action='permit.mint',
                 object_type='permit', object_id='p1', outcome='permitted',
                 state='PERMITTED', metadata={}, reason_codes=[]),
            dict(common, sequence=2, event_id='execute', action='github_merge.execute',
                 object_type='execution', object_id='x1', outcome='success',
                 state='CONSUMED', metadata={'adapter_status': 'success'}, reason_codes=['reconciled']),
            dict(common, sequence=3, event_id='reconcile', action='github_merge.reconcile',
                 object_type='reconciliation', object_id='r1', outcome='reconciled',
                 state='RECONCILED', metadata={'execution_id': 'x1'}, reason_codes=['provider_outcome_confirmed'])]


def chained(events):
    """Hash-chain events exactly as PilotControlPlane._audit does."""
    from proofrail.core import digest_ledger_entry

    previous, out = 'GENESIS', []
    for event in copy.deepcopy(events):
        event['previous_hash'] = previous
        event['entry_hash'] = digest_ledger_entry(event)
        previous = event['entry_hash']
        out.append(event)
    return out


class AuditReviewTests(unittest.TestCase):
    def codes(self, events):
        return {f['code'] for f in review_events(events, tenant_id='tenant-a')['findings']}

    def test_intact_hash_chain_is_consistent_not_certified(self):
        result = review_events(chained(lifecycle()), tenant_id='tenant-a')
        self.assertEqual(result['status'], 'NO_FINDINGS_IN_SUPPLIED_EVENTS')
        self.assertEqual(result['authenticity'], 'HASH_CHAIN_CONSISTENT')
        self.assertEqual(result['hash_chain'], {'starts_at_genesis': True, 'entries': 3})
        self.assertFalse(result['authorization_proven'])

    def test_edited_event_breaks_hash_chain(self):
        # The original gap: a claim edited after recording still triaged clean.
        events = chained(lifecycle())
        events[1]['metadata']['adapter_status'] = 'success'
        events[1]['outcome'] = 'success'
        events[1]['reason_codes'] = ['edited']
        result = review_events(events, tenant_id='tenant-a')
        self.assertEqual(result['authenticity'], 'HASH_CHAIN_INVALID')
        self.assertIn('hash_chain_invalid', {f['code'] for f in result['findings']})
        self.assertEqual(result['status'], 'NEEDS_REVIEW')

    def test_removed_or_reordered_event_breaks_links(self):
        events = chained(lifecycle())
        self.assertIn('hash_chain_broken', self.codes([events[0], events[2]]))
        self.assertIn('hash_chain_broken', self.codes([events[1], events[0], events[2]]))

    def test_rehashing_an_edit_still_breaks_the_next_link(self):
        events = chained(lifecycle())
        from proofrail.core import digest_ledger_entry
        events[1]['metadata']['adapter_status'] = 'failed'
        events[1]['entry_hash'] = digest_ledger_entry(events[1])
        codes = self.codes(events)
        self.assertNotIn('hash_chain_invalid', codes)
        self.assertIn('hash_chain_broken', codes)

    def test_partially_hashed_export_is_invalid(self):
        events = chained(lifecycle())
        events[2].pop('entry_hash')
        result = review_events(events, tenant_id='tenant-a')
        self.assertEqual(result['authenticity'], 'HASH_CHAIN_INVALID')
        self.assertIn('partial_hash_chain', {f['code'] for f in result['findings']})

    def test_cli_exits_4_on_tampered_chained_export(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'events.jsonl'
            events = chained(lifecycle())
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            ok = subprocess.run([sys.executable, '-m', 'proofrail.cli', 'audit-review',
                                 '--events', str(path), '--tenant', 'tenant-a'],
                                capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(ok.stdout)['authenticity'], 'HASH_CHAIN_CONSISTENT')
            events[0]['object_id'] = 'p-forged'
            path.write_text(''.join(json.dumps(e) + '\n' for e in events))
            bad = subprocess.run([sys.executable, '-m', 'proofrail.cli', 'audit-review',
                                  '--events', str(path), '--tenant', 'tenant-a'],
                                 capture_output=True, text=True)
            self.assertEqual(bad.returncode, 4)
            self.assertEqual(json.loads(bad.stdout)['authenticity'], 'HASH_CHAIN_INVALID')

    def test_consistent_claims_are_not_certification(self):
        result = review_events(lifecycle(), tenant_id='tenant-a')
        self.assertEqual(result['status'], 'NO_FINDINGS_IN_SUPPLIED_EVENTS')
        self.assertEqual(result['authenticity'], 'NOT_CHECKED')
        self.assertFalse(result['authorization_proven'])
        self.assertFalse(result['provider_effect_proven'])

    def test_empty_export_is_not_clean(self):
        self.assertIn('no_reviewable_lifecycle', self.codes([]))

    def test_tenant_mismatch_is_never_combined(self):
        events = lifecycle()
        events[0]['tenant_id'] = 'tenant-b'
        self.assertTrue({'tenant_mismatch', 'missing_prior_mint'} <= self.codes(events))

    def test_missing_reconciliation(self):
        self.assertIn('missing_reconciliation', self.codes(lifecycle()[:2]))

    def test_partial_export_reports_missing_mint(self):
        self.assertIn('missing_prior_mint', self.codes(lifecycle()[1:]))

    def test_wrong_execution_binding(self):
        events = lifecycle()
        events[-1]['metadata']['execution_id'] = 'another-execution'
        self.assertTrue({'missing_execution_binding', 'missing_reconciliation'} <= self.codes(events))

    def test_unknown_adapter_cannot_be_summarized_as_clean_success(self):
        events = lifecycle()
        events[1]['metadata']['adapter_status'] = 'unknown'
        self.assertTrue({'contradictory_execution', 'unresolved_execution', 'conflicting_success_claims'} <= self.codes(events))

    def test_duplicate_execution_and_replay_signal(self):
        events = lifecycle()
        duplicate = copy.deepcopy(events[1])
        duplicate['reason_codes'].append('permit_replayed')
        events.append(duplicate)
        self.assertTrue({'duplicate_event', 'multiple_execution_records', 'replay_attempt_recorded'} <= self.codes(events))

    def test_reordered_records_are_not_silently_sorted(self):
        self.assertIn('sequence_discontinuity', self.codes(list(reversed(lifecycle()))))

    def test_malformed_shapes_do_not_raise(self):
        for field, value in [('sequence', {}), ('sequence', True), ('metadata', []),
                             ('reason_codes', None), ('event_id', []), ('observed_at', 'bad')]:
            with self.subTest(field=field, value=value):
                events = lifecycle()
                events[1][field] = value
                self.assertIn('malformed_event', self.codes(events))
        self.assertIn('malformed_event', self.codes([None]))

    def test_unhashable_optional_fields_do_not_raise(self):
        events = lifecycle()
        events[1]['metadata']['adapter_status'] = []
        events[2]['metadata']['execution_id'] = {}
        self.assertIn('incomplete_execution', self.codes(events))
        self.assertIn('missing_execution_binding', self.codes(events))

    def test_unsupported_permit_action_requires_review(self):
        events = lifecycle()
        events[-1]['action'] = 'future.action'
        self.assertIn('unsupported_lifecycle_event', self.codes(events))

    def test_cli_exit_codes_and_preserves_input(self):
        with TemporaryDirectory() as directory:
            path, output = Path(directory) / 'events.jsonl', Path(directory) / 'review.json'
            def invoke():
                return subprocess.run([sys.executable, '-m', 'proofrail.cli', 'audit-review',
                                       '--events', str(path), '--tenant', 'tenant-a',
                                       '--output', str(output)], capture_output=True, text=True)
            path.write_text(''.join(json.dumps(e) + '\n' for e in lifecycle()))
            original = path.read_bytes()
            completed = invoke()
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(output.read_text())['authenticity'], 'NOT_CHECKED')
            self.assertEqual(path.read_bytes(), original)
            path.write_text(json.dumps(lifecycle()[1]) + '\n')
            self.assertEqual(invoke().returncode, 4)
            path.write_text('{not json}\n')
            self.assertEqual(invoke().returncode, 2)


if __name__ == '__main__':
    unittest.main()
