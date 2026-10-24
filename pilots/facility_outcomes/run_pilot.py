"""Run the five handoff demonstrations end to end and export verifiable evidence.

    python pilots/facility_outcomes/run_pilot.py --out /tmp/wrn-pilot

Each scenario gets a fresh provider simulator process and fresh stores. The output
directory holds summary.json (per-scenario claims and provider side-effect
counts) and an evidence bundle for scenarios A and D, each verified offline with
verify_bundle.py. Synthetic data only; no network beyond 127.0.0.1; no money moves.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from evidence_export import export_case, source_commit  # noqa: E402
from fixtures import ALL_MET, World, start_provider  # noqa: E402
from records import PilotError  # noqa: E402
from verify_bundle import verify  # noqa: E402


def count(url):
    return json.load(urllib.request.urlopen(url + '/admin/count', timeout=5))['count']


def arm(url, mode, seconds=0):
    request = urllib.request.Request(url + '/admin/fault', method='POST', headers={'Content-Type': 'application/json'},
                                     data=json.dumps({'mode': mode, 'seconds': seconds}).encode())
    urllib.request.urlopen(request, timeout=5).read()


def refusal(fn):
    try:
        fn()
        return None
    except PilotError as exc:
        return exc.reason


def prepare(w):
    problem = w.report()
    plan, approval = w.plan_and_approve(problem)
    return problem, plan, approval, w.authorize(problem, plan, approval)


def through_work(w, envelope, problem):
    result = w.pilot.admit('tenant-a', envelope)
    w.clock.advance(hours=3)
    w.pilot.claim_completion(w['contractor-a'], 'tenant-a', problem['problem_id'], evidence_refs=[])
    w.clock.advance(hours=1)
    return result


def scenario_a(w, url, out):
    problem, plan, approval, envelope = prepare(w)
    pid, p = problem['problem_id'], w.pilot
    result = through_work(w, envelope, problem)
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria=ALL_MET, evidence_refs=w.inspection_refs())
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    acceptance = p.buyer_decide(w['buyer-a'], 'tenant-a', pid, decision='ACCEPTED', reason='Zone clear on inspection')
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=32000)
    settlement = p.settle(w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    learning = p.learning_record('tenant-a', pid, area_type='staging_zone', debris_volume_class='medium', shareable=True)
    bundle = export_case(w['buyer-a'], p, 'tenant-a', pid, out / 'bundle-A')
    report = verify(bundle)
    return {'execution': result['authority_state'], 'outcome': verdict['assessment_state'],
            'buyer': acceptance['decision'], 'settlement': settlement['authorization_status'],
            'money_moved': settlement['money_moved'], 'case_state': p.store.state('tenant-a', pid),
            'learning_causal_claim': learning['causal_claim'], 'provider_orders': count(url),
            'bundle': str(bundle), 'bundle_verified': report['verified'], 'bundle_key_trust': report['key_trust']}


def scenario_b(w, url, out):
    problem, plan, approval, envelope = prepare(w)
    w.pilot.amend_plan(w['planner-a'], 'tenant-a', plan['plan_id'], estimated_cost=34000)
    return {'change': 'quote raised after approval', 'original_authority': 'REFUSED',
            'reason': refusal(lambda: w.pilot.admit('tenant-a', envelope)), 'provider_orders': count(url)}


def scenario_c(w, url, out):
    problem, plan, approval, envelope = prepare(w)
    first = w.pilot.admit('tenant-a', envelope)['authority_state']
    return {'first_admission': first, 'replay': refusal(lambda: w.pilot.admit('tenant-a', envelope)),
            'provider_orders': count(url)}


def scenario_d(w, url, out):
    problem, plan, approval, envelope = prepare(w)
    pid, p = problem['problem_id'], w.pilot
    result = through_work(w, envelope, problem)
    claim_only = p.assess(w['qa-a'], 'tenant-a', pid)['assessment_state']
    p.submit_inspection(w['inspector-a'], 'tenant-a', pid, criteria={'C1': 'not_met', 'C2': 'met'},
                        evidence_refs=w.inspection_refs())
    verdict = p.assess(w['qa-a'], 'tenant-a', pid)
    invoice = p.submit_invoice(w['billing-a'], 'tenant-a', work_order_id=result['work_order_id'], amount=32000)
    settlement = p.settle(w['finance-a'], 'tenant-a', pid, invoice_id=invoice['invoice_id'])
    bundle = export_case(w['qa-a'], p, 'tenant-a', pid, out / 'bundle-D')
    report = verify(bundle)
    return {'execution': result['authority_state'], 'outcome_with_claim_only': claim_only,
            'outcome_after_inspection': verdict['assessment_state'], 'settlement': settlement['authorization_status'],
            'settlement_reasons': settlement['denial_reasons'], 'provider_orders': count(url),
            'bundle': str(bundle), 'bundle_verified': report['verified'],
            'bundle_physical_outcome': report['physical_outcome']['stated']}


def scenario_e(w, url, out):
    problem, plan, approval, envelope = prepare(w)
    gateway = w.pilot.gateways['tenant-a']
    arm(url, 'drop_without_effect')
    first = w.pilot.admit('tenant-a', envelope)
    after_reconcile = w.pilot.reconcile('tenant-a', envelope['envelope_id'])['authority_state']
    return {'provider_outcome': first['provider_outcome'], 'authority': first['authority_state'],
            'after_read_only_reconcile': after_reconcile,
            'second_admission': refusal(lambda: w.pilot.admit('tenant-a', envelope)),
            'provider_create_calls': gateway.provider_calls, 'provider_orders': count(url)}


SCENARIOS = {'A authorized success': scenario_a, 'B changed scope': scenario_b, 'C replay': scenario_c,
             'D false completion': scenario_d, 'E ambiguous external operation': scenario_e}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    results = {}
    for name, fn in SCENARIOS.items():
        tag = name.split()[0]
        proc, url = start_provider(out / 'work' / tag / 'provider')
        try:
            world = World(out / 'work' / tag / 'pilot', url, provider_timeout=1.0)
            results[name] = fn(world, url, out)
        finally:
            proc.kill()
            proc.wait()
        print(f'[{name}] ' + json.dumps({k: v for k, v in results[name].items() if k != 'bundle'}))
    expected = {
        'A authorized success': lambda r: r['execution'] == 'RECONCILED' and r['outcome'] == 'VERIFIED'
        and r['settlement'] == 'SIMULATED_AUTHORIZED' and r['money_moved'] is False and r['provider_orders'] == 1
        and r['bundle_verified'],
        'B changed scope': lambda r: r['reason'] == 'state_root_changed' and r['provider_orders'] == 0,
        'C replay': lambda r: r['first_admission'] == 'RECONCILED' and r['replay'] == 'permit_replayed'
        and r['provider_orders'] == 1,
        'D false completion': lambda r: r['execution'] == 'RECONCILED' and r['outcome_after_inspection'] == 'REJECTED'
        and r['settlement'] == 'DENIED' and r['bundle_verified'] and r['bundle_physical_outcome'] == 'REJECTED',
        'E ambiguous external operation': lambda r: r['authority'] == 'EXECUTION_UNKNOWN'
        and r['after_read_only_reconcile'] == 'EXECUTION_UNKNOWN' and r['second_admission'] is not None
        and r['provider_create_calls'] == 1 and r['provider_orders'] == 0,
    }
    verdicts = {name: ('PASS' if expected[name](r) else 'FAIL') for name, r in results.items()}
    (out / 'summary.json').write_text(json.dumps({
        'kind': 'wrn.facility-pilot-demonstration.v1', 'source_commit': source_commit(HERE),
        'note': 'Synthetic, local, author-run. INDEPENDENT VALIDATION: NOT COMPLETED.',
        'results': results, 'verdicts': verdicts}, indent=2, sort_keys=True) + '\n')
    for name, v in verdicts.items():
        print(f'{v:4}  {name}')
    return 0 if all(v == 'PASS' for v in verdicts.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
