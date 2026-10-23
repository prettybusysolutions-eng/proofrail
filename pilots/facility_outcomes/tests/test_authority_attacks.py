"""Authority attacks: every refusal is pinned to its reason and leaves the provider untouched.

Envelopes minted here with the real issuer key but wrong contents model a buggy or
misused issuer: the gateway must still refuse them, because it recomputes the
expected effect and roots from the records instead of trusting the envelope.
"""
import copy
import json
import secrets
import subprocess
import sys
from datetime import timedelta

import pytest

from conftest import PILOT, approved
from fixtures import save_world
from proofrail.envelope import mint_action_authority_envelope
from proofrail_gateway import (ACTION_TYPE, ADAPTER_CONTRACT, current_roots, expected_parameters,
                               success_predicate, work_order_target)
from records import PilotError


def refused(env, envelope, tenant='tenant-a'):
    with pytest.raises(PilotError) as exc:
        env.p.admit(tenant, envelope)
    assert env.count() == 0, 'a refused admission reached the provider'
    return exc.value.reason


def mint(env, problem, plan, approval, *, signer=None, issuer_id=None, issuer_role='verifier', subject=None,
         params_edit=None, target=None, approval_digest=None, roots=None, predicate=None, now=None, nonce=None,
         trust=None, envelope_id='env-forged-0001'):
    w, p = env.w, env.p
    params = expected_parameters(problem, plan, approval, envelope_id)
    if params_edit:
        params_edit(params)
    signer = signer or w['issuer-a']
    return mint_action_authority_envelope(
        roots=roots or current_roots(p.store, p.registry, p.policy.root('tenant-a'), 'tenant-a', problem['problem_id'],
                                     plan['plan_id'], approval['approval_id']),
        approval_digest=approval_digest or approval['approval_digest'], action_type=ACTION_TYPE,
        target=target or work_order_target(params), parameters=params,
        subject_principal_id=subject or w['gateway-a'].principal.principal_id, subject_role='executor',
        issuer_principal_id=issuer_id or w['issuer-a'].principal.principal_id, issuer_role=issuer_role,
        adapter_contract=ADAPTER_CONTRACT,
        observation_contract={'name': 'wrn-provider-read', 'version': 'v1', 'minimum_confirmations': 1,
                              'success_predicate_digest': predicate or success_predicate(params)},
        nonce=nonce or secrets.token_hex(32), expires_at=w.clock.now() + timedelta(hours=1),
        private_key=signer.private_key, key_id=signer.principal.key_id, now=now or w.clock.now(),
        envelope_id=envelope_id, trust=trust)


def test_control_a_correctly_minted_envelope_is_admitted(env):
    problem, plan, approval, _ = approved(env)
    assert env.p.admit('tenant-a', mint(env, problem, plan, approval))['authority_state'] == 'RECONCILED'


def test_forged_issuer_with_another_key(env):
    problem, plan, approval, _ = approved(env)
    assert refused(env, mint(env, problem, plan, approval, signer=env.w['issuer-b'],
                             issuer_id='issuer-a')) == 'issuer_key_changed'


def test_forged_issuer_claiming_the_real_key_id(env):
    problem, plan, approval, _ = approved(env)
    forged = mint(env, problem, plan, approval, signer=env.w['issuer-b'], issuer_id='issuer-a')
    forged['signature']['key_id'] = env.w['issuer-a'].principal.key_id
    assert refused(env, forged) == 'invalid_envelope'


def test_altered_after_signing(env):
    problem, plan, approval, envelope = approved(env)
    tampered = copy.deepcopy(envelope)
    tampered['effect']['parameters']['max_cost'] = 99000
    assert refused(env, tampered) == 'invalid_envelope'


def test_issuer_role_other_than_verifier(env):
    problem, plan, approval, _ = approved(env)
    assert refused(env, mint(env, problem, plan, approval, issuer_role='governor')) == 'issuer_changed'


def test_envelope_from_another_tenants_issuer(env):
    problem, plan, approval, _ = approved(env)
    assert refused(env, mint(env, problem, plan, approval, signer=env.w['issuer-b'],
                             issuer_id='issuer-b')) == 'issuer_changed'


def test_subject_is_another_executor(env):
    problem, plan, approval, _ = approved(env)
    assert refused(env, mint(env, problem, plan, approval, subject='gateway-b')) == 'subject_changed'


