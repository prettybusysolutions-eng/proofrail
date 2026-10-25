"""Provider-enforced authorization (#57) over real HTTP.

The enforcing simulator runs as its own process, its trusted roster loaded from an
operator-provisioned file. Every request here is built only from authority that the
pilot's own issuer and gateway legitimately produced: nothing is hand-signed,
re-signed or altered after signing. Refusals come from missing or mismatched
request context, an untrusted roster, or time.

The pilot world normally runs on a pinned clock (2026-10-23); the enforcing provider
reads wall time, so these tests run the world on the real clock.
"""
import base64
import json
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import PILOT
from fixtures import World
from records import Clock, PilotError


def free_port():
    with closing(socket.socket()) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def roster(world, *, tenants=('a', 'b'), gateways=True, issuers=True):
    entry = lambda name: {'tenant_id': world.ids[name].principal.tenant_id,
                          'key_id': world.ids[name].principal.key_id,
                          'public_key': world.ids[name].principal.public_key}
    return {'issuers': {f'issuer-{t}': entry(f'issuer-{t}') for t in tenants} if issuers else {},
            'gateways': {f'gateway-{t}': entry(f'gateway-{t}') for t in tenants} if gateways else {}}


def start_enforcing(workdir: Path, port: int, trusted: dict):
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / 'roster.json').write_text(json.dumps(trusted))
    port_file = workdir / 'provider.port'
    port_file.unlink(missing_ok=True)            # a restart must wait for the new process, not the old file
    proc = subprocess.Popen([sys.executable, '-I', str(PILOT / 'provider_simulator.py'),
                             '--db', str(workdir / 'provider.sqlite3'), '--port', str(port),
                             '--port-file', str(port_file), '--enforce-authority', str(workdir / 'roster.json')])
    deadline = time.monotonic() + 15
    while not port_file.exists():
        if proc.poll() is not None or time.monotonic() > deadline:
            proc.kill()
            raise AssertionError('enforcing provider did not start')
        time.sleep(0.02)
    return proc


def orders(db: Path) -> int:
    """Ground truth read straight from the provider's store (admin endpoints are disabled)."""
    if not db.exists():
        return 0
    with closing(sqlite3.connect(f'file:{db}?mode=ro', uri=True)) as c:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        table = next(n for n in names if 'order' in n)
        return c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


@pytest.fixture
def enforced(tmp_path):
    port = free_port()
    url = f'http://127.0.0.1:{port}'
    world = World(tmp_path / 'pilot', url, clock=Clock(datetime.now(timezone.utc)), provider_timeout=2.0)
    procs = [start_enforcing(tmp_path / 'provider', port, roster(world))]
    db = tmp_path / 'provider' / 'provider.sqlite3'

    def restart(trusted):
        procs[0].kill()
        procs[0].wait()
        procs[0] = start_enforcing(tmp_path / 'provider', port, trusted)
    try:
        yield SimpleNamespace(w=world, p=world.pilot, url=url, tmp=tmp_path, count=lambda: orders(db),
                              restart=restart)
    finally:
        procs[0].kill()
        procs[0].wait()


def approve(env, t='a'):
    problem = env.w.report(t)
    plan, approval = env.w.plan_and_approve(problem, t)
    return problem, plan, approval, env.w.authorize(problem, plan, approval, t)


def pack(record):
    return base64.b64encode(json.dumps(record, sort_keys=True).encode()).decode()


def credentials(env, envelope, t='a'):
    """The envelope and signed receipt exactly as the gateway stored them."""
    stored = env.p.store.get(f'tenant-{t}', 'authority', envelope['envelope_id'])
    return stored['envelope'], stored['consumption_attestation']


def post(env, tenant, body, headers):
    req = urllib.request.Request(f'{env.url}/v1/tenants/{tenant}/work-orders', method='POST',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          # Caller-chosen and untrusted: authority never comes from it.
                                          'X-Client-Id': 'direct-client', **headers})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def direct(env, envelope, receipt, *, tenant='tenant-a', body=None, key=None, drop=()):
    headers = {'Idempotency-Key': key or envelope['record_hash'],
               'X-ProofRail-Envelope': pack(envelope), 'X-ProofRail-Consumption': pack(receipt)}
    for name in drop:
        headers.pop(name)
    return post(env, tenant, body if body is not None else dict(envelope['effect']['parameters']), headers)


# ------------------------------------------------------------------ the authorized path

def test_gateway_authority_is_accepted_and_reconciles(enforced):
    problem, plan, approval, envelope = approve(enforced)
    result = enforced.p.admit('tenant-a', envelope)
    assert result['authority_state'] == 'RECONCILED'
    assert enforced.count() == 1


