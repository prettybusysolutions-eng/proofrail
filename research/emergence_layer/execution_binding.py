"""Experimental local consumption and destination-provenance integration.

Uses ProofRail signature/authority verification and the existing permit_claims
and permit_events replay tables. Execution records use an additional namespaced
table. No deployed registry is modified by the tests. SQLite provenance is a
trusted fixture; GitHub requests are executed through the authenticated connector.
"""
import copy
import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from proofrail.crypto import canonical_json, sign_record, verify_signature
from acceptance_bridge import BindingError, full_digest, require, verify_handoff


def connect(path):
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    return db


class ExecutionLedger:
    def __init__(self, path, private_key, key_id):
        self.path, self.private_key, self.key_id = Path(path), private_key, key_id
        self.public_key = private_key.public_key()
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS emergence_executions (
                execution_id TEXT PRIMARY KEY, authority_digest TEXT NOT NULL UNIQUE,
                nonce TEXT NOT NULL UNIQUE, body TEXT NOT NULL,
                dispatch_started INTEGER NOT NULL DEFAULT 0)''')
            # Same schema and uniqueness boundary used by ProofRail's existing
            # GitHub and migration consumers. No separate replay namespace.
            db.executescript('''
                CREATE TABLE IF NOT EXISTS permit_claims (
                    permit_hash TEXT PRIMARY KEY, nonce TEXT NOT NULL UNIQUE,
                    executor_id TEXT NOT NULL, executing_at TEXT NOT NULL,
                    consumed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS permit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    permit_hash TEXT NOT NULL, state TEXT NOT NULL,
                    observed_at TEXT NOT NULL, executor_id TEXT NOT NULL);
            ''')

    def _db(self):
        # sqlite connection context managers don't close connections themselves.
        from contextlib import closing
        return closing(connect(self.path))

    def consume(self, handoff, contract, trust, *, clock=time.time):
        # Snapshot caller objects before verification so checked bytes are stored.
        handoff, contract = copy.deepcopy(handoff), copy.deepcopy(contract)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                now = int(clock())
                binding = verify_handoff(handoff, contract, trust, now=now)
                authority = handoff['payload']['authority']
                # Checkpoint-bearing authority needs checkpoint validation and
                # advancement. Reject until that mode is integrated explicitly.
                require('trust' not in authority, 'checkpoint_authority_not_supported')
                timestamp = datetime.fromtimestamp(now, timezone.utc).isoformat().replace('+00:00', 'Z')
                db.execute('INSERT INTO permit_claims VALUES (?,?,?,?,?)',
                           (authority['record_hash'], authority['nonce'], contract['recipient'],
                            timestamp, timestamp))
                db.executemany('INSERT INTO permit_events (permit_hash,state,observed_at,executor_id) '
                               'VALUES (?,?,?,?)', [(authority['record_hash'], state, timestamp,
                               contract['recipient']) for state in ('EXECUTING', 'CONSUMED')])
                record = sign_record({
                    'kind': 'emergence.consumption.v1', 'execution_id': str(uuid.uuid4()),
                    'tenant': contract['tenant'], 'task_id': contract['task_id'],
                    'target': contract['target'], 'executor': contract['recipient'],
                    'handoff_digest': binding['handoff_digest'],
                    'authority_digest': binding['authority_digest'],
                    'contract_digest': binding['contract_digest'], 'consumed_at': now,
                    'permit_hash': authority['record_hash'], 'permit_nonce': authority['nonce'],
                }, self.private_key, key_id=self.key_id)
                db.execute('INSERT INTO emergence_executions VALUES (?,?,?,?,0)',
                           (record['execution_id'], record['authority_digest'],
                            handoff['payload']['authority']['nonce'],
                            canonical_json(record).decode()))
                db.execute('COMMIT')
                return record
            except sqlite3.IntegrityError as exc:
                db.execute('ROLLBACK')
                raise BindingError('authority_already_consumed') from exc
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def get(self, execution_id):
        with self._db() as db:
            row = db.execute('SELECT body,dispatch_started FROM emergence_executions WHERE execution_id=?',
                             (execution_id,)).fetchone()
        require(row is not None, 'execution_not_found')
        record = json.loads(row['body'])
        require(record.get('kind') == 'emergence.consumption.v1', 'consumption_kind')
        require(record.get('execution_id') == execution_id, 'consumption_execution_changed')
        require(record['signature']['key_id'] == self.key_id, 'consumption_key_changed')
        verify_signature(record, self.public_key)
        with self._db() as db:
            claim = db.execute('SELECT * FROM permit_claims WHERE permit_hash=?',
                               (record['permit_hash'],)).fetchone()
        require(claim is not None and claim['nonce'] == record['permit_nonce'] and
                claim['executor_id'] == record['executor'], 'shared_claim_missing_or_changed')
        return record, bool(row['dispatch_started'])

    def begin_dispatch(self, execution_id, handoff, contract, trust, *, clock=time.time):
        """One durable admission; caller must execute only the bound operation."""
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                consumption, _ = self.get(execution_id)
                binding = verify_handoff(handoff, contract, trust, now=int(clock()))
                for field in ('handoff_digest', 'authority_digest', 'contract_digest'):
                    require(consumption[field] == binding[field], 'dispatch_' + field + '_changed')
                cursor = db.execute('UPDATE emergence_executions SET dispatch_started=1 '
                                    'WHERE execution_id=? AND dispatch_started=0', (execution_id,))
                require(cursor.rowcount == 1, 'dispatch_already_started_no_retry')
                db.execute('COMMIT')
                return consumption
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def dispatch_local(self, execution_id, handoff, contract, trust, destination, *,
                       clock=time.time, fault=None):
        require(fault in (None, 'after_mark', 'after_effect'), 'invalid_fault')
        handoff, contract = copy.deepcopy(handoff), copy.deepcopy(contract)
        require(contract['action_type'] == 'artifact_write' and
                contract['capability'] == 'publish-artifact' and
                contract['target'].startswith('fixture:') and
                contract['parameters'] == {'version': 1}, 'unsupported_local_effect')
        require(set(handoff['payload']['task']) == {'artifact'}, 'unsupported_local_task')
        consumption = self.begin_dispatch(execution_id, handoff, contract, trust, clock=clock)
        if fault == 'after_mark':
            os._exit(73)
        destination.apply(consumption, handoff['payload']['task']['artifact'])
        if fault == 'after_effect':
            os._exit(73)


class LocalArtifactDestination:
    """Destination-owned transaction binds current bytes to the creating run.

    A trusted fixture, not an external-provider adapter or malicious-DB defense.
    """
    def __init__(self, path):
        self.path = Path(path)
        db = connect(self.path)
        try:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS operations (
                    execution_id TEXT PRIMARY KEY, consumption_digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (
                    tenant TEXT NOT NULL, target TEXT NOT NULL, execution_id TEXT NOT NULL,
                    consumption_digest TEXT NOT NULL, content TEXT NOT NULL,
                    PRIMARY KEY (tenant,target));
            ''')
        finally:
            db.close()

    def apply(self, consumption, content):
        require(isinstance(content, str), 'artifact_must_be_text')
        db = connect(self.path)
        try:
            db.execute('BEGIN IMMEDIATE')
            digest = full_digest(consumption)
            db.execute('INSERT INTO operations VALUES (?,?)', (consumption['execution_id'], digest))
            db.execute('INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?)',
                       (consumption['tenant'], consumption['target'], consumption['execution_id'], digest, content))
            db.execute('COMMIT')
        except BaseException:
            db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def observe(self, target, *, tenant, observer, key_id, private_key, now):
        db = connect(self.path)
        try:
            row = db.execute('SELECT * FROM artifacts WHERE tenant=? AND target=?', (tenant, target)).fetchone()
        finally:
            db.close()
        # Run identity comes from the destination record, not from the requested
        # execution ID or executor's self-reported success.
        return sign_record({
            'kind': 'emergence.execution-observation.v1', 'observer': observer,
            'tenant': tenant, 'target': target, 'observed_at': now,
            'status': 'present' if row else 'absent',
            'execution_id': row['execution_id'] if row else None,
            'consumption_digest': row['consumption_digest'] if row else None,
            'content_sha256': hashlib.sha256(row['content'].encode()).hexdigest() if row else None,
        }, private_key, key_id=key_id)


