"""Controlled local recovery experiments; not a production execution service.

The sink is a separate SQLite database. Worker crashes use os._exit, so no
cleanup/exception handler can quietly finish the task. No model or API is mocked
as real: this lab deliberately uses deterministic, local effect fixtures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from smatp import Store, make_envelope, make_receipt, new_identity

MODES = ('retry_only', 'durable', 'idempotent', 'verified')
FAULTS = ('none', 'before_effect', 'after_effect', 'after_checkpoint', 'false_ack', 'wrong_effect')
VALUE = 'artifact:approved-specification-v1'
EXPECTED = hashlib.sha256(VALUE.encode()).hexdigest()


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    return db


def worker(root, mode, fault):
    root = Path(root)
    ledger = connect(root / 'execution.db')
    sink = connect(root / 'sink.db')
    status = ledger.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0]
    if mode != 'retry_only' and status == 'COMPLETED':
        return
    if fault == 'before_effect':
        os._exit(73)
    if fault != 'false_ack':
        # Atomic uniqueness is enforced by the destination, not the caller.
        key = 'task-1' if mode in ('idempotent', 'verified') else os.urandom(16).hex()
        value = 'artifact:wrong-specification' if fault == 'wrong_effect' else VALUE
        sink.execute('INSERT OR IGNORE INTO effects VALUES (?, ?)', (key, value))
        sink.commit()
    if fault == 'after_effect':
        os._exit(73)
    if mode == 'verified':
        rows = sink.execute('SELECT value FROM effects WHERE effect_key=?', ('task-1',)).fetchall()
        observed = hashlib.sha256(rows[0][0].encode()).hexdigest() if len(rows) == 1 else None
        status = 'COMPLETED' if observed == EXPECTED else 'UNCONFIRMED'
    else:
        # The non-verifying variants trust the sink's successful response.
        observed, status = None, 'COMPLETED'
    ledger.execute('UPDATE jobs SET status=?, observed=? WHERE id=1', (status, observed))
    ledger.commit()
    if fault == 'after_checkpoint':
        os._exit(73)
    sink.close()
    ledger.close()


def experiment(mode, fault):
    if mode not in MODES or fault not in FAULTS:
        raise ValueError('Unknown experiment')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db = connect(root / 'execution.db')
        db.execute('CREATE TABLE jobs (id INTEGER PRIMARY KEY, status TEXT, observed TEXT)')
        db.execute("INSERT INTO jobs VALUES (1, 'PENDING', NULL)")
        db.commit()
        db.close()
        sink = connect(root / 'sink.db')
        sink.execute('CREATE TABLE effects (effect_key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        sink.commit()
        sink.close()

        # Retain the existing protocol and bind experiment observations to receipts.
        sender, sender_pub = new_identity()
        recipient, recipient_pub = new_identity()
        store = Store(root / 'handoff.db')
        store.register_agent('requester', sender_pub)
        store.register_agent('executor', recipient_pub)
        env = make_envelope('requester', 'executor', 'local-fixture',
                            {'expected_sha256': EXPECTED}, sender)
        mid = store.submit(env)['message_id']
        store.append_receipt(make_receipt(mid, 'executor', 'ACCEPTED', None, recipient))
        codes = []
        # Same two deliveries in every arm. Persistent false acknowledgment stays
        # false on both attempts; crash faults occur only on the first attempt.
        for injected in (fault, fault if fault in ('false_ack', 'wrong_effect') else 'none'):
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                   '--worker', directory, mode, injected],
                                  capture_output=True, text=True, timeout=15)
            if proc.returncode not in (0, 73):
                raise RuntimeError(proc.stderr or f'Unexpected exit {proc.returncode}')
            codes.append(proc.returncode)
        db = connect(root / 'execution.db')
        status, observed = db.execute('SELECT status, observed FROM jobs WHERE id=1').fetchone()
        db.close()
        sink = connect(root / 'sink.db')
        values = [row[0] for row in sink.execute('SELECT value FROM effects')]
        sink.close()
        # This read is the lab oracle, separate from the worker's reported status.
        actual = len(values)
        correct = actual == 1 and values[0] == VALUE
        if status == 'COMPLETED':
            store.append_receipt(make_receipt(mid, 'executor', 'COMPLETED',
                store.last_receipt_hash(mid), recipient,
                result={'observed_sha256': observed, 'worker_claim': status}))
        chain_valid = store.verify_record(mid)
        record = store.get_record(mid)
        store.close()
        return {'mode': mode, 'fault': fault, 'worker_exit_codes': codes,
                'effect_count': actual, 'status': status,
                'duplicate_effects': max(0, actual - 1),
                'false_completion': status == 'COMPLETED' and not correct,
                'correct_effect': correct, 'receipt_chain_valid': chain_valid,
                'protocol_status': record['status']}


def run_matrix():
    rows = [experiment(mode, fault) for fault in FAULTS for mode in MODES]
    return {'scope': 'Local SQLite fixtures; two deliveries per cell; no remote services',
            'rows': rows,
            'summary': {mode: {
                'duplicate_effects': sum(r['duplicate_effects'] for r in rows if r['mode'] == mode),
                'false_completions': sum(r['false_completion'] for r in rows if r['mode'] == mode),
                'correct_effect_cases': sum(r['correct_effect'] for r in rows if r['mode'] == mode),
            } for mode in MODES}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', nargs=3, metavar=('ROOT', 'MODE', 'FAULT'))
    parser.add_argument('--output', default='counterfactual_results.json')
    args = parser.parse_args()
    if args.worker:
        worker(*args.worker)
    else:
        results = run_matrix()
        Path(args.output).write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results['summary'], indent=2))
