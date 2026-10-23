"""Export one case as a portable evidence bundle (no operational database needed to verify it).

Only principals of the case's tenant with an evidence role may export. The bundle
holds signed records, the ProofRail replay-registry claim for the envelope, the
admission-time identity and policy snapshots, the tenant's audit chain, a
manifest and checksums. It never holds private keys, tokens or databases.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from consumption_provenance import read_registry_claim
from records import Identity, require

EXPORT_ROLES = {'buyer', 'tenant_admin', 'outcome_reviewer', 'settlement_authorizer'}
FORMAT = 'wrn.case-bundle.v1'


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def _claim(registry_path: Path, permit_hash: str) -> dict:
    """Compatibility helper used by existing negative tests."""
    return read_registry_claim(registry_path, permit_hash)


def source_commit(directory: Path) -> str | None:
    try:
        return subprocess.run(['git', '-C', str(directory), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def export_case(actor: Identity, pilot, tenant_id: str, problem_id: str, out: Path) -> Path:
    who = actor.principal
    require(who.tenant_id == tenant_id and who.roles & EXPORT_ROLES, 'export_not_permitted')
    out = Path(out)
    require(not out.exists(), 'export_destination_exists')
    store = pilot.store
    problem = store.get(tenant_id, 'problem', problem_id)
    authorities = [a for a in store.all(tenant_id, 'authority')
                   if a['envelope']['effect']['parameters']['problem_id'] == problem_id]
    require(len(authorities) == 1, 'case_has_no_single_admitted_authority')
    authority = authorities[0]
    params = authority['envelope']['effect']['parameters']
    plan = store.get(tenant_id, 'plan', params['plan_id'])
    approval = next(a for a in store.all(tenant_id, 'approval')
                    if a['approval_digest'] == authority['envelope']['approval_digest'])
    work_order = authority['reference']['provider_operation_reference']
    envelope_id = authority['envelope']['envelope_id']
    observations = [o for o in store.all(tenant_id, 'observation')
                    if o['observed_subject']['id'] in (envelope_id, work_order)]
    verdicts = [v for v in store.all(tenant_id, 'verdict') if v['work_order_id'] == work_order]
    outcome_ids = {v['outcome_id'] for v in verdicts}
    acceptances = [a for a in store.all(tenant_id, 'acceptance') if a['outcome_id'] in outcome_ids]
    invoices = [i for i in store.all(tenant_id, 'invoice') if i['work_order_id'] == work_order]
    settlements = [s for s in store.all(tenant_id, 'settlement') if s['work_order_id'] == work_order]

    out.mkdir(parents=True)
    _write(out / 'records' / 'problem.json', problem)
    _write(out / 'records' / 'plan.json', plan)
    _write(out / 'records' / 'approval.json', approval)
    _write(out / 'records' / 'envelope.json', authority['envelope'])
    _write(out / 'records' / 'authority_reference.json', authority['reference'])
    require('consumption_attestation' in authority, 'signed_consumption_attestation_missing')
    _write(out / 'records' / 'consumption.json',
           read_registry_claim(pilot.replay_registry, authority['envelope']['record_hash']))
    _write(out / 'records' / 'consumption-attestation.json',
           authority['consumption_attestation'])
    for kind, items in (('observations', observations), ('verdicts', verdicts), ('acceptances', acceptances),
                        ('invoices', invoices), ('settlements', settlements)):
        for i, item in enumerate(items):
            _write(out / 'records' / kind / f'{i:02d}.json', item)
    _write(out / 'context' / 'identity-at-admission.json', authority['identity_snapshot'])
    _write(out / 'context' / 'identity-at-export.json', pilot.registry.snapshot(tenant_id))
    _write(out / 'context' / 'policy-at-admission.json', authority['policy_snapshot'])
    _write(out / 'context' / 'state-inputs-at-admission.json', authority['state_inputs'])
    _write(out / 'audit' / 'chain.json', store.audit_entries(tenant_id))
    (out / 'VERIFY.md').write_text(VERIFY_TEXT)
    files = sorted(p for p in out.rglob('*') if p.is_file())
    sums = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    _write(out / 'manifest.json', {
        'format': FORMAT, 'tenant_id': tenant_id, 'problem_id': problem_id, 'work_order_id': work_order,
        'exported_by': who.principal_id, 'source_commit': source_commit(Path(__file__).parent),
        'algorithms': {'canonicalization': 'RFC 8785 (rfc8785)', 'hash': 'SHA-256 over canonical JSON',
                       'signature': 'Ed25519 (proofrail.crypto.sign_record)',
                       'verifier': 'pilots/facility_outcomes/verify_bundle.py ' + FORMAT},
        'files': sums})
    files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (out / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n'
                                            for p in files))
    store.audit(tenant_id, 'case_exported', problem_id, {'by': who.principal_id})
    return out


VERIFY_TEXT = """# Verifying this case bundle

    python pilots/facility_outcomes/verify_bundle.py <bundle> [--trusted-keys keys.json]

The verifier reports five dimensions separately:

1. Integrity: every file matches SHA256SUMS and the manifest; nothing is missing or extra.
2. Authenticity: every signed record verifies under the key of the principal it names, and that
   principal holds the role the record requires. Without --trusted-keys, the keys come from the
   bundle itself (self-asserted): that shows internal consistency only, not who signed. Obtain the
   tenant's keys independently and pass them with --trusted-keys to check origin.
3. Authority validity: the ProofRail envelope was issued by the authority issuer, bound to exactly
   these records (all four roots recomputed from the included snapshots). A separately signed
   gateway attestation binds a digest of the registry rows observed after the local consumption
   commit. It authenticates the gateway's claim, NOT independently retained registry history.
   An external checkpoint or anchor remains necessary for stronger rollback-resistance claims.
4. Provider-observed execution: an independent, signed provider read found exactly one work order
   matching every authorized parameter.
5. Attested physical outcome: the verdict is reproduced from the included observations under the
   same qualification rules. This is attestation by a designated inspector, not physical proof.

Settlement in this pilot is simulated; no money moves.
"""
