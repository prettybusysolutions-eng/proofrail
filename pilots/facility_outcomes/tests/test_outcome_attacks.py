"""Outcome attacks: a physical result becomes VERIFIED only from qualified, independent inspection."""
from datetime import timedelta

import pytest

from conftest import through_work
from fixtures import ALL_MET, evidence
from records import PilotError


def case(env):
    problem, plan, approval, envelope, result = through_work(env)
    return problem['problem_id'], env.p, env.w


def excluded_reasons(verdict):
    return [x['reason'] for x in verdict['excluded_observations']]


def test_contractor_self_certification_alone_is_insufficient(env):
    pid, p, w = case(env)
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verdict['assessment_state'] == 'INSUFFICIENT_EVIDENCE'
    assert excluded_reasons(verdict) == ['performer_claim_is_not_outcome_evidence']


def test_photo_from_a_different_facility(env):
    pid, p, w = case(env)
    refs = [evidence('elsewhere', facility='FAC-Z9', area='ZONE-STAGING-3', captured_at=w.clock.now(), by='inspector-a')]
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=refs)
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verdict['assessment_state'] == 'INSUFFICIENT_EVIDENCE'
    assert 'evidence_location_mismatch' in excluded_reasons(verdict)


def test_old_photo_reused_from_the_problem_report(env):
    pid, p, w = case(env)
    report_refs = p.store.get('tenant-a', 'problem', pid)['evidence_refs']
    reused = [{**report_refs[0], 'captured_at': w.clock.text()}]      # same file, new timestamp claimed
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=reused)
    assert 'evidence_reused_from_problem_report' in excluded_reasons(p.assess(w['qa-a'], 'tenant-a', pid))


def test_photo_captured_before_the_work_order_existed(env):
    pid, p, w = case(env)
    refs = [evidence('early', facility='FAC-A1', area='ZONE-STAGING-3',
                     captured_at=w.clock.now() - timedelta(hours=10), by='inspector-a')]
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=refs)
    assert 'evidence_predates_work_order' in excluded_reasons(p.assess(w['qa-a'], 'tenant-a', pid))


def test_inspector_not_designated_by_the_buyer(env):
    pid, p, w = case(env)
    stranger = p.registry.add('stranger-a', tenant_id='tenant-a', organization='unknown-co', roles={'inspector'})
    p.submit_inspection(stranger, 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    assert 'inspector_not_designated_by_buyer' in excluded_reasons(p.assess(w['qa-a'], 'tenant-a', pid))


def test_inspector_employed_by_the_provider(env):
    pid, p, w = case(env)
    p.submit_inspection(w['provider-inspector-a'], 'tenant-a', pid, criteria=ALL_MET,
                        evidence_refs=w.inspection_refs())
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verdict['assessment_state'] == 'INSUFFICIENT_EVIDENCE'
    assert 'inspector_not_independent_of_performer' in excluded_reasons(verdict)


def test_inspection_signed_by_an_unregistered_key(env):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from records import Identity
    pid, p, w = case(env)
    genuine = w['inspector-a']
    impostor = Identity(genuine.principal, Ed25519PrivateKey.generate())   # claims the inspector's identity
    p.submit_inspection(impostor, 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    assert 'signature_invalid' in excluded_reasons(p.assess(w['qa-a'], 'tenant-a', pid))


def test_performer_cannot_be_the_reviewer(env):
    """A reviewer employed by the provider organisation is refused."""
    pid, p, w = case(env)
    insider = p.registry.add('qa-contractor-a', tenant_id='tenant-a', organization='clearpath-facility-services',
                             roles={'outcome_reviewer'})
    with pytest.raises(PilotError) as exc:
        p.assess(insider, 'tenant-a', pid)
    assert exc.value.reason == 'reviewer_not_independent_of_performer'


def test_signed_but_contradicted_by_another_qualified_inspection(env):
    pid, p, w = case(env)
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    w.clock.advance(minutes=20)
    p.submit_inspection(w['inspector2-a'], 'tenant-a', pid, criteria={'C1': 'not_met', 'C2': 'met'},
                        evidence_refs=w.inspection_refs(name='second-opinion'))
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verdict['assessment_state'] == 'DISPUTED'
    assert len(verdict['contradictory_observations']) == 2
    assert p.store.state('tenant-a', pid) == 'DISPUTED'


def test_acceptance_criteria_changed_after_work_began(env):
    pid, p, w = case(env)
    authority = p._authority_for('tenant-a', pid)
    plan_id = authority['envelope']['effect']['parameters']['plan_id']
    looser = [{'criterion_id': 'C1', 'description': 'Most debris removed', 'check': 'area_clear_of_debris'}]
    with pytest.raises(PilotError) as exc:
        p.amend_plan(w['planner-a'], 'tenant-a', plan_id, acceptance_criteria=looser)
    assert exc.value.reason == 'transition_not_allowed'      # scope is fixed once work exists
    plan = p.store.get('tenant-a', 'plan', plan_id)                    # tampered in storage instead
    p.store.put('tenant-a', 'plan', plan_id, {**plan, 'plan_digest': 'a' * 64}, replace=True)
    with pytest.raises(PilotError) as exc:
        p.assess(w['qa-a'], 'tenant-a', pid)
    assert exc.value.reason == 'acceptance_criteria_changed'


def test_inspection_after_the_allowed_window(env):
    pid, p, w = case(env)
    w.clock.advance(hours=48 + 24 + 1)       # completion window plus grace, plus one hour
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    assert 'inspection_after_allowed_window' in excluded_reasons(p.assess(w['qa-a'], 'tenant-a', pid))


def test_inspection_without_evidence(env):
    pid, p, w = case(env)
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=[])
    assert 'inspection_without_evidence' in excluded_reasons(p.assess(w['qa-a'], 'tenant-a', pid))


def test_inspection_about_another_work_order_is_not_used(env):
    pid, p, w = case(env)
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs(),
                        subject='WO-99999')
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verdict['assessment_state'] == 'INSUFFICIENT_EVIDENCE'


