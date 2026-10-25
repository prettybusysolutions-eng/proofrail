"""Financial attacks on the simulated settlement. No money moves in any test."""
import pytest

from conftest import through_work
from records import PilotError
from fixtures import ALL_MET


def accepted_case(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    p.assess(w['qa-a'], 'tenant-a', pid)
    p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='clear')
    return pid, p, w, result['work_order_id']


def settle(env, pid, invoice):
    return env.p.settle(env.w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'] if invoice else None)


def test_duplicate_settlement_request(env):
    pid, p, w, wo = accepted_case(env)
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=wo, amount=30000)
    assert settle(env, pid, invoice)['authorization_status'] == 'SIMULATED_AUTHORIZED'
    again = settle(env, pid, invoice)
    assert again['authorization_status'] == 'DENIED' and again['duplicate_check_result'] == 'DUPLICATE'
    assert again['denial_reasons'] == ['duplicate_settlement']


def test_amount_above_the_approved_cap(env):
    pid, p, w, wo = accepted_case(env)
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=wo, amount=35001)
    assert settle(env, pid, invoice)['denial_reasons'] == ['amount_exceeds_approved_cap']


def test_invoice_for_a_different_work_order(env):
    pid, p, w, wo = accepted_case(env)
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id='WO-77777', amount=30000)
    assert settle(env, pid, invoice)['denial_reasons'] == ['invoice_for_other_work_order']


def test_rejected_outcome_cannot_be_accepted_or_paid(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria={'C1': 'not_met', 'C2': 'met'},
                        evidence_refs=w.inspection_refs())
    assert p.assess(w['qa-a'], 'tenant-a', pid)['assessment_state'] == 'REJECTED'
    with pytest.raises(PilotError) as exc:
        p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='pay anyway')
    assert exc.value.reason == 'outcome_not_verified'
    with pytest.raises(PilotError) as exc:            # no new inspections once the case is rejected
        p.submit_inspection(w['inspector2-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    assert exc.value.reason == 'transition_not_allowed'
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=30000)
    decision = settle(env, pid, invoice)
    assert decision['authorization_status'] == 'DENIED'
    assert decision['denial_reasons'] == ['outcome_not_verified', 'outcome_previously_rejected_or_disputed',
                                          'buyer_acceptance_missing']


def test_later_verified_verdict_does_not_override_an_earlier_rejection(env):
    """Rule-level: given a REJECTED then a VERIFIED verdict on file, settlement is denied."""
    import settlement_simulator
    pid, p, w, wo = accepted_case(env)
    verdict = [v for v in p.store.all('tenant-a', 'verdict') if v['work_order_id'] == wo][-1]
    rejected = w['qa-a'].sign({**{k: v for k, v in verdict.items() if k not in ('record_hash', 'signature')},
                               'outcome_id': 'out-earlier', 'assessment_state': 'REJECTED'})
    authority = p._authority_for('tenant-a', pid)
    approval = p.store.all('tenant-a', 'approval')[0]
    acceptance = p.store.all('tenant-a', 'acceptance')[-1]
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=wo, amount=30000)
    decision = settlement_simulator.decide(
        w['finance-a'], registry=p.registry, store=p.store, tenant_id='tenant-a', work_order_id=wo,
        verdicts=[rejected, verdict], acceptance=acceptance, invoice=invoice, approval=approval, authority=authority,
        provider_organization='clearpath-facility-services', contractors=set(), now=w.clock.now(),
        current_order_matches=True)
    assert decision['denial_reasons'] == ['outcome_previously_rejected_or_disputed']


def test_settlement_before_buyer_acceptance(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    p.assess(w['qa-a'], 'tenant-a', pid)
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=30000)
    assert settle(env, pid, invoice)['denial_reasons'] == ['buyer_acceptance_missing']


def test_buyer_disputes_after_acceptance(env):
    pid, p, w, wo = accepted_case(env)
    p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='DISPUTED', reason='debris returned')
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=wo, amount=30000)
    decision = settle(env, pid, invoice)
    assert decision['denial_reasons'] == ['buyer_disputed'] and decision['dispute_status'] == 'DISPUTED'


def test_currency_mismatch(env):
    pid, p, w, wo = accepted_case(env)
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=wo, amount=30000, currency='EUR')
    assert settle(env, pid, invoice)['denial_reasons'] == ['currency_mismatch']


def test_forged_invoice(env):
    pid, p, w, wo = accepted_case(env)
    genuine = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=wo, amount=30000)
    forged = {**genuine, 'amount': 34000}                     # altered after the provider signed it
    p.store.put('tenant-a', 'invoice', forged['invoice_id'], forged, replace=True)
    assert settle(env, pid, forged)['denial_reasons'] == ['invoice_signature_invalid']


def test_invoice_from_someone_other_than_the_provider(env):
    pid, p, w, wo = accepted_case(env)
    outsider = p.registry.add('billing-x', tenant_id='tenant-a', organization='other-vendor', roles={'provider'})
    invoice = p.submit_invoice(outsider, 'tenant-a', work_order_id=wo, amount=30000)
    assert settle(env, pid, invoice)['denial_reasons'] == ['invoice_not_from_approved_provider']


def test_no_invoice(env):
    pid, p, w, wo = accepted_case(env)
    assert settle(env, pid, None)['denial_reasons'] == ['invoice_missing']


def test_reviewer_cannot_also_authorize_settlement(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    dual = p.registry.add('qa-finance-a', tenant_id='tenant-a', organization='northside-logistics',
                          roles={'settlement_authorizer', 'outcome_reviewer'})
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    assert p.assess(dual, 'tenant-a', pid)['assessment_state'] == 'VERIFIED'
    p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='clear')
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=30000)
    decision = p.settle(dual, 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    assert decision['denial_reasons'] == ['authorizer_not_independent']


def test_replayed_settlement_authorization_after_close(env):
    pid, p, w, wo = accepted_case(env)
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=wo, amount=30000)
    first = settle(env, pid, invoice)
    assert first['authorization_status'] == 'SIMULATED_AUTHORIZED' and p.store.state('tenant-a', pid) == 'CLOSED'
    second = p.settle(w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    assert second['denial_reasons'] == ['duplicate_settlement']
    authorized = [s for s in p.store.all('tenant-a', 'settlement') if s['authorization_status'] == 'SIMULATED_AUTHORIZED']
    assert len(authorized) == 1 and all(s['money_moved'] is False for s in p.store.all('tenant-a', 'settlement'))
