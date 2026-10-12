"""Offline evidence integrity comparison; not a human audit-effort study.

Baseline: Ed25519 signature over a SHA-256 digest of exact JSONL bytes.
ProofRail: exported hash-chain ledger and signed Merkle checkpoint.
Both receive the same externally supplied public key and optional latest digest.
Fresh child processes receive public verification material only. No private keys
are written to disk. This is same-machine replication, not independent review.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from proofrail.checkpoint import create_checkpoint, export_ledger, verify_checkpoint
from proofrail.core import digest_ledger_entry


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_records(path, count=100, false_claim=False):
    records, previous = [], 'GENESIS'
    for i in range(count):
        record = {'sequence': i + 1, 'previous_hash': previous,
                  'event': 'merge', 'provider_confirmed': not false_claim,
                  'claimed_success': True, 'operation_id': str(i)}
        record['entry_hash'] = digest_ledger_entry(record)
        previous = record['entry_hash']
        records.append(record)
    path.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))


def sign_pair(root, source, key, name):
    ledger = root / (name + '.jsonl')
    export_ledger(source, ledger)
    data = ledger.read_bytes()
    return data, {
        'conventional': {'sha256': sha(data),
                         'signature': base64.b64encode(key.sign(bytes.fromhex(sha(data)))).decode()},
        'proofrail': create_checkpoint(ledger, private_key=key, key_id='fixture-checkpoint')}


def worker(args):
    # Integrity verification uses local files only; no provider credentials/API.
    key = Ed25519PublicKey.from_public_bytes(Path(args.key).read_bytes())
    manifest = json.loads(Path(args.manifest).read_text())
    start = perf_counter()
    try:
        if args.path_kind == 'conventional':
            data = Path(args.ledger).read_bytes()
            digest = sha(data)
            key.verify(base64.b64decode(manifest['signature']), bytes.fromhex(digest))
            valid = manifest['sha256'] == digest
        else:
            valid = verify_checkpoint(manifest, args.ledger, public_key=key)['valid']
        if args.pin:
            valid = valid and sha(Path(args.ledger).read_bytes()) == Path(args.pin).read_text().strip()
        error = None
    except Exception as exc:
        valid, error = False, type(exc).__name__
    print(json.dumps({'integrity_accepted': valid, 'error': error,
                      'verify_ms': (perf_counter() - start) * 1000}))


def run():
    key, wrong = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        public = root / 'trusted-public.key'
        public.write_bytes(key.public_key().public_bytes_raw())
        source = root / 'source.jsonl'
        write_records(source)
        data, manifests = sign_pair(root, source, key, 'full')
        write_records(source, count=50)
        old, old_manifests = sign_pair(root, source, key, 'old')
        write_records(source, false_claim=True)
        false, false_manifests = sign_pair(root, source, key, 'false')
        forged, forged_manifests = sign_pair(root, source, wrong, 'forged')
        pin = root / 'retained-latest-digest.txt'
        pin.write_text(sha(data))
        lines = data.splitlines(keepends=True)
        broken = copy.deepcopy(manifests)
        broken['conventional']['signature'] = base64.b64encode(b'\0' * 64).decode()
        broken['proofrail']['signature']['value'] = base64.urlsafe_b64encode(b'\0' * 64).decode().rstrip('=')
        cases = [
            ('authentic', data, manifests, True, False, 'integrity'),
            ('altered', data.replace(b'"operation_id": "0"', b'"operation_id": "x"', 1), manifests, False, False, 'integrity'),
            ('tail_deleted', b''.join(lines[:-1]), manifests, False, False, 'integrity'),
            ('reordered', b''.join(reversed(lines)), manifests, False, False, 'integrity'),
            ('duplicated', data + lines[-1], manifests, False, False, 'integrity'),
            ('signature_corrupted', data, broken, False, False, 'integrity'),
            ('attacker_signed_replacement', forged, forged_manifests, False, False, 'integrity'),
            ('old_valid_bundle_without_freshness', old, old_manifests, True, False, 'known_limit'),
            ('old_bundle_with_retained_latest_digest', old, old_manifests, False, True, 'freshness_with_external_pin'),
            ('signed_false_claim', false, false_manifests, True, False, 'known_limit')]
        results = []
        script = Path(__file__).resolve()
        for label, payload, pair, expected, pinned, classification in cases:
            ledger = root / 'candidate.jsonl'
            ledger.write_bytes(payload)
            for path_kind in ('conventional', 'proofrail'):
                manifest = root / 'candidate-manifest.json'
                manifest.write_text(json.dumps(pair[path_kind]))
                command = [sys.executable, str(script), '--worker', '--path-kind', path_kind,
                           '--ledger', str(ledger), '--manifest', str(manifest), '--key', str(public)]
                if pinned:
                    command += ['--pin', str(pin)]
                output = subprocess.run(command, capture_output=True, text=True, check=True)
                observed = json.loads(output.stdout)
                results.append({'case': label, 'path': path_kind, 'classification': classification,
                                'expected_acceptance': expected, **observed,
                                'expected_behavior_observed': observed['integrity_accepted'] == expected})
        return {'scope': __doc__, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                'source_tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
                'harness_sha256': sha(script.read_bytes()), 'python': sys.version,
                'ledger_records': 100, 'ledger_bytes': len(data),
                'manifest_bytes': {k: len(json.dumps(v).encode()) for k,v in manifests.items()},
                'cases': results, 'valid': all(r['expected_behavior_observed'] for r in results),
                'human_audit_time_measured': False, 'independent_review': False,
                'timing_note': 'One observation per case, excludes interpreter/import startup; not a performance benchmark.',
                'limits': ['No live provider truth or causal attribution verification',
                           'No whole-product comparison or lifecycle/quorum/anchor verification',
                           'Trusted public key and latest digest supplied by harness, not a deployed trust-distribution service',
                           'Both verifiers and all fixtures authored by the same assistant']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    for field in ('path-kind', 'ledger', 'manifest', 'key', 'pin', 'output'):
        parser.add_argument('--' + field)
    args = parser.parse_args()
    if args.worker:
        worker(args)
    else:
        result = run()
        rendered = json.dumps(result, indent=2) + '\n'
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(rendered)
        else:
            print(rendered)
        sys.exit(0 if result['valid'] else 1)
