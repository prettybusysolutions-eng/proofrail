"""Portable case evidence: tampering fails the right dimension; missing proof never verifies an outcome."""
import hashlib
import json
import subprocess
import sys

import pytest

from conftest import PILOT, through_work
from evidence_export import export_case
from fixtures import ALL_MET
from records import PilotError
from verify_bundle import verify


def full_case(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid, p, w = problem['problem_id'], env.p, env.w
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    p.assess(w['qa-a'], 'tenant-a', pid)
    p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='clear')
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=32000)
    p.settle(w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    return pid


def resum(root):
    """An attacker who edits files also regenerates every checksum."""
    manifest = json.loads((root / 'manifest.json').read_text())
    files = [p for p in root.rglob('*') if p.is_file() and p.name not in ('SHA256SUMS', 'manifest.json')]
    manifest['files'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    files = sorted(p for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (root / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n'
                                             for p in files))


def edit(root, rel, change):
    path = root / rel
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


@pytest.fixture
def bundle(env):
    pid = full_case(env)
    return export_case(env.w['buyer-a'], env.p, 'tenant-a', pid, env.tmp / 'bundle'), env


def test_genuine_bundle_verifies_on_every_dimension(bundle):
    root, env = bundle
    report = verify(root)
    assert report['verified'] and report['key_trust'] == 'self_asserted'
    assert {d: v['result'] for d, v in report['dimensions'].items()} == {
        'integrity': 'PASS', 'authenticity': 'PASS', 'authority': 'PASS', 'execution': 'PASS', 'outcome': 'PASS'}
    assert report['physical_outcome']['stated'] == 'VERIFIED' == report['physical_outcome']['reproduced']
    assert 'not physical proof' in report['physical_outcome']['nature']


def test_command_line_exit_codes(bundle):
    root, env = bundle
    assert subprocess.run([sys.executable, str(PILOT / 'verify_bundle.py'), str(root)],
                          capture_output=True).returncode == 0
    (root / 'extra.txt').write_text('x')
    assert subprocess.run([sys.executable, str(PILOT / 'verify_bundle.py'), str(root)],
                          capture_output=True).returncode == 1


def pinned_fixture_keys(env):
    """Keys held by the synthetic test world, not copied from the evidence export."""
    return {ident.principal.principal_id: ident.principal.public_key
            for ident in env.w.ids.values() if ident.principal.tenant_id == 'tenant-a'}


def test_trusted_keys_upgrade_and_mismatch(bundle):
    root, env = bundle
    keys = pinned_fixture_keys(env)
    assert verify(root, keys)['key_trust'] == 'trusted' and verify(root, keys)['verified']
    keys['approver-a'] = keys['buyer-a']                      # an independently held key disagrees
    report = verify(root, keys)
    assert not report['verified'] and report['dimensions']['authenticity']['result'] == 'FAIL'


def test_swapped_public_key_in_the_bundle_fails_against_trusted_keys(bundle):
    """A key substituted inside the bundle is caught by independently held keys."""
    root, env = bundle
    trusted = pinned_fixture_keys(env)
    edit(root, 'context/identity-at-export.json',
         lambda d: d['principals'][0].update(public_key=d['principals'][1]['public_key']))
    resum(root)
    assert not verify(root, trusted)['verified']


def test_historical_issuer_key_is_pinned_even_if_absent_from_export_snapshot(bundle):
    """An earlier issuer still needs independent trust after its account is removed."""
    root, env = bundle
    trusted = pinned_fixture_keys(env)
    def remove_retired_issuer(snapshot):
        snapshot['principals'] = [p for p in snapshot['principals']
                                  if p['principal_id'] != 'issuer-a']
    edit(root, 'context/identity-at-export.json', remove_retired_issuer)
    resum(root)
    report = verify(root, trusted)
    assert report['verified'] and report['key_trust'] == 'trusted', report

    untrusted_history = {k: v for k, v in trusted.items() if k != 'issuer-a'}
    report = verify(root, untrusted_history)
    assert not report['verified']
    assert report['dimensions']['authenticity']['result'] == 'FAIL'
    assert any(x['check'] == 'admission key of issuer-a matches independently trusted key'
               and x['result'] == 'FAIL'
               for x in report['dimensions']['authenticity']['checks'])


def test_historical_issuer_key_substitution_fails_trusted_origin_check(bundle):
    """Fail on independently pinned admission-time key mismatch, not only on hashes."""
    root, env = bundle
    trusted = pinned_fixture_keys(env)
    def change_issuer_key(snapshot):
        issuer = next(p for p in snapshot['principals'] if p['principal_id'] == 'issuer-a')
        issuer['public_key'] = trusted['buyer-a']
    edit(root, 'context/identity-at-admission.json', change_issuer_key)
    resum(root)
    report = verify(root, trusted)
    assert not report['verified']
    assert report['dimensions']['authenticity']['result'] == 'FAIL'
    assert any(x['check'] == 'admission key of issuer-a matches independently trusted key'
               and x['result'] == 'FAIL'
               for x in report['dimensions']['authenticity']['checks'])


@pytest.mark.parametrize('rel,change,dimension', [
    ('records/approval.json', lambda d: d.update(approved_maximum_cost=99000), 'authenticity'),
    ('records/envelope.json', lambda d: d['effect']['parameters'].update(max_cost=99000), 'authority'),
    ('records/consumption.json', lambda d: d['claim'].update(nonce='0' * 64), 'authority'),
    ('records/authority_reference.json', lambda d: d.update(authority_state='EXECUTION_UNKNOWN'), 'execution'),
    ('context/policy-at-admission.json', lambda d: d.update(max_work_order_cost=1), 'authority'),
    ('context/state-inputs-at-admission.json', lambda d: d.update(work_state='CANCELLED'), 'authority'),
    ('context/identity-at-admission.json', lambda d: d['designations'].pop(), 'authority'),
    ('audit/chain.json', lambda d: d[0]['detail'].update(actor='someone-else'), 'authenticity'),
])
def test_tampering_fails_the_right_dimension_even_with_new_checksums(bundle, rel, change, dimension):
    root, env = bundle
    edit(root, rel, change)
    resum(root)
    report = verify(root)
    assert not report['verified']
    assert report['dimensions']['integrity']['result'] == 'PASS'      # checksums were regenerated
    assert report['dimensions'][dimension]['result'] == 'FAIL'


def test_provider_observation_tampered_to_show_a_different_order(bundle):
    root, env = bundle
    reference = json.loads((root / 'records' / 'authority_reference.json').read_text())
    for path in (root / 'records' / 'observations').glob('*.json'):
        data = json.loads(path.read_text())
        if data['record_hash'] == reference['reconciliation_reference']:
            data['findings']['work_order']['orders'][0]['area_id'] = 'ZONE-OTHER'
            path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    resum(root)
    report = verify(root)
    assert report['dimensions']['authenticity']['result'] == 'FAIL'       # observer signature breaks
    assert report['dimensions']['execution']['result'] == 'FAIL'


def test_removed_inspection_means_the_verdict_no_longer_reproduces(bundle):
    root, env = bundle
    for path in (root / 'records' / 'observations').glob('*.json'):
        if json.loads(path.read_text())['observation_type'] == 'inspection':
            path.unlink()
    resum(root)
    report = verify(root)
    assert report['physical_outcome']['stated'] == 'VERIFIED'
    assert report['physical_outcome']['reproduced'] == 'INSUFFICIENT_EVIDENCE'
    assert not report['verified'] and report['dimensions']['outcome']['result'] == 'FAIL'


def test_case_without_inspection_never_presents_a_verified_outcome(env):
    problem, plan, approval, envelope, result = through_work(env)
    pid = problem['problem_id']
    env.p.assess(env.w['qa-a'], 'tenant-a', pid)
    report = verify(export_case(env.w['qa-a'], env.p, 'tenant-a', pid, env.tmp / 'b2'))
    assert report['verified']                                    # the bundle is honest and consistent
    assert report['physical_outcome']['stated'] == 'INSUFFICIENT_EVIDENCE'
    assert report['physical_outcome']['buyer_decision'] is None


def test_malformed_bundle_is_a_failure_not_a_crash(bundle):
    root, env = bundle
    (root / 'records' / 'envelope.json').write_text('{not json')
    out = subprocess.run([sys.executable, str(PILOT / 'verify_bundle.py'), str(root), '--json'],
                         capture_output=True, text=True)
    assert out.returncode == 1 and json.loads(out.stdout)['verified'] is False


def test_export_requires_a_tenant_evidence_role(env):
    pid = full_case(env)
    for actor in ('contractor-a', 'inspector-a', 'buyer-b', 'qa-b'):
        with pytest.raises(PilotError) as exc:
            export_case(env.w[actor], env.p, 'tenant-a', pid, env.tmp / ('x-' + actor))
        assert exc.value.reason == 'export_not_permitted'


def test_bundle_holds_no_private_material_or_other_tenants(bundle):
    root, env = bundle
    blob = ''.join(p.read_text() for p in root.rglob('*') if p.is_file())
    assert 'private' not in blob.lower() and 'tenant-b' not in blob and '-b"' not in blob
    assert not [p for p in root.rglob('*') if p.suffix in ('.sqlite3', '.db', '.hex', '.key')]