def test_insufficient_then_verified_is_progression_not_dispute(env):
    pid, p, w = case(env)
    first = p.assess(w['qa-a'], 'tenant-a', pid)
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    second_reviewer = p.registry.add('qa2-a', tenant_id='tenant-a', organization='northside-logistics',
                                     roles={'outcome_reviewer'})
    second = p.assess(second_reviewer, 'tenant-a', pid)
    assert (first['assessment_state'], second['assessment_state']) == ('INSUFFICIENT_EVIDENCE', 'VERIFIED')
    assert p.store.state('tenant-a', pid) == 'OUTCOME_REVIEW'


def test_reviewers_cannot_reach_different_verdicts_on_the_same_evidence(env):
    """Verdicts are computed from qualified observations, so reviewers agree; conflicts surface as DISPUTED."""
    pid, p, w = case(env)
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria={'C1': 'not_met', 'C2': 'met'},
                        evidence_refs=w.inspection_refs())
    other = p.registry.add('qa2-a', tenant_id='tenant-a', organization='northside-logistics', roles={'outcome_reviewer'})
    states = {p.assess(w['qa-a'], 'tenant-a', pid)['assessment_state'], p.assess(other, 'tenant-a', pid)['assessment_state']}
    assert states == {'REJECTED'}


def test_completion_claim_after_cancellation_is_refused(env):
    from conftest import approved
    problem, plan, approval, envelope = approved(env)
    env.p.cancel(env.w['admin-a'], 'tenant-a', problem['problem_id'])
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', envelope)
    assert exc.value.reason == 'state_root_changed' and env.count() == 0
    with pytest.raises(PilotError) as exc:
        env.p.claim_completion(env.w['contractor-a'], 'tenant-a', problem['problem_id'], evidence_refs=[])
    assert exc.value.reason == 'execution_not_reconciled'


def test_verdict_signature_and_limitations(env):
    from proofrail.crypto import verify_signature
    from records import decode_public
    pid, p, w = case(env)
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verify_signature(verdict, decode_public(w['qa-a'].principal.public_key))
    assert any('do not prove the physical condition' in text for text in verdict['confidence_limitations'])
