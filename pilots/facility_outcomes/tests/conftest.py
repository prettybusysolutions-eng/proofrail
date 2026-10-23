"""Shared fixtures: each test gets its own provider simulator process and stores."""
import json
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

PILOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PILOT))

from fixtures import World, start_provider  # noqa: E402


def provider_count(url):
    return json.load(urllib.request.urlopen(url + '/admin/count', timeout=5))['count']


def arm(url, mode, seconds=0):
    req = urllib.request.Request(url + '/admin/fault', data=json.dumps({'mode': mode, 'seconds': seconds}).encode(),
                                 method='POST', headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=5).read()


def set_status(url, tenant_id, work_order_id, status):
    req = urllib.request.Request(url + '/admin/status', method='POST', headers={'Content-Type': 'application/json'},
                                 data=json.dumps({'tenant_id': tenant_id, 'work_order_id': work_order_id,
                                                  'status': status}).encode())
    urllib.request.urlopen(req, timeout=5).read()


@pytest.fixture
def env(tmp_path):
    proc, url = start_provider(tmp_path / 'provider')
    try:
        world = World(tmp_path / 'pilot', url, provider_timeout=1.0)
        yield SimpleNamespace(w=world, p=world.pilot, url=url, tmp=tmp_path, proc=proc,
                              count=lambda: provider_count(url), arm=lambda m, s=0: arm(url, m, s))
    finally:
        proc.kill()
        proc.wait()


def approved(env, t='a', **kw):
    problem = env.w.report(t)
    plan, approval = env.w.plan_and_approve(problem, t, **kw)
    envelope = env.w.authorize(problem, plan, approval, t)
    return problem, plan, approval, envelope


def through_work(env, t='a'):
    """A reconciled work order with a contractor claim, ready for inspection."""
    problem, plan, approval, envelope = approved(env, t)
    result = env.p.admit(f'tenant-{t}', envelope)
    assert result['authority_state'] == 'RECONCILED'
    env.w.clock.advance(hours=3)
    env.p.claim_completion(env.w[f'contractor-{t}'], f'tenant-{t}', problem['problem_id'], evidence_refs=[])
    env.w.clock.advance(hours=1)
    return problem, plan, approval, envelope, result
