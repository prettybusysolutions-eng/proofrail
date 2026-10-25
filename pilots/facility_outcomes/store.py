"""Tenant-scoped business store and append-only, hash-chained audit log (SQLite).

Every read and write takes the caller's tenant. A record belonging to another
tenant is indistinguishable from a missing one (`not_found`), so guessed
identifiers reveal nothing. This store holds business records only; ProofRail's
replay registry is a separate file owned by the gateway.

SQLite is a pilot component (no Docker/PostgreSQL in this environment): it gives
real transactions and unique constraints, not multi-node durability.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from proofrail.crypto import canonical_json
from records import PilotError, require

KINDS = ('problem', 'plan', 'approval', 'revocation', 'authority', 'observation', 'verdict', 'acceptance',
         'invoice', 'settlement', 'learning')
GENESIS = '0' * 64


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        with closing(self._db()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS records (
                    tenant_id TEXT NOT NULL, kind TEXT NOT NULL, record_id TEXT NOT NULL,
                    body TEXT NOT NULL, PRIMARY KEY (tenant_id, kind, record_id));
                CREATE TABLE IF NOT EXISTS work (
                    tenant_id TEXT NOT NULL, problem_id TEXT NOT NULL, state TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, problem_id));
                CREATE TABLE IF NOT EXISTS settlements_authorized (
                    tenant_id TEXT NOT NULL, work_order_id TEXT NOT NULL, settlement_id TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, work_order_id));
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL,
                    event TEXT NOT NULL, subject TEXT NOT NULL, detail TEXT NOT NULL,
                    previous TEXT NOT NULL, hash TEXT NOT NULL UNIQUE);
            ''')

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        return db

    # ------------------------------------------------------------ records
    def put(self, tenant_id: str, kind: str, record_id: str, body: dict, *, replace: bool = False) -> None:
        require(kind in KINDS, 'unknown_kind')
        with closing(self._db()) as db:
            try:
                db.execute(('INSERT OR REPLACE' if replace else 'INSERT') +
                           ' INTO records VALUES (?,?,?,?)', (tenant_id, kind, record_id, json.dumps(body)))
            except sqlite3.IntegrityError:
                raise PilotError('record_exists', f'{kind}:{record_id}') from None

    def get(self, tenant_id: str, kind: str, record_id: str) -> dict:
        with closing(self._db()) as db:
            row = db.execute('SELECT body FROM records WHERE tenant_id=? AND kind=? AND record_id=?',
                             (tenant_id, kind, record_id)).fetchone()
        require(row is not None, 'not_found')   # same answer for absent and other-tenant records
        return json.loads(row[0])

    def all(self, tenant_id: str, kind: str) -> list[dict]:
        with closing(self._db()) as db:
            rows = db.execute('SELECT body FROM records WHERE tenant_id=? AND kind=? ORDER BY rowid',
                              (tenant_id, kind)).fetchall()
        return [json.loads(r[0]) for r in rows]

    # ------------------------------------------------------------ work state
    def state(self, tenant_id: str, problem_id: str) -> str:
        with closing(self._db()) as db:
            row = db.execute('SELECT state FROM work WHERE tenant_id=? AND problem_id=?',
                             (tenant_id, problem_id)).fetchone()
        return row[0] if row else 'NONE'

    def move(self, tenant_id: str, problem_id: str, expected: str, new: str) -> None:
        """Compare-and-set, so two concurrent transitions cannot both succeed."""
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM work WHERE tenant_id=? AND problem_id=?',
                             (tenant_id, problem_id)).fetchone()
            current = row[0] if row else 'NONE'
            if current != expected:
                db.execute('ROLLBACK')
                raise PilotError('state_changed_concurrently', f'{expected} -> {current}')
            db.execute('INSERT OR REPLACE INTO work VALUES (?,?,?)', (tenant_id, problem_id, new))
            db.execute('COMMIT')

    # ------------------------------------------------------------ settlement uniqueness
    def reserve_settlement(self, tenant_id: str, work_order_id: str, settlement_id: str) -> bool:
        with closing(self._db()) as db:
            try:
                db.execute('INSERT INTO settlements_authorized VALUES (?,?,?)',
                           (tenant_id, work_order_id, settlement_id))
                return True
            except sqlite3.IntegrityError:
                return False

    # ------------------------------------------------------------ audit chain
    def audit(self, tenant_id: str, event: str, subject: str, detail: dict) -> str:
        with closing(self._db()) as db:
            db.execute('BEGIN IMMEDIATE')
            # One chain per tenant, so a tenant's audit can be exported and verified on its own.
            row = db.execute('SELECT hash FROM audit WHERE tenant_id=? ORDER BY sequence DESC LIMIT 1',
                             (tenant_id,)).fetchone()
            previous = row[0] if row else GENESIS
            entry = {'tenant_id': tenant_id, 'event': event, 'subject': subject, 'detail': detail,
                     'previous': previous}
            value = hashlib.sha256(canonical_json(entry)).hexdigest()
            db.execute('INSERT INTO audit (tenant_id,event,subject,detail,previous,hash) VALUES (?,?,?,?,?,?)',
                       (tenant_id, event, subject, json.dumps(detail, sort_keys=True), previous, value))
            db.execute('COMMIT')
        return value

    def audit_entries(self, tenant_id: str) -> list[dict]:
        with closing(self._db()) as db:
            rows = db.execute('SELECT tenant_id,event,subject,detail,previous,hash FROM audit WHERE tenant_id=? '
                              'ORDER BY sequence', (tenant_id,)).fetchall()
        return [{'tenant_id': t, 'event': e, 'subject': s, 'detail': json.loads(d), 'previous': p, 'hash': h}
                for t, e, s, d, p, h in rows]


def verify_chain(entries: list[dict]) -> bool:
    """Checks one tenant's full chain from genesis. A truncated tail is not detectable this way."""
    previous = GENESIS
    if len({e['tenant_id'] for e in entries}) > 1:
        return False
    for entry in entries:
        body = {k: entry[k] for k in ('tenant_id', 'event', 'subject', 'detail', 'previous')}
        if entry['previous'] != previous or hashlib.sha256(canonical_json(body)).hexdigest() != entry['hash']:
            return False
        previous = entry['hash']
    return True
