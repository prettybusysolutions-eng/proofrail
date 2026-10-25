"""Read replay-registry consumption committed by ProofRail's local pilot gateway.

This is local operational state, not proof of independently retained history.
A separately signed gateway receipt can authenticate its attestation about
these rows; it cannot prove external checkpoint publication or rollback safety.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from records import require


def read_registry_claim(registry_path: Path, permit_hash: str) -> dict:
    with closing(sqlite3.connect(f'file:{registry_path}?mode=ro', uri=True)) as db:
        claim = db.execute(
            'SELECT permit_hash, nonce, executor_id, executing_at, consumed_at '
            'FROM permit_claims WHERE permit_hash=?', (permit_hash,)
        ).fetchone()
        events = db.execute(
            'SELECT state, observed_at, executor_id FROM permit_events '
            'WHERE permit_hash=? ORDER BY sequence', (permit_hash,)
        ).fetchall()
    require(claim is not None, 'consumption_record_missing')
    keys = ('permit_hash', 'nonce', 'executor_id', 'executing_at', 'consumed_at')
    return {
        'registry_format': 'proofrail.permit_claims (as consume_permit)',
        'claim': dict(zip(keys, claim)),
        'events': [dict(zip(('state', 'observed_at', 'executor_id'), e)) for e in events],
    }
