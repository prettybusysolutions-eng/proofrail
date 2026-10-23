"""Tenant isolation, error hygiene, crash recovery and the documented joint-rollback limit."""
import json
import shutil
import subprocess
import sys

import pytest

from conftest import PILOT, approved, provider_count, through_work, wait_for_orders
from fixtures import ALL_MET, load_world, save_world
from records import PilotError
from store import verify_chain


# ------------------------------------------------------------------ isolation

def test_cross_tenant_read_looks_like_a_missing_record(env):
    problem, plan, approval, envelope = approved(env)
    for kind, rid in (('problem', problem['problem_id']), ('plan', plan['plan_id']),
                      ('approval', approval['approval_id'])):
        with pytest.raises(PilotError) as other:
            env.p.store.get('tenant-b', kind, rid)
        with pytest.raises(PilotError) as missing:
            env.p.store.get('tenant-b', kind, 'does-not-exist')
        assert other.value.reason == missing.value.reason == 'not_found'


def test_other_tenants_gateway_cannot_spend_this_tenants_authority(env):
    problem, plan, approval, envelope = approved(env)
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-b', envelope)
    assert exc.value.reason == 'tenant_mismatch' and env.count() == 0


@pytest.mark.parametrize('actor,step', [
    ('qa-b', 'assess'), ('contractor-b', 'claim'), ('inspector-b', 'inspect'), ('buyer-b', 'decide'),
    ('planner-b', 'amend'),
])
def test_cross_tenant_mutation_is_refused(env, actor, step):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    calls = {'assess': lambda: p.assess(w[actor], 'tenant-a', pid),
             'claim': lambda: p.claim_completion(w[actor], 'tenant-a', pid, evidence_refs=[]),
             'inspect': lambda: p.submit_inspection(w[actor], 'tenant-a', pid, criteria=ALL_MET,
                                                    evidence_refs=w.inspection_refs()),
             'decide': lambda: p.buyer_decide(w[actor], 'tenant-a', pid, decision='DISPUTED', reason='x'),
             'amend': lambda: p.amend_plan(w[actor], 'tenant-a', plan['plan_id'], estimated_cost=1)}
    with pytest.raises(PilotError) as exc:
        calls[step]()
    assert exc.value.reason in ('actor_tenant_mismatch', 'signer_tenant_mismatch')


def test_refusals_carry_reason_codes_only(env):
    problem, plan, approval, envelope = approved(env)
    tampered = {**envelope, 'nonce': 'n' * 64}
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', tampered)
    assert str(exc.value) == exc.value.reason == 'invalid_envelope'
    assert envelope['nonce'] not in str(exc.value) and 'tenant' not in str(exc.value)


# ------------------------------------------------------------------ recovery

def test_gateway_process_dies_while_the_provider_call_is_in_flight(env):
    problem, plan, approval, envelope = approved(env)
    save_world(env.w, env.tmp / 'world.json')
    (env.tmp / 'envelope.json').write_text(json.dumps(envelope))
    env.arm('timeout_after_accept', 30)
    worker = subprocess.Popen([sys.executable, str(PILOT / 'worker.py'), '--world', str(env.tmp / 'world.json'),
                               '--provider', env.url, '--tenant', 'tenant-a',
                               '--envelope', str(env.tmp / 'envelope.json'), '--out', str(env.tmp / 'out.json'),
                               '--timeout', '30'])
    wait_for_orders(env.url, 1)                               # the call reached the provider
    worker.kill()                                             # the gateway process dies mid-call
    worker.wait()
    assert not (env.tmp / 'out.json').exists()
    restarted = load_world(env.tmp / 'world.json', env.url, provider_timeout=1.0)
    stored = restarted.pilot.store.get('tenant-a', 'authority', envelope['envelope_id'])
    assert stored['reference']['authority_state'] == 'CONSUMED'      # written before the call
    resolved = restarted.pilot.reconcile('tenant-a', envelope['envelope_id'])
    assert resolved['authority_state'] == 'RECONCILED'
    with pytest.raises(PilotError) as exc:
        restarted.pilot.admit('tenant-a', envelope)
    assert exc.value.reason == 'permit_replayed'
    assert restarted.pilot.gateways['tenant-a'].provider_calls == 0 and provider_count(env.url) == 1


def test_replay_registry_missing_entirely(env):
    problem, plan, approval, envelope = approved(env)
    env.p.admit('tenant-a', envelope)
    registry = env.p.replay_registry
    for suffix in ('', '-wal', '-shm'):
        (registry.parent / (registry.name + suffix)).unlink(missing_ok=True)
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', envelope)
    assert exc.value.reason == 'authority_already_admitted' and env.count() == 1


def test_joint_rollback_of_registry_and_business_store_is_a_known_limit(env):
    """LIMITATION (docs/WRN_THREAT_MODEL.md): restoring BOTH stores from before admission lets the
    gateway call the provider a second time. What still holds: the provider's idempotency key is the
    envelope hash, so no second order is created, and reconciliation confirms the single order."""
    problem, plan, approval, envelope = approved(env)
    backup = env.tmp / 'backup'
    shutil.copytree(env.p.workdir, backup)
    env.p.admit('tenant-a', envelope)
    shutil.rmtree(env.p.workdir)
    shutil.copytree(backup, env.p.workdir)
    second = env.p.admit('tenant-a', envelope)
    assert env.p.gateways['tenant-a'].provider_calls == 2          # the limit: a second call is made
    assert env.count() == 1                                         # the backstop: provider idempotency
    assert second['authority_state'] == 'RECONCILED'


def test_audit_chain_detects_edits_but_not_tail_truncation(env):
    through_work(env)
    entries = env.p.store.audit_entries('tenant-a')
    assert verify_chain(entries)
    edited = json.loads(json.dumps(entries))
    edited[1]['detail']['actor'] = 'someone-else'
    assert not verify_chain(edited)
    assert verify_chain(entries[:-2])    # LIMITATION: a truncated tail still verifies without a checkpoint


def test_observer_unavailable_keeps_the_outcome_unknown(env, monkeypatch):
    problem, plan, approval, envelope = approved(env)
    observer = env.p.gateways['tenant-a'].observer
    monkeypatch.setattr(observer.client, 'call', lambda *a, **k: (_ for _ in ()).throw(PilotError('provider_outcome_unknown')))
    result = env.p.admit('tenant-a', envelope)
    assert result['authority_state'] == 'EXECUTION_UNKNOWN' and result['reason'] == 'provider_unreadable'