@pytest.mark.parametrize('field,value,reason', [
    ('max_cost', 99000, 'parameters_changed'),
    ('provider_id', 'P-099', 'target_changed'),
    ('area_id', 'ZONE-DOCK-1', 'target_changed'),
    ('scope_revision', 7, 'parameters_changed'),
])
def test_validly_signed_but_wrong_effect(env, field, value, reason):
    problem, plan, approval, _ = approved(env)
    envelope = mint(env, problem, plan, approval, params_edit=lambda p: p.update({field: value}))
    assert refused(env, envelope) == reason


def test_validly_signed_wrong_target_string(env):
    problem, plan, approval, _ = approved(env)
    assert refused(env, mint(env, problem, plan, approval, target='workorder:P-014:tenant-a:FAC-A1:ZONE-X')) \
        == 'target_changed'


def test_validly_signed_other_approval_digest(env):
    problem, plan, approval, _ = approved(env)
    assert refused(env, mint(env, problem, plan, approval, approval_digest='f' * 64)) == 'approval_scope_changed'


@pytest.mark.parametrize('root', ['identity', 'evidence', 'policy', 'state'])
def test_validly_signed_with_a_wrong_root(env, root):
    problem, plan, approval, _ = approved(env)
    p = env.p
    roots = current_roots(p.store, p.registry, p.policy.root('tenant-a'), 'tenant-a', problem['problem_id'],
                          plan['plan_id'], approval['approval_id'])
    roots[root] = 'e' * 64
    assert refused(env, mint(env, problem, plan, approval, roots=roots)) == root + '_root_changed'


def test_success_predicate_changed(env):
    problem, plan, approval, _ = approved(env)
    assert refused(env, mint(env, problem, plan, approval, predicate='d' * 64)) == 'predicate_changed'


def test_issued_in_the_future(env):
    problem, plan, approval, _ = approved(env)
    early = mint(env, problem, plan, approval, now=env.w.clock.now() + timedelta(minutes=10))
    assert refused(env, early) == 'authority_not_yet_valid'


def test_checkpoint_bearing_authority_not_supported(env):
    problem, plan, approval, _ = approved(env)
    trust = {'replay_root': 'a' * 64, 'checkpoint_root': 'b' * 64, 'observation_root': 'c' * 64,
             'minimum_checkpoint_epoch': 0, 'monotonic_counter': 0}
    assert refused(env, mint(env, problem, plan, approval, trust=trust)) == 'checkpoint_authority_not_supported'


def test_expired(env):
    problem, plan, approval, envelope = approved(env)
    env.w.clock.advance(hours=2)
    assert refused(env, envelope) == 'permit_expired'


def test_evidence_changed_after_its_root_was_approved(env):
    problem, plan, approval, envelope = approved(env)
    stored = env.p.store.get('tenant-a', 'problem', problem['problem_id'])
    stored['evidence_refs'][0]['sha256'] = '0' * 64
    env.p.store.put('tenant-a', 'problem', problem['problem_id'], stored, replace=True)
    assert refused(env, envelope) == 'evidence_root_changed'


def test_policy_changed_after_issuance(env):
    problem, plan, approval, envelope = approved(env)
    doc = {k: v for k, v in env.p.policy.doc('tenant-a').items() if k != 'tenant_id'}
    env.p.policy.set('tenant-a', {**doc, 'max_work_order_cost': 40000})
    assert refused(env, envelope) == 'policy_root_changed'


def test_identity_changed_between_authorization_and_dispatch(env):
    problem, plan, approval, envelope = approved(env)
    env.p.registry.add('new-approver-a', tenant_id='tenant-a', organization='northside-logistics', roles={'approver'})
    assert refused(env, envelope) == 'identity_root_changed'


def test_state_drift_problem_revised(env):
    problem, plan, approval, envelope = approved(env)
    stored = env.p.store.get('tenant-a', 'problem', problem['problem_id'])
    env.p.store.put('tenant-a', 'problem', problem['problem_id'], {**stored, 'revision': stored['revision'] + 1},
                    replace=True)
    assert refused(env, envelope) == 'state_root_changed'


def test_revoked_before_issuance(env):
    problem = env.w.report()
    plan, approval = env.w.plan_and_approve(problem)
    env.p.revoke_approval(env.w['admin-a'], 'tenant-a', approval['approval_id'])
    with pytest.raises(PilotError) as exc:
        env.w.authorize(problem, plan, approval)
    assert exc.value.reason == 'approval_revoked'


