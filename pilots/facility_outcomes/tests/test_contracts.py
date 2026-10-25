"""Contracts: schemas reject ambiguous input; docs match the code; digests bind what they claim."""
import json
from pathlib import Path

import pytest

import lifecycle
from conftest import approved
from policy import approval_digest, plan_digest
from records import PilotError, SCHEMAS, validate

DOCS = Path(__file__).resolve().parents[3] / 'docs'
NAMES = sorted(p.name.replace('.schema.json', '') for p in SCHEMAS.glob('*.schema.json'))


def test_state_machine_document_matches_the_transition_table():
    text = (DOCS / 'WRN_STATE_MACHINES.md').read_text()
    generated = text.split('<!-- BEGIN GENERATED TRANSITIONS -->\n')[1].split('<!-- END GENERATED TRANSITIONS -->')[0]
    assert generated == lifecycle.markdown_table()


def test_every_transition_names_an_actor_states_and_a_failure():
    for t in lifecycle.TRANSITIONS:
        assert t.actor_role and t.sources and t.target in lifecycle.STATES and t.failure and t.evidence
        assert all(s in lifecycle.STATES or s == 'NONE' for s in t.sources)


def test_transition_guard():
    assert lifecycle.transition('APPROVED', 'admit_work_order', {'gateway'}) == 'WORK_ORDER_PENDING'
    with pytest.raises(PilotError) as exc:
        lifecycle.transition('APPROVED', 'admit_work_order', {'planner'})
    assert exc.value.reason == 'actor_not_permitted'
    with pytest.raises(PilotError) as exc:
        lifecycle.transition('CLOSED', 'admit_work_order', {'gateway'})
    assert exc.value.reason == 'transition_not_allowed'
    with pytest.raises(PilotError) as exc:
        lifecycle.transition('APPROVED', 'teleport', {'gateway'})
    assert exc.value.reason == 'unknown_transition'


@pytest.mark.parametrize('name', NAMES)
def test_every_schema_is_closed(name):
    schema = json.loads((SCHEMAS / f'{name}.schema.json').read_text())
    assert schema['additionalProperties'] is False and schema['required']


def real_records(env):
    problem, plan, approval, envelope = approved(env)
    env.p.admit('tenant-a', envelope)
    authority = env.p.store.get('tenant-a', 'authority', envelope['envelope_id'])
    return {'problem_record': env.p.store.get('tenant-a', 'problem', problem['problem_id']),
            'intervention_plan': plan, 'approval_record': approval,
            'execution_authority_reference': authority['reference'],
            'observation_record': env.p.store.all('tenant-a', 'observation')[0]}


def test_real_records_validate_and_extra_fields_are_rejected(env):
    for name, record in real_records(env).items():
        validate(name, record)
        with pytest.raises(PilotError) as exc:
            validate(name, {**record, 'unexpected': True})
        assert exc.value.reason == f'invalid_{name}'


@pytest.mark.parametrize('value', ['2026-10-23T13:00:00+00:00', '2026-10-23 13:00:00Z', '2026-10-23T13:00:00',
                                   '23/10/2026', 1792406400])
def test_ambiguous_timestamps_are_rejected(env, value):
    problem = real_records(env)['problem_record']
    with pytest.raises(PilotError):
        validate('problem_record', {**problem, 'reported_at': value})


@pytest.mark.parametrize('value', [32000.5, '32000', -1, 10 ** 12])
def test_money_is_bounded_integer_minor_units(env, value):
    plan = real_records(env)['intervention_plan']
    with pytest.raises(PilotError):
        validate('intervention_plan', {**plan, 'estimated_cost': value})


def test_plan_and_approval_digests_bind_every_field(env):
    records = real_records(env)
    plan, approval = records['intervention_plan'], records['approval_record']
    for field in ('provider_id', 'estimated_cost', 'target', 'acceptance_criteria', 'policy_root', 'scope_revision'):
        changed = {**plan, field: 'x'}
        assert plan_digest(changed) != plan['plan_digest'], field
    for field in ('approved_plan_digest', 'approved_maximum_cost', 'approved_provider', 'expires_at', 'tenant_id'):
        assert approval_digest({**approval, field: 'x'}) != approval['approval_digest'], field


def test_settlement_schema_forbids_money_movement(env):
    schema = json.loads((SCHEMAS / 'settlement_decision.schema.json').read_text())
    assert schema['properties']['money_moved'] == {'const': False}


def test_learning_schema_forbids_identifiers_and_causal_claims(env):
    schema = json.loads((SCHEMAS / 'learning_record.schema.json').read_text())
    assert schema['properties']['causal_claim'] == {'const': 'none'}
    assert schema['properties']['context_features']['additionalProperties'] is False
    text = json.dumps(schema)
    assert 'tenant_id' not in text and 'facility_id' not in text and 'principal' not in text