def verify_execution(ledger, execution_id, handoff, contract, trust, observation, *, now):
    require(type(now) is int, 'integer_clock_required')
    consumption, started = ledger.get(execution_id)
    consumed_at = consumption['consumed_at']
    require(type(consumed_at) is int and consumed_at <= now, 'consumption_time_invalid')
    # Audit checks authority validity at consumption, not at a later readback.
    binding = verify_handoff(handoff, contract, trust, now=consumed_at)
    for field in ('handoff_digest', 'authority_digest', 'contract_digest'):
        require(consumption[field] == binding[field], 'consumption_' + field + '_changed')
    for field in ('tenant', 'task_id', 'target'):
        require(consumption[field] == contract[field], 'consumption_' + field + '_changed')
    require(consumption['executor'] == contract['recipient'], 'consumption_executor_changed')
    base = {**binding, 'execution_id': execution_id, 'consumption_digest': full_digest(consumption)}
    if not started or observation is None:
        return {**base, 'outcome': 'UNCONFIRMED', 'reason': 'no_dispatch_or_observation'}
    fields = {'kind', 'observer', 'tenant', 'target', 'observed_at', 'status', 'execution_id',
              'consumption_digest', 'content_sha256', 'signature', 'record_hash'}
    require(isinstance(observation, dict) and set(observation) == fields, 'invalid_execution_observation')
    require(observation['kind'] == 'emergence.execution-observation.v1', 'execution_observation_kind')
    require(observation['signature']['key_id'] == trust.observer_key_id, 'observer_key_changed')
    verify_signature(observation, trust.observer_public)
    require(observation['observer'] == contract['observer'], 'observer_changed')
    require(observation['target'] == contract['target'], 'observation_target_changed')
    require(observation['tenant'] == contract['tenant'], 'observation_tenant_changed')
    when = observation['observed_at']
    require(type(when) is int and consumed_at <= when <= now, 'observation_time_invalid')
    require(now - when <= contract['max_observation_age_seconds'], 'observation_stale')
    require(observation['status'] in ('present', 'absent', 'unknown'), 'observation_status')
    if observation['status'] != 'present':
        require(all(observation[f] is None for f in
                    ('execution_id', 'consumption_digest', 'content_sha256')), 'inconsistent_absence')
        return {**base, 'outcome': 'UNCONFIRMED', 'reason': observation['status']}
    require(observation['execution_id'] == execution_id, 'observation_execution_changed')
    require(observation['consumption_digest'] == full_digest(consumption), 'observation_consumption_changed')
    actual = observation['content_sha256']
    import re
    require(isinstance(actual, str) and re.fullmatch('[0-9a-f]{64}', actual), 'invalid_content_digest')
    return {**base, 'outcome': 'MATCH' if actual == contract['expected_sha256'] else 'DIVERGED',
            'observation_digest': full_digest(observation)}
