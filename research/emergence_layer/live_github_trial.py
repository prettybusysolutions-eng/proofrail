"""Prepare one connector-mediated GitHub write and verify captured readback.

Run directories contain temporary private keys: never publish the directory.
Only public-evidence.json and result.json are intended for review artifacts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import time
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from proofrail.envelope import mint_action_authority_envelope
from proofrail.trust import replay_claim_exists, replay_registry_root
from acceptance_bridge import Trust, full_digest
from smatp import make_envelope, encode_public
from execution_binding import ExecutionLedger
from github_artifact import prepare_commit, verify_commit


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prepare(directory, repository, branch, parent_sha, base_tree):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    keys = {name: Ed25519PrivateKey.generate() for name in ('sender', 'issuer', 'consumer', 'observer')}
    private = {name: key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
               serialization.NoEncryption()).hex() for name, key in keys.items()}
    fd = os.open(directory / 'private.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(private, stream)
    now = int(time.time())
    params = dict(repository=repository, branch=branch, parent_sha=parent_sha,
                  base_tree=base_tree, path='evidence/emergence-live-artifact.json')
    payload = 'Emergence live GitHub artifact: exact authorized bytes, one consumed execution.'
    task = {'artifact': payload}
    roots = {name: full_digest({'trial_root': name, 'repository': repository})
             for name in ('identity', 'evidence', 'policy', 'state')}
    approval = full_digest({'operator_authorization': 'Dedicated reversible trial branch artifact', **params})
    contract = dict(kind='emergence.acceptance.v1', tenant='prettybusysolutions-eng',
        task_id='github-trial-' + secrets.token_hex(8), sender='requester', recipient='executor',
        capability='publish-artifact', task_digest=full_digest(task), action_type='github_artifact_commit',
        target='github:' + repository + ':' + branch + ':' + params['path'], parameters=params,
        expected_sha256=hashlib.sha256(payload.encode()).hexdigest(), observer='github-connector-readback',
        observer_key_id='observer-key', max_observation_age_seconds=3600)
    authority = mint_action_authority_envelope(roots=roots, approval_digest=approval,
        action_type=contract['action_type'], target=contract['target'], parameters=params,
        subject_principal_id='executor', subject_role='executor', issuer_principal_id='trial-verifier',
        issuer_role='verifier', adapter_contract={'name': 'github-git-data', 'version': 'v1', 'idempotency_required': True},
        observation_contract={'name': 'emergence.acceptance', 'version': 'v1', 'minimum_confirmations': 1,
                              'success_predicate_digest': full_digest(contract)},
        nonce=secrets.token_hex(32), expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        private_key=keys['issuer'], key_id='issuer-key', now=datetime.fromtimestamp(now, timezone.utc))
    env = make_envelope('requester', 'executor', 'publish-artifact',
                        {'task': task, 'contract': contract, 'authority': authority}, keys['sender'],
                        now=now, ttl=3600)
    trust = Trust(encode_public(keys['sender'].public_key()), keys['issuer'].public_key(), 'issuer-key',
                  full_digest(authority), authority['issuer'], keys['observer'].public_key(),
                  'observer-key', roots, approval)
    ledger = ExecutionLedger(directory / 'registry.db', keys['consumer'], 'consumer-key')
    claim = ledger.consume(env, contract, trust)
    request = prepare_commit(ledger, claim['execution_id'], env, contract, trust)
    evidence = {'handoff': env, 'contract': contract, 'consumption': claim,
                'public_keys': {name: encode_public(key.public_key()) for name, key in keys.items()},
                'shared_claim_visible': replay_claim_exists(ledger.path, authority['record_hash']),
                'replay_root': replay_registry_root(ledger.path), 'request': request}
    write_json(directory / 'public-evidence.json', evidence)
    write_json(directory / 'request.json', request)
    print(json.dumps({'execution_id': claim['execution_id'], 'shared_claim_visible': evidence['shared_claim_visible']}))


def verify(directory):
    evidence = json.loads((directory / 'public-evidence.json').read_text())
    private = json.loads((directory / 'private.json').read_text())
    keys = {name: Ed25519PrivateKey.from_private_bytes(bytes.fromhex(value)) for name, value in private.items()}
    env, contract = evidence['handoff'], evidence['contract']
    authority = env['payload']['authority']
    trust = Trust(evidence['public_keys']['sender'], keys['issuer'].public_key(), 'issuer-key',
                  full_digest(authority), authority['issuer'], keys['observer'].public_key(),
                  'observer-key', authority['roots'], authority['approval_digest'])
    ledger = ExecutionLedger(directory / 'registry.db', keys['consumer'], 'consumer-key')
    provider = json.loads((directory / 'provider-readback.json').read_text())
    result = verify_commit(ledger, evidence['consumption']['execution_id'], env, contract, trust,
        commit=provider['commit'], file_content=provider['file_content'], repository=provider['repository'],
        path=provider['path'], observed_ref=provider['observed_ref'])
    result['branch_head_matches'] = provider['branch_head'] == provider['commit']['sha']
    if not result['branch_head_matches']:
        raise ValueError('branch_head_changed')
    try:
        prepare_commit(ledger, evidence['consumption']['execution_id'], env, contract, trust)
    except ValueError as exc:
        if str(exc) != 'dispatch_already_started_no_retry':
            raise
        result['repeat_dispatch_rejected'] = True
    else:
        raise AssertionError('Repeated dispatch was allowed')
    write_json(directory / 'result.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'verify'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--repository')
    parser.add_argument('--branch')
    parser.add_argument('--parent-sha')
    parser.add_argument('--base-tree')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.directory, args.repository, args.branch, args.parent_sha, args.base_tree)
    else:
        verify(args.directory)
