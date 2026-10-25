"""Independent outcome verification: did the intervention produce the agreed condition?

This is a different question from execution reconciliation (did the authorized
digital action happen?). A RECONCILED work order says nothing about the physical
result, and a VERIFIED verdict says nothing about payment.

Only qualified inspections count. Each observation is either used or excluded
with a stated reason, and the verdict lists both. Signatures attribute an
inspection to the inspector's key; they do not prove the physical condition.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from records import Identity, PilotError, Registry, digest, require, utc, validate

LIMITATIONS = [
    'Signatures attribute each inspection to the registered key of its inspector; they do not prove the physical condition.',
    'Inspector independence is checked against registered organisations and roles, not verified institutionally.',
    'Evidence files are bound by digest; their content (for example a photograph) is not machine-interpreted.',
]


def _exclude(excluded: list, observation: dict, reason: str) -> None:
    excluded.append({'observation': observation['record_hash'], 'reason': reason})


def qualify_inspection(observation: dict, *, registry: Registry, tenant_id: str, plan: dict, work_order_id: str,
                       created_at, problem: dict, provider_organization: str, now) -> str | None:
    """Return None if the inspection qualifies, else the reason it is excluded."""
    try:
        inspector = registry.signer(observation, role='inspector', tenant_id=tenant_id)
    except PilotError as exc:
        return exc.reason
    if inspector.principal_id != observation['observer_principal']:
        return 'observer_identity_mismatch'
    if observation['observer_role'] != 'inspector' or observation['independence_class'] != 'buyer_designated_inspector':
        return 'not_an_independent_inspection'
    if not registry.designated(tenant_id, plan['target']['facility_id'], inspector.principal_id):
        return 'inspector_not_designated_by_buyer'
    if inspector.organization == provider_organization or inspector.roles & {'contractor', 'provider', 'gateway'}:
        return 'inspector_not_independent_of_performer'
    if observation['observed_subject'] != {'kind': 'work_order', 'id': work_order_id}:
        return 'observation_for_other_work_order'
    when = utc(observation['observation_time'])
    window_end = utc(plan['expected_completion_window']['end']) + timedelta(hours=plan.get('_grace_hours', 0))
    if when < created_at or when > now:
        return 'inspection_time_invalid'
    if when > window_end:
        return 'inspection_after_allowed_window'
    if observation['observation_digest'] != digest(observation['findings']):
        return 'observation_digest_mismatch'
    refs = observation['evidence_refs']
    if not refs:
        return 'inspection_without_evidence'
    reported = {e['sha256'] for e in problem['evidence_refs']}
    for ref in refs:
        if (ref['facility_id'], ref['area_id']) != (plan['target']['facility_id'], plan['target']['area_id']):
            return 'evidence_location_mismatch'
        captured = utc(ref['captured_at'])
        if captured < created_at or captured > when:
            return 'evidence_predates_work_order'
        if ref['sha256'] in reported:
            return 'evidence_reused_from_problem_report'
    return None


def assess(reviewer: Identity, *, registry: Registry, tenant_id: str, problem: dict, plan: dict,
           authority: dict, observations: list, provider_organization: str, contractors: set,
           grace_hours: int, policy_digest: str, now) -> dict:
    ref = authority['reference']
    require(ref['authority_state'] == 'RECONCILED', 'execution_not_reconciled')
    work_order_id = ref['provider_operation_reference']
    require(authority['envelope']['effect']['parameters']['plan_digest'] == plan['plan_digest'],
            'acceptance_criteria_changed')
    r = reviewer.principal
    require('outcome_reviewer' in r.roles and r.tenant_id == tenant_id, 'reviewer_not_permitted')
    require(r.organization != provider_organization and r.principal_id not in contractors,
            'reviewer_not_independent_of_performer')
    created_at = next((utc(o['observation_time']) for o in observations
                       if o['observation_type'] == 'provider_work_order_state'
                       and o['record_hash'] == ref['reconciliation_reference']), None)
    require(created_at is not None, 'reconciliation_observation_missing')
    plan_view = {**plan, '_grace_hours': grace_hours}
    excluded, qualified = [], []
    for obs in observations:
        if obs['observation_type'] == 'provider_work_order_state':
            continue   # execution evidence, not outcome evidence
        if obs['observation_type'] == 'completion_claim':
            _exclude(excluded, obs, 'performer_claim_is_not_outcome_evidence')
            continue
        reason = qualify_inspection(obs, registry=registry, tenant_id=tenant_id, plan=plan_view,
                                    work_order_id=work_order_id, created_at=created_at, problem=problem,
                                    provider_organization=provider_organization, now=now)
        if reason:
            _exclude(excluded, obs, reason)
        else:
            qualified.append(obs)
    results, supporting, contradicting = [], set(), set()
    for criterion in plan['acceptance_criteria']:
        cid = criterion['criterion_id']
        votes = [(o, o['findings'].get('criteria', {}).get(cid, 'unknown')) for o in qualified]
        met = [o['record_hash'] for o, v in votes if v == 'met']
        not_met = [o['record_hash'] for o, v in votes if v == 'not_met']
        if met and not_met:
            result = 'conflicting'
            contradicting.update(not_met + met)
        elif not_met:
            result = 'not_met'
            contradicting.update(not_met)
        elif met:
            result = 'met'
            supporting.update(met)
        else:
            result = 'no_qualified_evidence'
        results.append({'criterion_id': cid, 'result': result, 'observations': sorted(met + not_met)})
    outcomes = {x['result'] for x in results}
    if 'conflicting' in outcomes:
        state = 'DISPUTED'
    elif 'not_met' in outcomes:
        state = 'REJECTED'
    elif outcomes == {'met'}:
        state = 'VERIFIED'
    else:
        state = 'INSUFFICIENT_EVIDENCE'
    verdict = {'kind': 'wrn.outcome-verdict.v1', 'outcome_id': 'out-' + uuid.uuid4().hex[:16],
               'tenant_id': tenant_id, 'problem_id': problem['problem_id'], 'intervention_id': plan['plan_id'],
               'work_order_id': work_order_id, 'plan_digest': plan['plan_digest'],
               'assessment_policy_digest': policy_digest, 'assessment_time': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
               'assessment_state': state, 'criteria_results': results,
               'supporting_observations': sorted(supporting), 'contradictory_observations': sorted(contradicting),
               'excluded_observations': excluded, 'reviewer_principal': r.principal_id,
               'confidence_limitations': LIMITATIONS}
    signed = reviewer.sign(verdict)
    validate('outcome_verdict', signed)
    return signed
