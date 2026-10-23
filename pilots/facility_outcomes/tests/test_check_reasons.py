"""One test per pilot check that no earlier test enforced on its own.

review_tools/mutate_checks.py removed each check in turn: 66 of 107 left the suite
green, because boundary tests are refused by whichever layer fires first (usually
the state root or a signature). Each test here builds the exact input one check
exists to reject, re-signing or re-digesting where an earlier check would
otherwise stop it, and asserts that check's reason.
"""
import copy
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import outcome_verifier
import settlement_simulator
from conftest import approved, through_work
from evidence_export import _claim, export_case
from fixtures import ALL_MET
from policy import approval_digest, plan_digest
from proofrail_gateway import AuthorityIssuer, Gateway, Observer
from records import PilotError, stamp, utc, validate, without


def reason(fn):
    with pytest.raises(PilotError) as exc:
        fn()
    return exc.value.reason


def case(env):
    problem, plan, approval, envelope = approved(env)
    return env.p.store.get('tenant-a', 'problem', problem['problem_id']), plan, approval


# ------------------------------------------------------------------ policy: plans

def replan(plan, **changes):
    new = {**copy.deepcopy(plan), **changes}
    new['plan_digest'] = plan_digest(new)
    return new


@pytest.mark.parametrize('changes,expected', [
    ({'problem_id': 'prb-other'}, 'plan_problem_mismatch'),
    ({'target': {'tenant_id': 'tenant-a', 'facility_id': 'FAC-A1', 'area_id': 'ZONE-X'}}, 'plan_target_mismatch'),
    ({'currency': 'EUR'}, 'currency_mismatch'),
    ({'estimated_cost': 60000}, 'cost_exceeds_policy'),
    ({'provider_id': 'P-099'}, 'provider_not_approved'),
    ({'expected_completion_window': {'start': '2026-10-24T00:00:00Z', 'end': '2026-10-23T00:00:00Z'}},
     'invalid_completion_window'),
    ({'policy_root': 'c' * 64}, 'policy_changed'),
])
def test_plan_checks(env, changes, expected):
    problem, plan, approval = case(env)
    assert reason(lambda: env.p.policy.check_plan(problem, replan(plan, **changes))) == expected


def test_plan_digest_must_recompute(env):
    problem, plan, approval = case(env)
    assert reason(lambda: env.p.policy.check_plan(problem, {**plan, 'plan_digest': 'a' * 64})) == 'plan_digest_mismatch'


def test_problem_must_be_confirmed(env):
    problem, plan, approval = case(env)
    assert reason(lambda: env.p.policy.check_plan({**problem, 'status': 'REPORTED'}, plan)) == 'problem_not_confirmed'


@pytest.mark.parametrize('field,expected', [('allowed_problem_types', 'problem_type_not_permitted'),
                                            ('allowed_risk_classes', 'risk_class_not_permitted')])
def test_policy_must_permit_the_problem(env, field, expected):
    problem, plan, approval = case(env)
    doc = {k: v for k, v in env.p.policy.doc('tenant-a').items() if k != 'tenant_id'}
    env.p.policy.set('tenant-a', {**doc, field: []})
    assert reason(lambda: env.p.policy.check_plan(problem, plan)) == expected


def test_tenant_without_policy(env):
    assert reason(lambda: env.p.policy.doc('tenant-z')) == 'no_policy_for_tenant'


# ------------------------------------------------------------------ policy: approvals

def reapprove(env, approval, *, signer='approver-a', keep_digest=False, **changes):
    new = {k: v for k, v in copy.deepcopy(approval).items() if k not in ('record_hash', 'signature')}
    new.update(changes)
    if not keep_digest:
        new['approval_digest'] = approval_digest(new)
    return env.w[signer].sign(new)


def check(env, problem, plan, approval, now=None):
    return reason(lambda: env.p.policy.check_approval(env.p.registry, problem, plan, approval,
                                                      now=now or env.w.clock.now()))


@pytest.mark.parametrize('changes,expected', [
    ({'approver_principal': 'approver-b'}, 'approver_identity_mismatch'),
    ({'approved_plan_digest': 'b' * 64}, 'approval_scope_changed'),
    ({'approved_provider': 'P-099'}, 'provider_changed'),
    ({'currency': 'EUR'}, 'currency_mismatch'),
    ({'approved_maximum_cost': 30000}, 'cost_exceeds_approval'),
    ({'approved_maximum_cost': 60000}, 'cost_exceeds_policy'),
])
def test_approval_checks(env, changes, expected):
    problem, plan, approval = case(env)
    assert check(env, problem, plan, reapprove(env, approval, **changes)) == expected