def test_revoked_after_issuance(env):
    problem, plan, approval, envelope = approved(env)
    env.p.revoke_approval(env.w['admin-a'], 'tenant-a', approval['approval_id'])
    assert refused(env, envelope) == 'state_root_changed'


def test_revoked_during_admission_stops_the_provider_call(env, monkeypatch):
    """Revocation lands after verification but before the claim: authority is spent, no work order."""
    problem, plan, approval, envelope = approved(env)
    gateway = env.p.gateways['tenant-a']
    real = gateway._consume

    def revoke_then_consume(e):
        env.p.revoke_approval(env.w['admin-a'], 'tenant-a', approval['approval_id'])
        return real(e)
    monkeypatch.setattr(gateway, '_consume', revoke_then_consume)
    assert refused(env, envelope) == 'state_changed_during_admission'
    assert gateway.provider_calls == 0
    with pytest.raises(PilotError) as exc:
        env.p.reconcile('tenant-a', envelope['envelope_id'])
    assert exc.value.reason == 'admission_aborted_before_provider_call'


def test_duplicate_nonce_across_two_cases(env):
    p1, plan1, ap1, _ = approved(env)
    p2, plan2, ap2, _ = approved(env)
    nonce = secrets.token_hex(32)
    first = mint(env, p1, plan1, ap1, nonce=nonce, envelope_id='env-nonce-1')
    second = mint(env, p2, plan2, ap2, nonce=nonce, envelope_id='env-nonce-2')
    assert env.p.admit('tenant-a', first)['authority_state'] == 'RECONCILED'
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', second)
    assert exc.value.reason == 'permit_replayed' and env.count() == 1


def test_two_approved_envelopes_for_one_case(env):
    problem, plan, approval, first = approved(env)
    second = env.w.authorize(problem, plan, approval)
    assert env.p.admit('tenant-a', first)['authority_state'] == 'RECONCILED'
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', second)
    assert exc.value.reason == 'state_root_changed' and env.count() == 1


def test_replay_registry_rolled_back_alone(env):
    import shutil
    problem, plan, approval, envelope = approved(env)
    registry = env.p.replay_registry
    env.p.admit('tenant-a', mint(env, *approved(env)[:3], envelope_id='env-warmup'))   # registry exists
    backup = env.tmp / 'registry-backup.sqlite3'
    shutil.copy(registry, backup)
    env.p.admit('tenant-a', envelope)
    for suffix in ('', '-wal', '-shm'):
        (registry.parent / (registry.name + suffix)).unlink(missing_ok=True)
    shutil.copy(backup, registry)
    with pytest.raises(PilotError) as exc:
        env.p.admit('tenant-a', envelope)
    assert exc.value.reason == 'authority_already_admitted' and env.count() == 2


def test_concurrent_admission_from_two_processes(env):
    problem, plan, approval, envelope = approved(env)
    save_world(env.w, env.tmp / 'world.json')
    (env.tmp / 'envelope.json').write_text(json.dumps(envelope))
    procs = [subprocess.Popen([sys.executable, str(PILOT / 'worker.py'), '--world', str(env.tmp / 'world.json'),
                               '--provider', env.url, '--tenant', 'tenant-a', '--envelope', str(env.tmp / 'envelope.json'),
                               '--out', str(env.tmp / f'out{i}.json'), '--timeout', '2']) for i in (1, 2)]
    for proc in procs:
        assert proc.wait(60) == 0
    results = [json.loads((env.tmp / f'out{i}.json').read_text()) for i in (1, 2)]
    assert sorted(r['outcome'] for r in results) == ['admitted', 'refused'], results
    admitted = next(r for r in results if r['outcome'] == 'admitted')
    refusal = next(r for r in results if r['outcome'] == 'refused')
    assert admitted['authority_state'] == 'RECONCILED'
    # Whichever layer the loser reaches first: the registry claim, the business-store record,
    # or (if the winner already moved the work state) the state root.
    assert refusal['reason'] in ('permit_replayed', 'authority_already_admitted', 'state_root_changed')
    assert env.count() == 1


def test_another_tenants_identity_change_does_not_touch_this_tenants_authority(env):
    problem, plan, approval, envelope = approved(env)
    env.p.registry.add('new-approver-b', tenant_id='tenant-b', organization='harbor-distribution', roles={'approver'})
    assert env.p.admit('tenant-a', envelope)['authority_state'] == 'RECONCILED'
