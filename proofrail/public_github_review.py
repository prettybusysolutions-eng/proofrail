"""Review public provider observations without inventing permit authority."""
from collections import Counter
from datetime import datetime
import re

from .core import ProofRailError


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('missing timezone')
        return parsed
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProofRailError('Invalid public snapshot timestamp') from exc


def review_public_snapshot(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('schema') != 'proofrail.public-github-snapshot.v1':
        raise ProofRailError('Unsupported public snapshot format')
    cases = snapshot.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ProofRailError('Snapshot requires public cases')
    reports, seen = [], set()
    for case in cases:
        try:
            case_id, pull = case['case_id'], case['pull']
            if not isinstance(case_id, str) or case_id in seen:
                raise ValueError('duplicate or invalid case ID')
            seen.add(case_id)
            if case_id != f"{case['repository']}#{pull['number']}":
                raise ValueError('case identity does not match repository and PR')
            if type(pull['merged']) is not bool or pull['state'] not in ('open', 'closed'):
                raise ValueError('invalid merge/state fields')
            if not re.fullmatch('[0-9a-f]{40,64}', pull['head_sha']):
                raise ValueError('invalid head SHA')
            if not isinstance(case['reviews'], list) or not isinstance(case['runs'], list):
                raise ValueError('invalid review/run lists')
            if not isinstance(case['coverage'], dict) or not isinstance(case['sources'], dict):
                raise ValueError('missing coverage/source metadata')
            for source in ('pull', 'reviews', 'runs'):
                if not isinstance(case['sources'].get(source), str):
                    raise ValueError('missing source URL')
            _time(case['retrieved_at'])
            created = _time(pull['created_at'])
            if pull['merged']:
                if pull['state'] != 'closed' or not re.fullmatch('[0-9a-f]{40,64}', pull['merge_commit_sha']):
                    raise ValueError('merged state lacks a closed PR and commit')
                if _time(pull['merged_at']) < created:
                    raise ValueError('merge precedes creation')
            elif pull.get('merged_at') is not None:
                raise ValueError('unmerged PR has merge timestamp')
            if pull['state'] == 'closed' and _time(pull['closed_at']) < created:
                raise ValueError('close precedes creation')
            latest_reviews = {}
            for review in case['reviews']:
                key = review['reviewer']
                if not isinstance(key, str) or review['state'] not in ('APPROVED', 'CHANGES_REQUESTED', 'COMMENTED', 'DISMISSED', 'PENDING'):
                    raise ValueError('invalid review record')
                # Comments do not cancel an earlier approval/request for changes.
                if review['state'] in ('COMMENTED', 'PENDING'):
                    continue
                timestamp = _time(review['submitted_at'])
                if type(review['id']) is not int or not isinstance(review['commit_id'], str):
                    raise ValueError('invalid submitted review binding')
                old = latest_reviews.get(key)
                if old is None or (timestamp, review['id']) > (_time(old['submitted_at']), old['id']):
                    latest_reviews[key] = review
            approvals = [r for r in latest_reviews.values() if r['state'] == 'APPROVED']
            current_approvals = [r for r in approvals if r['commit_id'] == pull['head_sha']]
            latest_runs = {}
            for run in case['runs']:
                if run['head_sha'] != pull['head_sha']:
                    raise ValueError('workflow belongs to another head')
                if type(run['id']) is not int or type(run['workflow_id']) is not int or type(run['run_attempt']) is not int:
                    raise ValueError('invalid workflow identifiers')
                if not isinstance(run['event'], str) or not isinstance(run['status'], str) or (run['conclusion'] is not None and not isinstance(run['conclusion'], str)):
                    raise ValueError('invalid workflow status')
                rank = (_time(run['created_at']), run['id'], run['run_attempt'])
                key = (run['workflow_id'], run['event'])
                if key not in latest_runs or rank > latest_runs[key][0]:
                    latest_runs[key] = (rank, run)
            selected = [item[1] for item in latest_runs.values()]
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ProofRailError(f'Malformed public case: {case.get("case_id") if isinstance(case, dict) else "unknown"}: {exc}') from exc
        questions = []
        if not current_approvals:
            questions.append('No current-head approval observed; required approvals and bypass rules are unknown.')
        if not selected:
            questions.append('No retained Actions runs returned for this head; this does not establish that CI never ran.')
        unsuccessful = [r['id'] for r in selected if r['status'] != 'completed' or r['conclusion'] not in ('success', 'neutral', 'skipped')]
        if unsuccessful:
            questions.append('Inspect selected non-success or unfinished runs; their requiredness and merge-time state are unknown.')
        if case['coverage'].get('runs_truncated') or case['coverage'].get('reviews_possibly_truncated') or case['coverage'].get('errors'):
            questions.append('Snapshot coverage is incomplete; retrieve missing pages or failed resources.')
        reports.append({'case_id': case_id, 'source': case['sources']['pull'],
                        'provider_state': 'MERGED_RECORDED' if pull['merged'] else 'CLOSED_UNMERGED' if pull['state'] == 'closed' else 'OPEN',
                        'head_sha': pull['head_sha'], 'merge_commit_sha': pull.get('merge_commit_sha'),
                        'review_records': len(case['reviews']),
                        'latest_current_head_approvals': len(current_approvals),
                        'latest_other_head_approvals': len(approvals) - len(current_approvals),
                        'selected_workflow_runs': [r['id'] for r in selected],
                        'non_success_or_unfinished_run_ids': unsuccessful,
                        'questions': questions, 'authorization': 'NOT_ESTABLISHED',
                        'source_authenticity': 'NOT_CRYPTOGRAPHICALLY_VERIFIED'})
    return {'kind': 'proofrail.public-github-review.v1', 'case_count': len(reports),
            'provider_states': dict(Counter(r['provider_state'] for r in reports)), 'cases': reports,
            'limits': ['Public API snapshots are provider observations, not ProofRail permits or organization audit logs.',
                       'No historic policy, required-check, bypass, actor-causation or universal revocation determination.',
                       'Latest retrieved reviews/runs may differ from merge-time state; Actions coverage excludes external status providers.',
                       'No human review-time or commercial validation is measured.']}
