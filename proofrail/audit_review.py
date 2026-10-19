"""Conservative triage of supplied pilot audit events, not authorization proof."""
from collections import defaultdict
from datetime import datetime
import re

from .core import digest_ledger_entry


def _hash_chain(events, flag):
    """Check entry_hash/previous_hash links when the export carries them.

    Pilot exports are hash-chained; hand-built inputs may carry no hashes.
    A consistent chain shows the supplied events were not individually edited
    or reordered. It does not detect a full rewrite or tail truncation; that
    needs an independently retained checkpoint or external anchor.
    """
    records = [(line, e) for line, e in enumerate(events, 1) if isinstance(e, dict)]
    hashed = [(line, e) for line, e in records if 'entry_hash' in e]
    if not hashed:
        return 'NOT_CHECKED', None
    if len(hashed) != len(records):
        line, event = next((l, e) for l, e in records if 'entry_hash' not in e)
        flag('partial_hash_chain', event, line,
             'Some events carry entry_hash and others do not; obtain a complete hash-chained export.')
        return 'HASH_CHAIN_INVALID', {'starts_at_genesis': None, 'entries': len(hashed)}
    consistent = True
    previous = None
    for line, event in records:
        if event.get('entry_hash') != digest_ledger_entry(event):
            consistent = False
            flag('hash_chain_invalid', event, line,
                 'Event content does not match its entry_hash; it was altered after recording.')
        if previous is not None and event.get('previous_hash') != previous:
            consistent = False
            flag('hash_chain_broken', event, line,
                 'previous_hash does not link to the preceding event; events were removed, inserted or reordered.')
        previous = event.get('entry_hash')
    detail = {'starts_at_genesis': records[0][1].get('previous_hash') == 'GENESIS',
              'entries': len(records)}
    return ('HASH_CHAIN_CONSISTENT' if consistent else 'HASH_CHAIN_INVALID'), detail


