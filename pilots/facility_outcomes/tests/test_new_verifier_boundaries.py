"""Focused regressions for five verifier controls surviving the integrated sweep.

Only synthetic, locally exported pilot bundles are modified. Every assertion
names the relevant fail-closed guard or the exact stable error reason. Other
dimension failures do not qualify as evidence that the target check works.
"""
from __future__ import annotations

import copy
import pytest

from test_bundle import edit, full_case, pinned_fixture_keys, resum
from evidence_export import export_case
from verify_bundle import verify


@pytest.fixture
def bundle(env):
    pid = full_case(env)
    root = export_case(env.w['buyer-a'], env.p, 'tenant-a', pid, env.tmp / 'bundle-final-five')
    assert verify(root, pinned_fixture_keys(env))['verified']
    return root, env


def failed_check(report, dimension, name, *, detail=None):
    checks = [c for c in report['dimensions'][dimension]['checks'] if c['check'] == name]
    assert len(checks) == 1, (dimension, name, report)
    assert checks[0]['result'] == 'FAIL', (name, checks[0], report)
    if detail is not None:
        assert checks[0]['detail'] == detail, (name, checks[0], detail)
    assert report['verified'] is False


def test_admission_gateway_must_have_registered_gateway_role(bundle):
    root, env = bundle

    def clear_gateway_role(s):
        who = next(p for p in s['principals'] if p['principal_id'] == 'gateway-a')
        assert 'gateway' in who['roles']
        who['roles'].remove('gateway')

    edit(root, 'context/identity-at-admission.json', clear_gateway_role)
    resum(root)
    report = verify(root, pinned_fixture_keys(env))
    failed_check(report, 'authenticity', 'admission-time gateway identity is registered')


def test_consumption_snapshot_has_exact_spent_executor_and_nonce(bundle):
    root, env = bundle
    edit(root, 'records/consumption.json',
         lambda rows: rows['claim'].update(nonce='separately-issued-nonce'))
    resum(root)
    report = verify(root, pinned_fixture_keys(env))
    failed_check(
        report, 'authority',
        'unsigned registry-export snapshot reports one consumption by the named executor')


def test_unknown_historical_gateway_has_specific_refusal_reason(bundle):
    root, env = bundle

    def drop_gateway(s):
        s['principals'] = [p for p in s['principals'] if p['principal_id'] != 'gateway-a']

    edit(root, 'context/identity-at-admission.json', drop_gateway)
    resum(root)
    report = verify(root, pinned_fixture_keys(env))
    failed_check(report, 'authenticity',
                 'gateway signature authenticates consumption-row attestation',
                 detail='consumption_gateway_unknown')


def test_gateway_receipt_mismatched_key_id_has_specific_refusal_reason(bundle):
    root, env = bundle
    edit(root, 'records/consumption-attestation.json',
         lambda a: a['signature'].update(key_id='key-from-another-issuer'))
    resum(root)
    report = verify(root, pinned_fixture_keys(env))
    failed_check(report, 'authenticity',
                 'gateway signature authenticates consumption-row attestation',
                 detail='consumption_gateway_key_mismatch')


@pytest.mark.parametrize('snapshot,phase', [
    ('context/identity-at-admission.json', 'admission'),
    ('context/identity-at-export.json', 'export'),
])
def test_principal_ids_must_be_unique_in_each_snapshot(bundle, snapshot, phase):
    root, env = bundle

    def duplicate_principal(s):
        assert s['principals']
        s['principals'].append(copy.deepcopy(s['principals'][0]))

    edit(root, snapshot, duplicate_principal)
    resum(root)
    report = verify(root, pinned_fixture_keys(env))
    failed_check(report, 'authenticity',
                 f'{phase} identity snapshot has unique principal IDs')