def test_approval_digest_must_recompute(env):
    problem, plan, approval = case(env)
    assert check(env, problem, plan, reapprove(env, approval, keep_digest=True, approval_digest='a' * 64)) \
        == 'approval_digest_mismatch'


def test_approval_time_checks(env):
    problem, plan, approval = case(env)
    now = env.w.clock.now()
    future = reapprove(env, approval, issued_at=stamp(now + timedelta(hours=1)),
                       expires_at=stamp(now + timedelta(hours=2)))
    assert check(env, problem, plan, future) == 'approval_not_yet_valid'
    assert check(env, problem, plan, approval, now=now + timedelta(hours=25)) == 'approval_expired'
    long = reapprove(env, approval, expires_at=stamp(utc(approval['issued_at']) + timedelta(hours=100)))
    assert check(env, problem, plan, long) == 'approval_validity_too_long'


def test_problem_evidence_root_must_match_its_refs(env):
    problem, plan, approval = case(env)
    resigned = env.w['reviewer-a'].sign({**without(problem, 'record_hash', 'signature'), 'evidence_root': 'd' * 64})
    assert check(env, resigned, plan, approval) == 'evidence_root_inconsistent'


def test_problem_cannot_be_confirmed_by_its_reporter(env):
    problem, plan, approval = case(env)
    dual = env.p.registry.add('dual-a', tenant_id='tenant-a', organization='northside-logistics',
                              roles={'reporter', 'problem_reviewer'})
    resigned = dual.sign({**without(problem, 'record_hash', 'signature'), 'reported_by': 'dual-a'})
    assert check(env, resigned, plan, approval) == 'problem_confirmed_by_its_reporter'


# ------------------------------------------------------------------ records and registry

def test_schema_validation_and_timestamps(env):
    assert reason(lambda: validate('problem_record', {})) == 'invalid_problem_record'
    assert reason(lambda: utc('2026-10-23T13:00:00+00:00')) == 'invalid_timestamp'   # offset form is ambiguous here
    assert reason(lambda: utc('not a timeZ')) == 'invalid_timestamp'


def test_registry_guards(env):
    r = env.p.registry
    assert reason(lambda: r.add('x', tenant_id='tenant-a', organization='o', roles={'superuser'})) == 'unknown_role'
    assert reason(lambda: r.add('buyer-a', tenant_id='tenant-a', organization='o', roles={'buyer'})) == 'duplicate_principal'
    existing = env.w['buyer-a']
    assert reason(lambda: r.adopt(existing.principal, existing.private_key)) == 'duplicate_principal'
    from records import Registry
    fresh = Registry()
    assert reason(lambda: fresh.adopt(existing.principal, Ed25519PrivateKey.generate())) == 'key_does_not_match_principal'
    assert reason(lambda: r.get('nobody')) == 'unknown_principal'


def test_designation_guards(env):
    r = env.p.registry
    assert reason(lambda: r.designate_inspector(tenant_id='tenant-a', facility_id='FAC-A1', inspector_id='inspector-a',
                                                by=env.w['qa-a'])) == 'designation_requires_tenant_buyer'
    assert reason(lambda: r.designate_inspector(tenant_id='tenant-a', facility_id='FAC-A1', inspector_id='inspector-a',
                                                by=env.w['buyer-b'])) == 'designation_requires_tenant_buyer'
    assert reason(lambda: r.designate_inspector(tenant_id='tenant-a', facility_id='FAC-A1', inspector_id='contractor-a',
                                                by=env.w['buyer-a'])) == 'designee_not_inspector'


def test_signer_guards(env):
    problem, plan, approval = case(env)
    r = env.p.registry
    assert reason(lambda: r.signer(without(approval, 'signature'), role='approver', tenant_id='tenant-a')) \
        == 'signature_missing'
    foreign = {**approval, 'signature': {**approval['signature'], 'key_id': 'key-unknown'}}
    assert reason(lambda: r.signer(foreign, role='approver', tenant_id='tenant-a')) == 'unknown_signing_key'
    assert reason(lambda: r.signer(approval, role='buyer', tenant_id='tenant-a')) == 'signer_role_not_permitted'
    assert reason(lambda: r.signer(approval, role='approver', tenant_id='tenant-b')) == 'signer_tenant_mismatch'


# ------------------------------------------------------------------ gateway components