def test_replaying_executed_authority_creates_nothing_new(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    first = enforced.count()
    status, _ = direct(enforced, *credentials(enforced, envelope))
    assert status in (200, 201) and enforced.count() == first == 1     # provider idempotency


def test_admin_endpoints_are_disabled(enforced):
    for method, path in (('GET', '/admin/count'), ('POST', '/admin/fault'), ('POST', '/admin/status')):
        req = urllib.request.Request(enforced.url + path, method=method, data=b'{}' if method == 'POST' else None,
                                     headers={'Content-Type': 'application/json'})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        assert exc.value.code == 403
        assert json.loads(exc.value.read())['error'] == 'admin_disabled_in_enforced_mode'


# ------------------------------------------------------------------ refusals: request context

def test_no_authority_is_refused(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    before = enforced.count()
    body = dict(envelope['effect']['parameters'], client_reference='direct-client')
    status, reply = post(enforced, 'tenant-a', body, {'Idempotency-Key': 'f' * 64})
    assert (status, reply['error']) == (403, 'authority_header_missing_or_oversized')
    assert enforced.count() == before


@pytest.mark.parametrize('missing', ['X-ProofRail-Envelope', 'X-ProofRail-Consumption'])
def test_each_header_is_required(enforced, missing):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    status, reply = direct(enforced, *credentials(enforced, envelope), key='e' * 64, drop=(missing,))
    assert (status, reply['error']) == (403, 'authority_header_missing_or_oversized')
    assert enforced.count() == 1


@pytest.mark.parametrize('value', ['not base64 at all!', base64.b64encode(b'[1, 2]').decode(),
                                   base64.b64encode(b'{"unterminated": ').decode()])
def test_undecodable_header_is_refused(enforced, value):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    _, receipt = credentials(enforced, envelope)
    status, reply = post(enforced, 'tenant-a', dict(envelope['effect']['parameters']),
                         {'Idempotency-Key': envelope['record_hash'], 'X-ProofRail-Envelope': value,
                          'X-ProofRail-Consumption': pack(receipt)})
    assert (status, reply['error']) == (403, 'authority_header_invalid')


def test_envelope_without_principals_is_refused(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    authorized, receipt = credentials(enforced, envelope)
    status, reply = post(enforced, 'tenant-a', dict(authorized['effect']['parameters']),
                         {'Idempotency-Key': authorized['record_hash'], 'X-ProofRail-Envelope': pack({}),
                          'X-ProofRail-Consumption': pack(receipt)})
    assert (status, reply['error']) == (403, 'authority_principal_invalid')


def test_empty_receipt_is_refused(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    authorized, _ = credentials(enforced, envelope)
    status, reply = direct(enforced, authorized, {})
    assert (status, reply['error']) == (403, 'consumption_receipt_invalid')
    assert enforced.count() == 1


@pytest.mark.parametrize('field,value', [('max_cost', 1), ('area_id', 'another-area'),
                                         ('client_reference', 'someone-else')])
def test_body_must_equal_the_authorized_parameters(enforced, field, value):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    authorized, receipt = credentials(enforced, envelope)
    body = dict(authorized['effect']['parameters'], **{field: value})
    status, reply = direct(enforced, authorized, receipt, body=body)
    assert (status, reply['error']) == (403, 'authority_effect_mismatch')
    assert enforced.count() == 1


def test_extra_body_field_is_refused(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    authorized, receipt = credentials(enforced, envelope)
    status, reply = direct(enforced, authorized, receipt, body=dict(authorized['effect']['parameters'], rush=True))
    assert (status, reply['error']) == (403, 'authority_effect_mismatch')


def test_idempotency_key_must_be_the_authority_digest(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    status, reply = direct(enforced, *credentials(enforced, envelope), key='a' * 64)
    assert (status, reply['error']) == (403, 'authority_idempotency_mismatch')
    assert enforced.count() == 1


def test_authority_cannot_be_used_on_another_tenant_path(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    status, reply = direct(enforced, *credentials(enforced, envelope), tenant='tenant-b')
    assert (status, reply['error']) == (403, 'authority_tenant_mismatch')
    assert enforced.count() == 1


def test_receipt_must_belong_to_the_same_authority(enforced):
    """Two legitimately admitted cases; their receipts are not interchangeable."""
    _, _, _, first = approve(enforced)
    enforced.p.admit('tenant-a', first)
    _, _, _, second = approve(enforced)
    enforced.p.admit('tenant-a', second)
    envelope_1, _ = credentials(enforced, first)
    _, receipt_2 = credentials(enforced, second)
    status, reply = direct(enforced, envelope_1, receipt_2, key=envelope_1['record_hash'])
    assert (status, reply['error']) == (403, 'consumption_receipt_scope_mismatch')
    assert enforced.count() == 2


def test_another_tenants_receipt_is_not_trusted_for_this_authority(enforced):
    _, _, _, mine = approve(enforced, 'a')
    enforced.p.admit('tenant-a', mine)
    _, _, _, theirs = approve(enforced, 'b')
    enforced.p.admit('tenant-b', theirs)
    envelope_a, _ = credentials(enforced, mine, 'a')
    _, receipt_b = credentials(enforced, theirs, 'b')
    status, reply = direct(enforced, envelope_a, receipt_b)
    assert (status, reply['error']) == (403, 'consumption_gateway_key_untrusted')


# ------------------------------------------------------------------ refusals: trust and time

@pytest.mark.parametrize('drop,expected', [('gateways', 'authority_untrusted_principal'),
                                           ('issuers', 'authority_untrusted_principal')])
def test_provider_trusts_only_its_own_roster(enforced, drop, expected):
    problem, plan, approval, envelope = approve(enforced)
    enforced.restart(roster(enforced.w, **{drop: False}))
    result = enforced.p.admit('tenant-a', envelope)    # the provider refuses; nothing to reconcile
    assert result['authority_state'] != 'RECONCILED' and enforced.count() == 0
    stored = credentials(enforced, envelope)
    status, reply = direct(enforced, *stored)
    assert (status, reply['error']) == (403, expected)


def test_roster_scoped_to_another_tenant_is_refused(enforced):
    problem, plan, approval, envelope = approve(enforced)
    enforced.restart(roster(enforced.w, tenants=('b',)))
    result = enforced.p.admit('tenant-a', envelope)
    assert result['authority_state'] != 'RECONCILED' and enforced.count() == 0
    status, reply = direct(enforced, *credentials(enforced, envelope))
    assert (status, reply['error']) == (403, 'authority_tenant_mismatch') or \
        (status, reply['error']) == (403, 'authority_untrusted_principal')


def test_expired_authority_is_refused(enforced):
    """Same legitimately issued pair, judged at a time after its expiry."""
    import provider_authority
    problem, plan, approval, envelope = approve(enforced)
    enforced.p.admit('tenant-a', envelope)
    authorized, receipt = credentials(enforced, envelope)
    headers = {'X-ProofRail-Envelope': pack(authorized), 'X-ProofRail-Consumption': pack(receipt)}
    body = dict(authorized['effect']['parameters'])
    trusted = roster(enforced.w)
    expiry = datetime.fromisoformat(authorized['expires_at'].replace('Z', '+00:00'))
    assert provider_authority.authorize_create('tenant-a', authorized['record_hash'], body, headers, trusted,
                                               now=expiry - timedelta(seconds=1))
    with pytest.raises(provider_authority.ProviderAuthorityError) as exc:
        provider_authority.authorize_create('tenant-a', authorized['record_hash'], body, headers, trusted,
                                            now=expiry)
    assert exc.value.reason == 'authority_envelope_invalid'


# ------------------------------------------------------------------ known gap

@pytest.mark.xfail(strict=True, reason=(
    'GAP: the gateway signs the consumption receipt BEFORE its post-consumption re-check. '
    'When that re-check aborts admission (revocation, role change), the stored envelope and '
    'receipt still form a valid pair, and a holder can present it directly to the enforcing '
    'provider within the validity window. Fix: sign the provider-facing token only after the '
    're-check passes, or bind it to the gateway connection.'))
def test_authority_the_gateway_aborted_cannot_be_used_directly(enforced, monkeypatch):
    problem, plan, approval, envelope = approve(enforced)
    gateway = enforced.p.gateways['tenant-a']
    real = gateway._consume

    def revoke_then_consume(e):
        enforced.p.revoke_approval(enforced.w['admin-a'], 'tenant-a', approval['approval_id'])
        return real(e)
    monkeypatch.setattr(gateway, '_consume', revoke_then_consume)
    with pytest.raises(PilotError) as exc:
        enforced.p.admit('tenant-a', envelope)
    assert exc.value.reason == 'state_changed_during_admission'
    assert enforced.count() == 0
    status, reply = direct(enforced, *credentials(enforced, envelope))
    assert status == 403, reply                    # currently 201: the provider creates the order
    assert enforced.count() == 0