def review_events(events, *, tenant_id):
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError('tenant_id is required')
    events = list(events)
    findings, grouped, seen_ids, seen_sequences = [], defaultdict(list), set(), set()
    count, previous = 0, None

    def flag(code, event, line, explanation):
        findings.append({'code': code, 'line': line,
                         'event_id': event.get('event_id'),
                         'permit_hash': event.get('permit_hash'),
                         'explanation': explanation})

    authenticity, chain = _hash_chain(events, flag)

    for line, event in enumerate(events, 1):
        count += 1
        if not isinstance(event, dict):
            flag('malformed_event', {}, line, 'Obtain an audit event object for this line.')
            continue
        required = ('event_id', 'tenant_id', 'action', 'object_id', 'object_type', 'outcome', 'observed_at')
        sequence = event.get('sequence')
        valid = all(isinstance(event.get(k), str) and event[k].strip() for k in required)
        valid &= type(sequence) is int and sequence > 0
        valid &= isinstance(event.get('metadata'), dict)
        reasons = event.get('reason_codes')
        valid &= isinstance(reasons, list) and all(isinstance(x, str) for x in reasons)
        try:
            timestamp = datetime.fromisoformat(str(event.get('observed_at', '')).replace('Z', '+00:00'))
            valid &= timestamp.tzinfo is not None
        except ValueError:
            valid = False
        if not valid:
            flag('malformed_event', event, line, 'Required fields, timestamp, sequence or metadata are invalid.')
            continue
        if event['tenant_id'] != tenant_id:
            flag('tenant_mismatch', event, line, 'Obtain an export restricted to the requested tenant.')
            continue
        if event['event_id'] in seen_ids or sequence in seen_sequences:
            flag('duplicate_event', event, line, 'Resolve duplicate event IDs or sequence numbers before review.')
        seen_ids.add(event['event_id'])
        seen_sequences.add(sequence)
        if previous is not None and sequence != previous + 1:
            flag('sequence_discontinuity', event, line, 'Export is reordered or has a gap; obtain the missing range or explain filtering.')
        previous = sequence
        permit = event.get('permit_hash')
        relevant = event['action'] in {'permit.mint', 'github_merge.execute', 'github_merge.reconcile'}
        if permit is not None or relevant:
            if not isinstance(permit, str) or not re.fullmatch('[0-9a-f]{64}', permit):
                flag('missing_permit_binding', event, line, 'Obtain a valid permit hash for this lifecycle event.')
                continue
            grouped[permit].append((line, event))

    for permit, entries in grouped.items():
        mints, executions, reconciled_ids = [], {}, set()
        for line, event in entries:
            action, state = event['action'], event.get('state')
            if 'permit_replayed' in event['reason_codes']:
                flag('replay_attempt_recorded', event, line, 'Inspect the rejected attempt; this does not prove a duplicate effect.')
            if action == 'permit.mint':
                mints.append((line, event))
                if state != 'PERMITTED' or event['outcome'] != 'permitted':
                    flag('contradictory_mint', event, line, 'Mint action has inconsistent state or outcome.')
            elif action == 'github_merge.execute':
                executions[event['object_id']] = (line, event)
                status = event['metadata'].get('adapter_status')
                if state != 'CONSUMED' or status not in ('success', 'failed', 'unknown') or event['outcome'] not in ('success', 'failure'):
                    flag('incomplete_execution', event, line, 'Obtain the consumed execution record and adapter outcome.')
                if (event['outcome'] == 'success') != (status == 'success'):
                    flag('contradictory_execution', event, line, 'Reported outcome conflicts with adapter status.')
                if status != 'success':
                    flag('unresolved_execution', event, line, 'Inspect provider evidence; do not infer that no effect occurred or retry automatically.')
                if not mints:
                    flag('missing_prior_mint', event, line, 'Obtain an earlier mint event; this export may cover only part of the lifecycle.')
            elif action == 'github_merge.reconcile':
                execution_id = event['metadata'].get('execution_id')
                if isinstance(execution_id, str):
                    reconciled_ids.add(execution_id)
                bound = executions.get(execution_id) if isinstance(execution_id, str) else None
                if bound is None:
                    flag('missing_execution_binding', event, line, 'Reconciliation must reference a prior execution of this permit.')
                if state == 'RECONCILED':
                    if event['outcome'] != 'reconciled' or 'provider_outcome_confirmed' not in event['reason_codes']:
                        flag('contradictory_reconciliation', event, line, 'Reconciled state lacks consistent outcome and confirmation reason.')
                    if bound and bound[1]['metadata'].get('adapter_status') != 'success':
                        flag('conflicting_success_claims', event, line, 'Reconciliation claims success after an unresolved or failed adapter result; inspect raw observations.')
                else:
                    flag('unresolved_reconciliation', event, line, 'Obtain or review provider observations; reconciliation did not establish a success claim.')
            else:
                flag('unsupported_lifecycle_event', event, line, 'This permit-linked action is outside the implemented triage rules.')
        if len(mints) > 1:
            flag('multiple_mints', mints[-1][1], mints[-1][0], 'Resolve multiple mint events for the same permit hash.')
        execution_events = [(line, e) for line, e in entries if e['action'] == 'github_merge.execute']
        if len(execution_events) > 1:
            flag('multiple_execution_records', execution_events[-1][1], execution_events[-1][0], 'Inspect repeated execution records; they are not proof of multiple provider effects.')
        for execution_id, (line, event) in executions.items():
            if execution_id not in reconciled_ids:
                flag('missing_reconciliation', event, line, 'Obtain a reconciliation record linked to this execution.')
        if not executions:
            flag('no_execution_in_export', entries[0][1], entries[0][0], 'Permit may be unused; this export does not establish completed execution.')

    if not grouped:
        flag('no_reviewable_lifecycle', {}, None, 'No supported permit lifecycle was available to review.')
    return {'kind': 'proofrail.audit-review.v1', 'tenant_id': tenant_id,
            'status': 'NEEDS_REVIEW' if findings else 'NO_FINDINGS_IN_SUPPLIED_EVENTS',
            'event_count': count, 'permit_count': len(grouped), 'findings': findings,
            'authenticity': authenticity, 'hash_chain': chain,
            'authorization_proven': False,
            'provider_effect_proven': False,
            'limits': ['Audit claims only; inspect permits, policies and raw provider observations separately.',
                       'A consistent hash chain does not detect a full rewrite or tail truncation without an external anchor.',
                       'No completeness, freshness, independent observation or universal revocation guarantee.',
                       'No findings is not approval to execute, retry or certify an action.']}