def test_components_require_their_roles(env):
    w, p = env.w, env.p
    gw = p.gateways['tenant-a']
    assert reason(lambda: AuthorityIssuer(w['gateway-a'], p.registry, p.store, p.policy, w.clock)) == 'issuer_role_required'
    assert reason(lambda: Observer(w['issuer-a'], gw.observer.client, w.clock)) == 'observer_role_required'
    kwargs = dict(registry=p.registry, store=p.store, policy=p.policy, clock=w.clock, replay_registry=p.replay_registry,
                  issuer_id='issuer-a', provider=gw.provider, observer=gw.observer)
    assert reason(lambda: Gateway(w['issuer-a'], **kwargs)) == 'gateway_role_required'
    assert reason(lambda: Gateway(w['gateway-a'], **{**kwargs, 'replay_registry': p.store.path})) \
        == 'separate_replay_registry_required'


def test_gateway_trusts_only_a_registered_issuer(env):
    problem, plan, approval, envelope = approved(env)
    gw = env.p.gateways['tenant-a']
    gw.issuer_id = 'approver-a'          # misconfiguration: pinned to a principal without the issuer role
    assert reason(lambda: env.p.admit('tenant-a', envelope)) == 'issuer_not_trusted'
    assert env.count() == 0


def test_malformed_envelopes(env):
    approved(env)
    assert reason(lambda: env.p.admit('tenant-a', ['not', 'a', 'dict'])) == 'invalid_envelope'
    assert reason(lambda: env.p.admit('tenant-a', {'record_hash': 'a' * 64, 'envelope_id': 'e', 'effect': 'x'})) \
        == 'invalid_envelope'
    assert env.count() == 0


def test_issuer_refuses_a_case_that_is_no_longer_approved(env):
    problem, plan, approval, envelope = approved(env)
    env.p.admit('tenant-a', envelope)
    assert reason(lambda: env.w.authorize(problem, plan, approval)) == 'work_not_approved'


def test_reconciliation_that_writes_is_refused(env, monkeypatch):
    problem, plan, approval, envelope = approved(env)
    env.arm('drop_without_effect')
    env.p.admit('tenant-a', envelope)
    gw = env.p.gateways['tenant-a']
    real = gw._reconcile

    def writes(*args):
        gw.provider_calls += 1           # a regression that issues a provider write during reconciliation
        return real(*args)
    monkeypatch.setattr(gw, '_reconcile', writes)
    assert reason(lambda: env.p.reconcile('tenant-a', envelope['envelope_id'])) == 'reconciliation_issued_provider_write'


# ------------------------------------------------------------------ outcome qualification

def inspection(env, pid, **changes):
    env.p.submit_inspection(env.w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET,
                            evidence_refs=env.w.inspection_refs())
    obs = [o for o in env.p.store.all('tenant-a', 'observation') if o['observation_type'] == 'inspection'][-1]
    edited = {**without(obs, 'record_hash', 'signature'), **changes}
    return env.w['inspector-a'].sign(edited)


def qualify(env, pid, obs, **override):
    authority = env.p._authority_for('tenant-a', pid)
    plan = env.p.store.get('tenant-a', 'plan', authority['envelope']['effect']['parameters']['plan_id'])
    created = next(utc(o['observation_time']) for o in env.p.store.all('tenant-a', 'observation')
                   if o['record_hash'] == authority['reference']['reconciliation_reference'])
    args = dict(registry=env.p.registry, tenant_id='tenant-a', plan={**plan, '_grace_hours': 24},
                work_order_id=authority['reference']['provider_operation_reference'], created_at=created,
                problem=env.p.store.get('tenant-a', 'problem', pid),
                provider_organization='clearpath-facility-services', now=env.w.clock.now())
    args.update(override)
    return outcome_verifier.qualify_inspection(obs, **args)


def test_qualification_reasons(env):
    problem, *_ = through_work(env)
    pid = problem['problem_id']
    assert qualify(env, pid, inspection(env, pid)) is None                                    # control
    assert qualify(env, pid, inspection(env, pid, observer_principal='inspector2-a')) == 'observer_identity_mismatch'
    assert qualify(env, pid, inspection(env, pid, independence_class='performer_claim')) == 'not_an_independent_inspection'
    assert qualify(env, pid, inspection(env, pid, observed_subject={'kind': 'work_order', 'id': 'WO-1'})) \
        == 'observation_for_other_work_order'
    early = stamp(env.w.clock.now() - timedelta(hours=10))
    assert qualify(env, pid, inspection(env, pid, observation_time=early)) == 'inspection_time_invalid'
    future = stamp(env.w.clock.now() + timedelta(hours=1))
    assert qualify(env, pid, inspection(env, pid, observation_time=future)) == 'inspection_time_invalid'
    assert qualify(env, pid, inspection(env, pid, findings={'criteria': {'C1': 'not_met', 'C2': 'met'}})) \
        == 'observation_digest_mismatch'


