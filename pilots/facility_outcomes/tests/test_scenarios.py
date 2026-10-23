"""Handoff demonstrations A-E. Each asserts the separated claims, not one success flag."""
from conftest import approved, through_work

from fixtures import ALL_MET, save_world, load_world
from records import PilotError
from store import verify_chain

import pytest


def test_A_authorized_success_keeps_every_claim_separate(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    assert result['authority_state'] == 'RECONCILED' and result['reason'] == 'observed_exact_effect'
    assert env.count() == 1
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verdict['assessment_state'] == 'VERIFIED'
    # The contractor's own claim was considered and excluded, not counted.
    assert [x['reason'] for x in verdict['excluded_observations']] == ['performer_claim_is_not_outcome_evidence']
    assert p.store.state('tenant-a', pid) == 'OUTCOME_REVIEW'          # verified is not accepted
    acceptance = p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='Zone clear')
    assert acceptance['outcome_digest'] == verdict['record_hash']
    assert p.store.state('tenant-a', pid) == 'ACCEPTED'                # accepted is not paid
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=32000)
    decision = p.settle(w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    assert decision['authorization_status'] == 'SIMULATED_AUTHORIZED' and decision['money_moved'] is False
    assert decision['approved_amount'] == 32000 and decision['denial_reasons'] == []
    assert p.store.state('tenant-a', pid) == 'CLOSED'
    learning = p.learning_record('tenant-a', pid, area_type='staging_zone', debris_volume_class='medium',
                                 shareable=True)
    assert learning['causal_claim'] == 'none' and 'tenant-a' not in str(learning)
    assert verify_chain(p.store.audit_entries('tenant-a'))
    assert env.count() == 1


@pytest.mark.parametrize('change', ['quote', 'provider', 'area', 'cost_cap'])
def test_B_changed_scope_rejects_the_original_authority(env, change):
    problem, plan, approval, envelope = approved(env)
    p, w = env.p, env.w
    if change == 'quote':
        p.amend_plan(w['planner-a'], 'tenant-a', plan['plan_id'], estimated_cost=34000)
    elif change == 'provider':
        p.amend_plan(w['planner-a'], 'tenant-a', plan['plan_id'], provider_id='P-099')
    elif change == 'area':
        p.amend_plan(w['planner-a'], 'tenant-a', plan['plan_id'],
                     target={**plan['target'], 'area_id': 'ZONE-DOCK-1'})
    else:  # re-approved with a different cost cap: the original envelope names the old approval
        p.amend_plan(w['planner-a'], 'tenant-a', plan['plan_id'], estimated_cost=plan['estimated_cost'])
        p.approve(w['approver-a'], 'tenant-a', plan['plan_id'], maximum_cost=45000)
    with pytest.raises(PilotError) as exc:
        p.admit('tenant-a', envelope)
    # The state root binds the plan digest and the work state, so it is the layer that refuses.
    assert exc.value.reason == 'state_root_changed'
    assert env.count() == 0


def test_C_replay_creates_no_second_work_order_including_after_restart(env):
    problem, plan, approval, envelope = approved(env)
    save_world(env.w, env.tmp / 'world.json')
    assert env.p.admit('tenant-a', envelope)['authority_state'] == 'RECONCILED'
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', envelope)
    assert exc.value.reason == 'permit_replayed'
    restarted = load_world(env.tmp / 'world.json', env.url, provider_timeout=1.0)
    with pytest.raises(PilotError) as exc:
        restarted.pilot.admit('tenant-a', envelope)
    assert exc.value.reason == 'permit_replayed'
    assert env.count() == 1


def test_D_false_completion_never_becomes_a_verified_outcome(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    claim_only = p.assess(w['qa-a'], 'tenant-a', pid)
    assert claim_only['assessment_state'] == 'INSUFFICIENT_EVIDENCE'
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria={'C1': 'not_met', 'C2': 'met'},
                        evidence_refs=w.inspection_refs())
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    assert verdict['assessment_state'] == 'REJECTED'
    # The execution record stays valid: the digital action did happen as authorized.
    assert p.store.get('tenant-a', 'authority', envelope['envelope_id'])['reference']['authority_state'] == 'RECONCILED'
    with pytest.raises(PilotError) as exc:
        p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='claimed done')
    assert exc.value.reason == 'outcome_not_verified'
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=32000)
    decision = p.settle(w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    assert decision['authorization_status'] == 'DENIED' and 'outcome_not_verified' in decision['denial_reasons']


def test_E1_timeout_after_the_provider_stored_the_order(env):
    """The response is lost, but an independent read finds the exact order: reconciled from observation."""
    problem, plan, approval, envelope = approved(env)
    gateway = env.p.gateways['tenant-a']
    env.arm('timeout_after_accept', 3)
    result = env.p.admit('tenant-a', envelope)
    assert result['provider_outcome'] == 'provider_outcome_unknown'
    assert result['authority_state'] == 'RECONCILED' and result['reason'] == 'observed_exact_effect'
    assert gateway.provider_calls == 1 and env.count() == 1
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', envelope)
    assert exc.value.reason == 'permit_replayed'
    assert env.count() == 1


def test_E2_connection_dropped_before_any_effect_stays_unknown_and_is_not_retried(env):
    problem, plan, approval, envelope = approved(env)
    gateway = env.p.gateways['tenant-a']
    env.arm('drop_without_effect')
    result = env.p.admit('tenant-a', envelope)
    assert result['authority_state'] == 'EXECUTION_UNKNOWN' and result['reason'] == 'not_yet_observed'
    again = env.p.reconcile('tenant-a', envelope['envelope_id'])
    assert again['authority_state'] == 'EXECUTION_UNKNOWN'
    assert gateway.provider_calls == 1 and env.count() == 0     # one attempt, never repeated
    with pytest.raises(PilotError):
        env.p.admit('tenant-a', envelope)
    assert env.p.store.state('tenant-a', problem['problem_id']) == 'WORK_ORDER_PENDING'


def test_E3_provider_dies_after_accepting_then_confirms_after_restart(env):
    """Unknown while the provider is unreadable; read-only recovery confirms once it is back."""
    import threading, time
    from conftest import provider_count
    from fixtures import start_provider
    problem, plan, approval, envelope = approved(env)
    gateway = env.p.gateways['tenant-a']
    port = int(env.url.rsplit(':', 1)[1])
    env.arm('timeout_after_accept', 30)
    box = {}
    worker = threading.Thread(target=lambda: box.update(r=env.p.admit('tenant-a', envelope)))
    worker.start()
    for _ in range(100):
        if provider_count(env.url) == 1:
            break
        time.sleep(0.02)
    env.proc.kill()                                                    # this provider process dies mid-request
    env.proc.wait()
    worker.join(30)
    assert box['r']['authority_state'] == 'EXECUTION_UNKNOWN' and box['r']['reason'] == 'provider_unreadable'
    proc, url = start_provider(env.tmp / 'provider', port=port)          # same store, same address
    try:
        resolved = env.p.reconcile('tenant-a', envelope['envelope_id'])
        assert resolved['authority_state'] == 'RECONCILED'
        assert gateway.provider_calls == 1 and provider_count(url) == 1
    finally:
        proc.kill()
