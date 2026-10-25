"""Adapter attacks: a provider response never establishes the authorized effect on its own.

Lesson carried from evidence/live-github-2026-10-19: GitHub answered success for a
merge another head had already made. Here every provider misbehaviour mode is
driven against the real simulator process, and side effects are counted from the
provider's own ground-truth endpoint.
"""
import json
import sqlite3
from contextlib import closing

import pytest

from conftest import approved, set_status
from records import PilotError


def test_success_response_for_a_different_operation_is_not_attribution(env):
    """The provider creates nothing and answers 201 naming some other order."""
    other_problem, other_plan, other_approval, other = approved(env)
    env.p.admit('tenant-a', other)                         # an unrelated, real order exists
    problem, plan, approval, envelope = approved(env)
    env.arm('wrong_operation_success')
    result = env.p.admit('tenant-a', envelope)
    assert result['provider_outcome'] == 'claimed_success'
    assert result['authority_state'] == 'RECONCILIATION_FAILED'
    assert result['reason'] == 'provider_success_not_observed'
    assert env.count() == 1                                 # only the unrelated order exists
    assert env.p.store.state('tenant-a', problem['problem_id']) == 'WORK_ORDER_PENDING'


def test_fabricated_success_with_no_orders_at_all(env):
    problem, plan, approval, envelope = approved(env)
    env.arm('wrong_operation_success')
    result = env.p.admit('tenant-a', envelope)
    assert result['authority_state'] == 'RECONCILIATION_FAILED' and env.count() == 0


def test_malformed_success_body_is_resolved_only_by_observation(env):
    problem, plan, approval, envelope = approved(env)
    env.arm('malformed')
    result = env.p.admit('tenant-a', envelope)
    assert result['provider_outcome'] == 'provider_outcome_unknown'
    assert result['authority_state'] == 'RECONCILED' and env.count() == 1


def test_response_naming_another_tenant(env):
    problem, plan, approval, envelope = approved(env)
    env.arm('other_tenant_response')
    result = env.p.admit('tenant-a', envelope)
    assert result['authority_state'] == 'RECONCILIATION_FAILED'
    assert result['reason'] == 'provider_response_inconsistent_with_observation'


def test_order_stored_with_different_parameters_is_not_reconciled(env, monkeypatch):
    """The provider stores a cheaper-looking variant of the request: observation must not accept it."""
    problem, plan, approval, envelope = approved(env)
    gateway = env.p.gateways['tenant-a']
    real = gateway.provider.call

    def altered(method, path, body=None, headers=None):
        if method == 'POST':
            body = {**body, 'max_cost': body['max_cost'] + 5000}
        return real(method, path, body, headers)
    monkeypatch.setattr(gateway.provider, 'call', altered)
    result = env.p.admit('tenant-a', envelope)
    assert result['authority_state'] == 'RECONCILIATION_FAILED'
    assert result['reason'] == 'work_order_differs_from_authorized_effect'


def test_provider_record_changed_after_reconciliation_blocks_settlement(env):
    """The provider's stored order is altered after it was reconciled: settlement must not proceed."""
    from conftest import through_work
    from fixtures import ALL_MET
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    p.assess(w['qa-a'], 'tenant-a', pid)
    p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='clear')
    with closing(sqlite3.connect(env.tmp / 'provider' / 'provider.sqlite3')) as db:
        body = json.loads(db.execute('SELECT body FROM orders').fetchone()[0])
        db.execute('UPDATE orders SET body=?', (json.dumps({**body, 'area_id': 'ZONE-OTHER'}),))
        db.commit()
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=32000)
    decision = p.settle(w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    assert decision['authorization_status'] == 'DENIED'
    assert decision['denial_reasons'] == ['work_order_changed_since_reconciliation']
    assert p.store.state('tenant-a', pid) == 'ACCEPTED'      # not closed


def test_provider_without_idempotency_duplicates_are_detected(env, monkeypatch):
    """Provider ignores Idempotency-Key. Even if a create were sent twice, observation flags duplicates."""
    problem, plan, approval, envelope = approved(env)
    env.arm('no_idempotency')
    gateway = env.p.gateways['tenant-a']
    real = gateway.provider.call

    def twice(method, path, body=None, headers=None):
        if method == 'POST':
            real(method, path, body, headers)               # a duplicate the gateway itself never sends
        return real(method, path, body, headers)
    monkeypatch.setattr(gateway.provider, 'call', twice)
    result = env.p.admit('tenant-a', envelope)
    assert env.count() == 2
    assert result['authority_state'] == 'RECONCILIATION_FAILED' and result['reason'] == 'duplicate_work_orders'


def test_status_changing_between_reads_does_not_flip_reconciliation(env):
    problem, plan, approval, envelope = approved(env)
    env.arm('status_flap')
    result = env.p.admit('tenant-a', envelope)
    assert result['authority_state'] == 'RECONCILED'
    set_status(env.url, 'tenant-a', result['work_order_id'], 'in_progress')
    with pytest.raises(PilotError) as exc:
        env.p.reconcile('tenant-a', envelope['envelope_id'])
    assert exc.value.reason == 'reconciliation_not_pending'   # a reconciled authority is not re-decided


def test_provider_unreadable_after_create_is_unknown_not_success(env, monkeypatch):
    problem, plan, approval, envelope = approved(env)
    observer = env.p.gateways['tenant-a'].observer
    real = observer.client.call
    monkeypatch.setattr(observer.client, 'call', lambda *a, **k: (500, None))
    result = env.p.admit('tenant-a', envelope)
    assert result['provider_outcome'] == 'claimed_success'
    assert result['authority_state'] == 'EXECUTION_UNKNOWN' and result['reason'] == 'provider_unreadable'
    monkeypatch.setattr(observer.client, 'call', real)
    assert env.p.reconcile('tenant-a', envelope['envelope_id'])['authority_state'] == 'RECONCILED'
    assert env.count() == 1


def test_provider_origin_is_fixed(env):
    from proofrail_gateway import ProviderClient
    with pytest.raises(PilotError) as exc:
        ProviderClient('http://attacker.example', 'x')
    assert exc.value.reason == 'provider_origin'


def test_provider_errors_expose_no_detail(env):
    from proofrail_gateway import ProviderClient
    client = ProviderClient('http://127.0.0.1:9', 'gateway-a', timeout=0.5)   # nothing listens on port 9
    with pytest.raises(PilotError) as exc:
        client.call('POST', '/v1/tenants/tenant-a/work-orders', {'secret': 'value'})
    assert str(exc.value) == 'provider_outcome_unknown' and exc.value.__cause__ is None