def test_assessment_preconditions(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    authority = p._authority_for('tenant-a', pid)
    plan = p.store.get('tenant-a', 'plan', plan['plan_id'])
    args = dict(registry=p.registry, tenant_id='tenant-a', problem=p.store.get('tenant-a', 'problem', pid), plan=plan,
                observations=p.store.all('tenant-a', 'observation'), provider_organization='clearpath-facility-services',
                contractors=set(), grace_hours=24, policy_digest='a' * 64, now=w.clock.now())
    unknown = {**authority, 'reference': {**authority['reference'], 'authority_state': 'EXECUTION_UNKNOWN'}}
    assert reason(lambda: outcome_verifier.assess(w['qa-a'], authority=unknown, **args)) == 'execution_not_reconciled'
    assert reason(lambda: outcome_verifier.assess(w['buyer-a'], authority=authority, **args)) == 'reviewer_not_permitted'
    assert reason(lambda: outcome_verifier.assess(w['qa-b'], authority=authority, **args)) == 'reviewer_not_permitted'
    no_recon = {**args, 'observations': [o for o in args['observations']
                                        if o['observation_type'] != 'provider_work_order_state']}
    assert reason(lambda: outcome_verifier.assess(w['qa-a'], authority=authority, **no_recon)) \
        == 'reconciliation_observation_missing'


# ------------------------------------------------------------------ settlement rules

def settlement_inputs(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    acceptance = p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='clear')
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=30000)
    return dict(registry=p.registry, store=p.store, tenant_id='tenant-a', work_order_id=result['work_order_id'],
                verdicts=[verdict], acceptance=acceptance, invoice=invoice, approval=approval,
                authority=p._authority_for('tenant-a', pid), provider_organization='clearpath-facility-services',
                contractors=set(), now=w.clock.now(), current_order_matches=True)


def test_settlement_rule_reasons(env):
    args = settlement_inputs(env)
    w = env.w
    assert reason(lambda: settlement_simulator.decide(w['qa-a'], **args)) == 'authorizer_not_permitted'
    unknown = {**args['authority'], 'reference': {**args['authority']['reference'], 'authority_state': 'EXECUTION_UNKNOWN'}}
    decide = lambda **o: settlement_simulator.decide(w['finance-a'], **{**args, **o})['denial_reasons']
    assert decide(authority=unknown) == ['work_order_not_reconciled_for_this_authority']
    acc = args['acceptance']
    misattributed = w['buyer-a'].sign({**without(acc, 'record_hash', 'signature'), 'buyer_principal': 'buyer-x'})
    assert decide(acceptance=misattributed) == ['buyer_identity_mismatch']
    unbound = w['buyer-a'].sign({**without(acc, 'record_hash', 'signature'), 'outcome_digest': 'e' * 64})
    assert decide(acceptance=unbound) == ['acceptance_not_bound_to_latest_verdict']
    assert decide() == []                                                               # control


# ------------------------------------------------------------------ pilot, store and export guards

def test_pilot_guards(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    assert reason(lambda: p._move(w['qa-b'], 'tenant-a', pid, 'begin_review')) == 'actor_tenant_mismatch'
    assert reason(lambda: p.revoke_approval(w['contractor-a'], 'tenant-a', approval['approval_id'])) \
        == 'revocation_not_permitted'
    assert reason(lambda: p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='x')) == 'no_verdict'
    assert reason(lambda: p.learning_record('tenant-a', pid, area_type='staging_zone', debris_volume_class='small',
                                            shareable=False)) == 'case_not_closed'
    assert reason(lambda: p.store.put('tenant-a', 'secrets', 'x', {})) == 'unknown_kind'


def test_export_guards(env):
    problem, plan, approval, envelope = approved(env)
    pid = problem['problem_id']
    assert reason(lambda: export_case(env.w['buyer-a'], env.p, 'tenant-a', pid, env.tmp / 'b')) \
        == 'case_has_no_single_admitted_authority'
    env.p.admit('tenant-a', envelope)
    (env.tmp / 'taken').mkdir()
    assert reason(lambda: export_case(env.w['buyer-a'], env.p, 'tenant-a', pid, env.tmp / 'taken')) \
        == 'export_destination_exists'
    assert reason(lambda: _claim(env.p.replay_registry, 'f' * 64)) == 'consumption_record_missing'
