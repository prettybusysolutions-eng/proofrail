"""Local HTTP integration comparison, NOT an independent review or GitHub benchmark.

Both paths use the same provider adapter. The conventional signed-grant gate
does not import ProofRail's signature/permit/claim implementation. Checkpoint
hardening, key custody, real GitHub semantics, and distributed revocation are
outside this comparison. Raw samples and provider-observed effects are retained.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import socket
import sqlite3
import statistics
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from integrations.openclaw.github_adapter import GitHubMergeAdapter, GitHubTransport
from proofrail.permit import execute_github_merge, mint_permit


HEAD = 'a' * 40
ROOTS = {name: str(i) * 64 for i, name in enumerate(
    ('identity', 'evidence', 'policy', 'state'), 1)}
APPROVAL = '5' * 64


class Provider:
    """Only the fixture implements provider writes; gates cannot set outcomes."""
    def __init__(self, root):
        self.path = root / 'provider.sqlite'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE pulls (id INTEGER PRIMARY KEY, head TEXT, merged INTEGER, effects INTEGER, mode TEXT)')
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, payload):
                data = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                number = int(self.path.split('/')[5])
                head, merged, effects, mode = provider.observe(number)
                self.reply(200, {'head': {'sha': head}, 'merged': bool(merged),
                                'mergeable': True, 'merge_commit_sha': 'c' * 40 if merged else None})

            def do_PUT(self):
                number = int(self.path.split('/')[5])
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with sqlite3.connect(provider.path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    head, merged, effects, mode = db.execute(
                        'SELECT head, merged, effects, mode FROM pulls WHERE id=?', (number,)).fetchone()
                    if mode == 'competing_head':
                        db.execute('UPDATE pulls SET head=?, merged=1, effects=effects+1 WHERE id=?', ('b' * 40, number))
                        code, result = 409, {'message': 'another actor merged changed head'}
                    elif body.get('sha') != head:
                        code, result = 409, {'message': 'head mismatch'}
                    else:
                        db.execute('UPDATE pulls SET merged=1, effects=effects+? WHERE id=?', (0 if merged else 1, number))
                        code, result = 200, {'merged': True, 'sha': 'c' * 40}
                if mode == 'lost_response':
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                self.reply(code, result)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.counter = 0

    def new(self, mode='normal', head=HEAD):
        self.counter += 1
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO pulls VALUES (?, ?, 0, 0, ?)', (self.counter, head, mode))
        return self.counter

    def observe(self, number):
        with sqlite3.connect(self.path) as db:
            return db.execute('SELECT head, merged, effects, mode FROM pulls WHERE id=?', (number,)).fetchone()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ConventionalGate:
    """Signature + current-context comparison + atomic unique claim + provider check.

    This is a transparent reference composition, not a commercial policy engine.
    It is not equivalent to ProofRail's checkpoint/portable-proof subsystem.
    """
    def __init__(self, root, key, adapter):
        self.path, self.key, self.adapter = root / 'conventional.sqlite', key, adapter
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE claims (nonce TEXT PRIMARY KEY, hash TEXT UNIQUE)')

    def mint(self, number, nonce):
        body = {'nonce': nonce, 'roots': ROOTS.copy(), 'approval': APPROVAL,
                'expires': time.time() + 3600,
                'effect': {'owner': 'fixture', 'repo': 'fixture', 'pull_number': number,
                           'expected_head_sha': HEAD, 'merge_method': 'squash'}}
        return {'body': body, 'signature': self.key.sign(rfc8785.dumps(body)).hex()}

    def run(self, permit, context, now, adapter=None):
        body = permit['body']
        data = rfc8785.dumps(body)
        self.key.public_key().verify(bytes.fromhex(permit['signature']), data)
        if now.timestamp() >= body['expires']:
            raise ValueError('expired')
        if body['roots'] != context or body['approval'] != APPROVAL:
            raise ValueError('context_changed')
        digest = hashlib.sha256(data).hexdigest()
        with sqlite3.connect(self.path, timeout=30) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO claims VALUES (?, ?)', (body['nonce'], digest))
        receipt = (adapter or self.adapter).execute({'execution': body['effect']}, idempotency_key=digest)
        return 'success' if receipt['status'] == 'success' and receipt['side_effect_confirmed'] else receipt['status']


class ProofRailGate:
    def __init__(self, root, key, adapter):
        self.path, self.key, self.adapter = root / 'proofrail.sqlite', key, adapter

    def mint(self, number, nonce):
        return mint_permit(**{f'{k}_root': v for k, v in ROOTS.items()},
            approval_digest=APPROVAL, repository='fixture/fixture', pull_number=number,
            expected_head_sha=HEAD, merge_method='squash', nonce=nonce,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            issuer_principal_id='fixture-verifier', issuer_role='verifier',
            private_key=self.key, key_id='fixture-key')

    def run(self, permit, context, now, adapter=None):
        result = execute_github_merge(permit, adapter=adapter or self.adapter,
            registry_path=self.path, public_key=self.key.public_key(),
            **{f'expected_{k}_root': v for k, v in context.items()},
            expected_approval_digest=APPROVAL, executor_id='fixture-executor', now=now)
        return {'RECONCILED': 'success', 'EXECUTION_FAILED': 'failed',
                'RECONCILIATION_FAILED': 'unknown'}[result['authority_state']]


def attempt(gate, permit, context=None, now=None, adapter=None):
    try:
        return {'status': gate.run(permit, context or ROOTS, now or datetime.now(timezone.utc), adapter)}
    except Exception as exc:
        return {'status': 'error', 'type': type(exc).__name__, 'reason': str(exc)}


def checks(root, provider, name, cls, key, adapter):
    folder = root / name
    folder.mkdir()
    gate = cls(folder, key, adapter)
    results = []

    def case(label, mode='normal', head=HEAD, mutate=None, context=None, now=None, repeat=False, hook=None):
        number = provider.new(mode, head)
        permit = gate.mint(number, f'{name}-{label}-nonce-00000001')
        if mutate:
            mutate(permit)
        first = attempt(gate, permit, context, now, hook)
        retries = [attempt(gate, permit, context, now)] if repeat else []
        result = {'case': label, 'first': first, 'retries': retries,
                  'provider': list(provider.observe(number))}
        results.append(result)
        return result

    case('normal')
    case('expired', now=datetime.now(timezone.utc) + timedelta(hours=2))
    case('policy_changed', context={**ROOTS, 'policy': '9' * 64})
    case('identity_changed', context={**ROOTS, 'identity': '9' * 64})
    case('tampered_signature', mutate=lambda p: p.update(signature='00' * 64))
    case('replay', repeat=True)
    case('provider_head_changed', head='b' * 40)
    case('lost_response', mode='lost_response')
    case('competing_head', mode='competing_head')

    class Crash:
        def execute(self, *args, **kwargs):
            raise RuntimeError('injected interruption after durable claim, before provider')
    case('interrupted_after_claim', repeat=True, hook=Crash())

    number = provider.new()
    permit = gate.mint(number, f'{name}-concurrency-nonce-00000001')
    barrier = threading.Barrier(4)
    def call(_):
        barrier.wait(timeout=10)
        return attempt(gate, permit)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        concurrent_results = list(pool.map(call, range(4)))
    results.append({'case': 'concurrent_replay', 'attempts': concurrent_results,
                    'provider': list(provider.observe(number))})

    # Explicit counterexample: an authoritative context change after gate
    # admission is not propagated into either already-dispatched adapter.
    number = provider.new()
    permit = gate.mint(number, f'{name}-late-revocation-nonce-00000001')
    live_context = ROOTS.copy()
    class LateRevocation:
        def execute(self, action, *, idempotency_key):
            live_context['identity'] = '9' * 64
            return adapter.execute(action, idempotency_key=idempotency_key)
    results.append({'case': 'late_revocation_boundary',
                    'first': attempt(gate, permit, live_context, adapter=LateRevocation()),
                    'provider': list(provider.observe(number)),
                    'revocation_occurred_before_http_write': live_context != ROOTS})

    for r in results:
        label, effects = r['case'], r['provider'][2]
        if label in {'normal', 'lost_response', 'replay'}:
            passed = r['first']['status'] == 'success' and effects == 1
            if label == 'replay':
                passed = passed and r['retries'][0]['status'] == 'error'
        elif label == 'competing_head':
            passed = r['first']['status'] != 'success' and effects == 1 and r['provider'][0] != HEAD
        elif label == 'concurrent_replay':
            passed = sum(x['status'] == 'success' for x in r['attempts']) == 1 and effects == 1
        elif label == 'late_revocation_boundary':
            passed = r['first']['status'] == 'success' and effects == 1 and r['revocation_occurred_before_http_write']
        else:
            passed = r['first']['status'] != 'success' and effects == 0
            if label == 'interrupted_after_claim':
                passed = passed and r['retries'][0]['status'] == 'error'
        r['expected_behavior_observed'] = passed
        r['classification'] = 'known_limit_reproduced' if label == 'late_revocation_boundary' else 'safety_or_functionality_check'
    return gate, results


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, int(len(values) * p + .999999) - 1))]


def run(samples, seed):
    key = Ed25519PrivateKey.generate()
    with tempfile.TemporaryDirectory(prefix='proofrail-comparison-') as directory:
        root = Path(directory)
        provider = Provider(root)
        try:
            adapter = GitHubMergeAdapter(GitHubTransport(token='synthetic-no-credential', api_base=provider.url))
            gates, cases = {}, {}
            for name, cls in [('conventional', ConventionalGate), ('proofrail', ProofRailGate)]:
                gates[name], cases[name] = checks(root, provider, name, cls, key, adapter)
            rng = random.Random(seed)
            timings = {name: [] for name in gates}
            errors = []
            for index in range(samples + 5):
                order = list(gates)
                rng.shuffle(order)
                for name in order:
                    number = provider.new()
                    permit = gates[name].mint(number, f'{name}-benchmark-{index:08d}')
                    started = time.perf_counter_ns()
                    result = attempt(gates[name], permit)
                    elapsed = (time.perf_counter_ns() - started) / 1e6
                    observed = provider.observe(number)
                    if result['status'] != 'success' or observed[2] != 1:
                        errors.append({'name': name, 'sample': index, 'result': result, 'provider': observed})
                    if index >= 5:
                        timings[name].append(elapsed)
            summary = {name: {'samples': len(v), 'p50_ms': statistics.median(v),
                             'p95_ms': percentile(v, .95), 'p99_ms': percentile(v, .99),
                             'mean_ms': statistics.mean(v)} for name, v in timings.items()}
            return {'schema': 1, 'scope': 'local HTTP fixture; shared GitHub adapter; base permits without trust checkpoints',
                    'independent_review': False,
                    'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                                    'sqlite': sqlite3.sqlite_version, 'cpu_count': os.cpu_count()},
                    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    'source_tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
                    'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'seed': seed, 'warmup_per_path': 5, 'cases': cases,
                    'summary': summary, 'raw_ms': timings, 'benchmark_errors': errors,
                    'valid': not errors and all(r['expected_behavior_observed'] for rows in cases.values() for r in rows),
                    'limits': ['not a live GitHub test', 'not a commercial policy-engine benchmark',
                               'shared adapter creates correlated failure risk', 'no checkpoint-mode comparison',
                               'no throughput/load test', 'permit minting excluded from timing',
                               'interruption is an exception injection, not process/power loss',
                               'late revocation is a reproduced limitation, not protection']}
        finally:
            provider.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20261012)
    args = parser.parse_args()
    if args.samples < 20:
        parser.error('at least 20 samples required')
    result = run(args.samples, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'valid': result['valid'], 'summary': result['summary'],
                      'failed_cases': [(name, r['case']) for name, rows in result['cases'].items()
                                       for r in rows if not r['expected_behavior_observed']]}))
    raise SystemExit(0 if result['valid'] else 1)
