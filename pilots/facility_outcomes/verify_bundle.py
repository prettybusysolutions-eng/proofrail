"""Verify a facility case bundle offline, reporting each claim dimension separately.

    python verify_bundle.py BUNDLE [--trusted-keys keys.json] [--json]

Exit 0 only if integrity, authenticity, authority validity and provider-observed
execution all pass. The physical outcome is reported as what the verdict states
and whether it reproduces from the included observations; a signature is never
presented as proof that the physical event occurred.

--trusted-keys: a JSON object {principal_id: base64 public key} obtained
independently of the bundle. Without it, key trust is 'self_asserted'.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from proofrail.envelope import verify_action_authority_envelope  # noqa: E402

import outcome_verifier  # noqa: E402
from policy import approval_digest, evidence_root, plan_digest  # noqa: E402
from proofrail_gateway import ACTION_TYPE, expected_parameters, success_predicate, work_order_target  # noqa: E402
from records import PilotError, Registry, decode_public, digest, utc  # noqa: E402
from store import verify_chain  # noqa: E402


class Report:
    def __init__(self):
        self.dimensions = {}

    def check(self, dimension, name, ok, detail=''):
        self.dimensions.setdefault(dimension, []).append({'check': name, 'result': 'PASS' if ok else 'FAIL',
                                                          'detail': '' if ok else detail})
        return ok

    def passed(self, dimension):
        return bool(self.dimensions.get(dimension)) and all(c['result'] == 'PASS' for c in self.dimensions[dimension])


def load(root, rel):
    return json.loads((root / rel).read_text())


def many(root, folder):
    d = root / 'records' / folder
    return [json.loads(p.read_text()) for p in sorted(d.glob('*.json'))] if d.exists() else []


def integrity(root, r):
    listed = {}
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        value, name = line.split('  ', 1)
        listed[name] = value
    present = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} - {'SHA256SUMS'}
    r.check('integrity', 'no missing or unlisted files', present == set(listed),
            f'missing={sorted(set(listed) - present)} unlisted={sorted(present - set(listed))}')
    bad = [n for n, v in listed.items() if (root / n).is_file() and hashlib.sha256((root / n).read_bytes()).hexdigest() != v]
    r.check('integrity', 'every file matches SHA256SUMS', not bad, ', '.join(bad))
    manifest = load(root, 'manifest.json')
    r.check('integrity', 'manifest lists the same digests', all(
        listed.get(n) == v for n, v in manifest['files'].items()) and set(manifest['files']) == set(listed) - {'manifest.json'})
    r.check('integrity', 'bundle format recognised', manifest.get('format') == 'wrn.case-bundle.v1')
    return manifest


def verify(root: Path, trusted: dict | None = None) -> dict:
    r = Report()
    manifest = integrity(root, r)
    tenant = manifest['tenant_id']
    problem, plan, approval = load(root, 'records/problem.json'), load(root, 'records/plan.json'), \
        load(root, 'records/approval.json')
    envelope, reference = load(root, 'records/envelope.json'), load(root, 'records/authority_reference.json')
    consumption = load(root, 'records/consumption.json')
    identity_then = load(root, 'context/identity-at-admission.json')
    identity_now = load(root, 'context/identity-at-export.json')
    policy = load(root, 'context/policy-at-admission.json')
    state_inputs = load(root, 'context/state-inputs-at-admission.json')
    observations, verdicts = many(root, 'observations'), many(root, 'verdicts')
    acceptances, invoices, settlements = many(root, 'acceptances'), many(root, 'invoices'), many(root, 'settlements')

    # ---- 2. authenticity
    snapshot = identity_now
    key_trust = 'self_asserted'
    if trusted is not None:
        key_trust = 'trusted'
        for p in snapshot['principals']:
            r.check('authenticity', f"key of {p['principal_id']} matches the independently trusted key",
                    trusted.get(p['principal_id']) == p['public_key'], 'untrusted or different key')
    registry = Registry.from_snapshot(snapshot)
    required = [('problem', problem, 'problem_reviewer'), ('approval', approval, 'approver')]
    required += [(f"observation {o['observation_id']}", o, {'provider_work_order_state': 'provider_observer',
                                                             'completion_claim': 'contractor',
                                                             'inspection': 'inspector'}[o['observation_type']])
                 for o in observations]
    required += [(f"verdict {v['outcome_id']}", v, 'outcome_reviewer') for v in verdicts]
    required += [(f"acceptance {a['acceptance_id']}", a, 'buyer') for a in acceptances]
    required += [(f"invoice {i['invoice_id']}", i, 'provider') for i in invoices]
    required += [(f"settlement {s['settlement_id']}", s, 'settlement_authorizer') for s in settlements]
    for name, record, role in required:
        try:
            registry.signer(record, role=role, tenant_id=tenant)
            r.check('authenticity', f'{name} signed by a registered {role}', True)
        except PilotError as exc:
            r.check('authenticity', f'{name} signed by a registered {role}', False, exc.reason)
    r.check('authenticity', 'audit chain intact from genesis (tail truncation is not detectable)',
            verify_chain(load(root, 'audit/chain.json')))

    # ---- 3. authority validity
    issuer = next((p for p in identity_then['principals'] if 'authority_issuer' in p['roles']), None)
    r.check('authority', 'issuer present in the admission-time identity snapshot', issuer is not None)
    params = expected_parameters(problem, plan, approval, envelope['envelope_id'])
    roots = {'identity': digest(identity_then), 'evidence': evidence_root(problem['evidence_refs']),
             'policy': digest(policy), 'state': digest(state_inputs)}
    r.check('authority', 'state inputs describe these records at admission',
            state_inputs['problem_digest'] == digest(problem) and state_inputs['plan_digest'] == plan['plan_digest']
            and state_inputs['approval_digest'] == approval['approval_digest']
            and state_inputs['work_state'] == 'APPROVED' and state_inputs['approval_revoked'] is False)
    r.check('authority', 'plan and approval digests recompute',
            plan['plan_digest'] == plan_digest(plan) and approval['approval_digest'] == approval_digest(approval)
            and approval['approved_plan_digest'] == plan['plan_digest'])
    try:
        verify_action_authority_envelope(envelope, public_key=decode_public(issuer['public_key']), expected_roots=roots,
                                         expected_approval_digest=approval['approval_digest'], action_type=ACTION_TYPE,
                                         target=work_order_target(params), parameters=params,
                                         now=utc(envelope['issued_at']))
        r.check('authority', 'envelope signature, roots, approval and exact effect (ProofRail verifier)', True)
    except Exception as exc:
        r.check('authority', 'envelope signature, roots, approval and exact effect (ProofRail verifier)', False,
                getattr(exc, 'code', type(exc).__name__))
    r.check('authority', 'issuer is the tenant authority issuer acting as verifier',
            issuer is not None and envelope['issuer'] == {'principal_id': issuer['principal_id'], 'role': 'verifier'}
            and envelope['signature']['key_id'] == issuer['key_id'])
    r.check('authority', 'success predicate binds the exact parameters',
            envelope['observation_contract']['success_predicate_digest'] == success_predicate(params))
    claim = consumption['claim']
    r.check('authority', 'consumed once in the ProofRail replay registry, by the named executor',
            claim['permit_hash'] == envelope['record_hash'] and claim['nonce'] == envelope['nonce']
            and claim['executor_id'] == envelope['subject']['principal_id']
            and [e['state'] for e in consumption['events']] == ['EXECUTING', 'CONSUMED'])
    r.check('authority', 'consumed within the envelope validity window',
            utc(envelope['issued_at']) <= utc(claim['consumed_at']) < utc(envelope['expires_at']))

    # ---- 4. provider-observed execution
    recon = next((o for o in observations if o['record_hash'] == reference['reconciliation_reference']), None)
    r.check('execution', 'authority reference is RECONCILED', reference['authority_state'] == 'RECONCILED',
            reference['authority_state'])
    r.check('execution', 'reconciling observation is included', recon is not None)
    if recon is not None:
        seen = recon['findings']['work_order']
        orders = seen.get('orders') or []
        exact = [o for o in orders if o.get('tenant_id') == tenant and
                 all(o.get(k) == v for k, v in params.items() if k != 'tenant_id')]
        r.check('execution', 'observation digest matches its findings', recon['observation_digest'] == digest(recon['findings']))
        r.check('execution', 'exactly one provider order matching every authorized parameter',
                seen.get('readable') is True and len(orders) == 1 and len(exact) == 1)
        r.check('execution', 'the matching order is the one the reference names',
                bool(exact) and exact[0]['work_order_id'] == reference['provider_operation_reference'])

    # ---- 5. attested physical outcome (reported, not "proven")
    outcome = {'stated': None, 'reproduced': None, 'buyer_decision': None, 'settlement': None}
    if verdicts:
        latest = verdicts[-1]
        outcome['stated'] = latest['assessment_state']
        provider_org = policy['approved_providers'][plan['provider_id']]['organization']
        contractors = {p['principal_id'] for p in identity_now['principals']
                       if p['organization'] == provider_org and set(p['roles']) & {'contractor', 'provider'}}
        reviewer = registry.get(latest['reviewer_principal'])

        class _Reviewer:                     # recompute only; never signs
            principal = reviewer

            @staticmethod
            def sign(record):
                return {**record, 'record_hash': 'f' * 64,
                        'signature': {'algorithm': 'ed25519', 'key_id': 'verify-only', 'value': 'A' * 88}}
        try:
            redo = outcome_verifier.assess(
                _Reviewer, registry=registry, tenant_id=tenant, problem=problem, plan=plan,
                authority={'reference': reference, 'envelope': envelope}, observations=observations,
                provider_organization=provider_org, contractors=contractors,
                grace_hours=policy['inspection_grace_hours'], policy_digest=latest['assessment_policy_digest'],
                now=utc(latest['assessment_time']))
            outcome['reproduced'] = redo['assessment_state']
            r.check('outcome', 'verdict reproduces from the included observations',
                    redo['assessment_state'] == latest['assessment_state']
                    and redo['criteria_results'] == latest['criteria_results'],
                    f"bundle says {latest['assessment_state']}, recomputed {redo['assessment_state']}")
        except PilotError as exc:
            r.check('outcome', 'verdict reproduces from the included observations', False, exc.reason)
        bound = [a for a in acceptances if a['outcome_digest'] == latest['record_hash']]
        outcome['buyer_decision'] = bound[-1]['decision'] if bound else None
    if settlements:
        outcome['settlement'] = {'status': settlements[-1]['authorization_status'],
                                 'money_moved': settlements[-1]['money_moved']}
        r.check('outcome', 'settlement is simulated (no money moved)', all(s['money_moved'] is False for s in settlements))
    required_dims = ('integrity', 'authenticity', 'authority', 'execution')
    return {'bundle': str(root), 'key_trust': key_trust,
            'verified': all(r.passed(d) for d in required_dims) and (not r.dimensions.get('outcome') or r.passed('outcome')),
            'dimensions': {d: {'result': 'PASS' if r.passed(d) else 'FAIL', 'checks': c} for d, c in r.dimensions.items()},
            'physical_outcome': {**outcome, 'nature': 'attested by a buyer-designated inspector under recorded rules; '
                                                      'not physical proof'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--trusted-keys', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    trusted = json.loads(args.trusted_keys.read_text()) if args.trusted_keys else None
    try:
        report = verify(args.bundle.resolve(), trusted)
    except Exception as exc:  # malformed bundle: a failure, never a crash or a pass
        report = {'bundle': str(args.bundle), 'verified': False, 'error': type(exc).__name__ + ': ' + str(exc)[:200]}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name, dim in report.get('dimensions', {}).items():
            print(f"{dim['result']:4}  {name}")
            for c in dim['checks']:
                print(f"        {c['result']:4} {c['check']}" + (f"  [{c['detail']}]" if c['detail'] else ''))
        if 'physical_outcome' in report:
            print('physical outcome:', json.dumps(report['physical_outcome']))
        print('key trust:', report.get('key_trust'), '| VERIFIED' if report['verified'] else '| NOT VERIFIED',
              report.get('error', ''))
    return 0 if report['verified'] else 1


if __name__ == '__main__':
    sys.exit(main())
