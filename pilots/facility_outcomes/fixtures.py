"""Deterministic synthetic world: two tenants, one provider, independent inspectors.

All names are fictional. Keys are generated per run and prove only the test
identities they create. Evidence files are synthetic bytes identified by digest.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pilot import FacilityPilot
from records import Clock, stamp

HERE = Path(__file__).resolve().parent
START = datetime(2026, 10, 23, 13, 0, 0, tzinfo=timezone.utc)
PROVIDER_ID = 'P-014'
PROVIDER_ORG = 'clearpath-facility-services'
CRITERIA = [
    {'criterion_id': 'C1', 'description': 'Staging zone floor clear of cardboard and packaging debris',
     'check': 'area_clear_of_debris'},
    {'criterion_id': 'C2', 'description': 'No damage to racking, marking or fixtures in the zone',
     'check': 'no_damage_to_fixtures'},
]
ALL_MET = {'C1': 'met', 'C2': 'met'}


def policy_doc(**overrides) -> dict:
    doc = {'allowed_problem_types': ['non_hazardous_debris'], 'allowed_risk_classes': ['non_hazardous'],
           'currency': 'USD', 'max_work_order_cost': 50000, 'max_approval_validity_hours': 72,
           'inspection_grace_hours': 24,
           'approved_providers': {PROVIDER_ID: {'organization': PROVIDER_ORG}}}
    doc.update(overrides)
    return doc


def evidence(name: str, *, facility: str, area: str, captured_at: datetime, by: str, media='image/jpeg') -> dict:
    return {'ref': name, 'sha256': hashlib.sha256(name.encode()).hexdigest(), 'media_type': media,
            'captured_at': stamp(captured_at), 'captured_by': by, 'facility_id': facility, 'area_id': area}


def start_provider(workdir: Path, port: int = 0):
    """Run the simulator as its own process with its own store; return (process, base_url)."""
    workdir.mkdir(parents=True, exist_ok=True)
    port_file = workdir / 'provider.port'
    port_file.unlink(missing_ok=True)
    proc = subprocess.Popen([sys.executable, '-I', str(HERE / 'provider_simulator.py'),
                             '--db', str(workdir / 'provider.sqlite3'), '--port-file', str(port_file),
                             '--port', str(port)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(200):
        if port_file.exists() and port_file.read_text().strip():
            return proc, 'http://127.0.0.1:' + port_file.read_text().strip()
        if proc.poll() is not None:
            raise RuntimeError('provider simulator exited: ' + proc.stderr.read().decode()[-400:])
        time.sleep(0.05)
    proc.kill()
    raise RuntimeError('provider simulator did not start')


class World:
    """Principals, designations and policy for tenants 'tenant-a' (Northside) and 'tenant-b' (Harbor)."""

    def __init__(self, workdir: Path, provider_url: str, *, clock: Clock | None = None, provider_timeout=5.0):
        self.clock = clock or Clock(START)
        self.pilot = FacilityPilot(workdir, self.clock, provider_url, provider_timeout=provider_timeout)
        r = self.pilot.registry
        self.ids = {}
        for tenant, org in (('tenant-a', 'northside-logistics'), ('tenant-b', 'harbor-distribution')):
            t = tenant[-1]
            add = lambda name, roles, organization=org: self.ids.__setitem__(
                f'{name}-{t}', r.add(f'{name}-{t}', tenant_id=tenant, organization=organization, roles=roles))
            add('reporter', {'reporter'})
            add('reviewer', {'problem_reviewer'})
            add('planner', {'planner'})
            add('approver', {'approver'})
            add('admin', {'tenant_admin'})
            add('buyer', {'buyer'})
            add('qa', {'outcome_reviewer'})
            add('finance', {'settlement_authorizer'})
            add('issuer', {'authority_issuer'}, organization='proofrail-authority-' + t)
            add('gateway', {'gateway'}, organization='proofrail-gateway-' + t)
            add('observer', {'provider_observer'}, organization='proofrail-observer-' + t)
            add('contractor', {'contractor'}, organization=PROVIDER_ORG)
            add('billing', {'provider'}, organization=PROVIDER_ORG)
            add('inspector', {'inspector'}, organization='independent-inspections-llc')
            add('inspector2', {'inspector'}, organization='second-opinion-inspections')
            add('provider-inspector', {'inspector'}, organization=PROVIDER_ORG)   # not independent
            for name in ('inspector', 'inspector2', 'provider-inspector'):
                r.designate_inspector(tenant_id=tenant, facility_id='FAC-' + t.upper() + '1',
                                      inspector_id=f'{name}-{t}', by=self.ids[f'buyer-{t}'])
            self.pilot.install_tenant(tenant, issuer=self.ids[f'issuer-{t}'], gateway=self.ids[f'gateway-{t}'],
                                      observer=self.ids[f'observer-{t}'], policy=policy_doc())

    def __getitem__(self, name):
        return self.ids[name]

    # ------------------------------------------------------------------ the happy path, step by step
    def report(self, t='a', area='ZONE-STAGING-3'):
        facility = 'FAC-' + t.upper() + '1'
        refs = [evidence(f'report-photo-{t}-{area}', facility=facility, area=area,
                         captured_at=self.clock.now() - timedelta(minutes=30), by=f'reporter-{t}')]
        problem = self.pilot.submit_problem(self[f'reporter-{t}'], f'tenant-{t}', facility_id=facility, area_id=area,
                                            description='Cardboard and non-hazardous packaging debris in staging zone',
                                            evidence_refs=refs)
        return self.pilot.confirm_problem(self[f'reviewer-{t}'], f'tenant-{t}', problem['problem_id'])

    def plan_and_approve(self, problem, t='a', quote=32000, cap=35000):
        plan = self.pilot.propose_plan(self[f'planner-{t}'], f'tenant-{t}', problem['problem_id'],
                                       provider_id=PROVIDER_ID, quote=quote, criteria=CRITERIA)
        approval = self.pilot.approve(self[f'approver-{t}'], f'tenant-{t}', plan['plan_id'], maximum_cost=cap)
        return plan, approval

    def authorize(self, problem, plan, approval, t='a'):
        return self.pilot.request_authority(f'tenant-{t}', problem_id=problem['problem_id'], plan_id=plan['plan_id'],
                                            approval_id=approval['approval_id'])

    def inspection_refs(self, t='a', area='ZONE-STAGING-3', name='inspection-photo'):
        return [evidence(f'{name}-{t}-{self.clock.text()}', facility='FAC-' + t.upper() + '1', area=area,
                         captured_at=self.clock.now(), by=f'inspector-{t}')]


# ---------------------------------------------------------------------- persistence for multi-process tests

def save_world(world: 'World', path: Path) -> None:
    """Write the synthetic world (including TEST private keys) to a 0600 file inside the workdir."""
    import json, os
    from cryptography.hazmat.primitives import serialization
    data = {'workdir': str(world.pilot.workdir), 'now': world.clock.text(),
            'provider_timeout': world.pilot.provider_timeout,
            'principals': [{**ident.principal.describe(), 'private_hex': ident.private_key.private_bytes(
                serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()}
                for ident in world.ids.values()],
            'designations': world.pilot.registry.designations(),
            'policies': {t: world.pilot.policy.doc(t) for t in ('tenant-a', 'tenant-b')}}
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream)


def load_world(path: Path, provider_url: str, *, provider_timeout: float | None = None) -> 'World':
    import json
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from records import Principal, utc
    data = json.loads(Path(path).read_text())
    world = World.__new__(World)
    world.clock = Clock(utc(data['now']))
    world.pilot = FacilityPilot(Path(data['workdir']), world.clock, provider_url,
                                provider_timeout=provider_timeout or data['provider_timeout'])
    world.ids = {}
    for p in data['principals']:
        principal = Principal(p['principal_id'], p['tenant_id'], p['organization'], frozenset(p['roles']),
                              p['key_id'], p['public_key'])
        world.ids[p['principal_id']] = world.pilot.registry.adopt(
            principal, Ed25519PrivateKey.from_private_bytes(bytes.fromhex(p['private_hex'])))
    world.pilot.registry.restore_designations(data['designations'])
    for t in ('a', 'b'):
        world.pilot.install_tenant(f'tenant-{t}', issuer=world.ids[f'issuer-{t}'], gateway=world.ids[f'gateway-{t}'],
                                   observer=world.ids[f'observer-{t}'],
                                   policy={k: v for k, v in data['policies'][f'tenant-{t}'].items() if k != 'tenant_id'})
    return world
