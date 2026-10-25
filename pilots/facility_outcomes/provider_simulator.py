"""Work-order provider simulator: a real HTTP server with its own persistent store.

    python provider_simulator.py --db /tmp/provider.db --port-file /tmp/port
        --trusted-gateways /path/to/provider-owned-keys.json [--port 0]
    # Explicit insecure testing ONLY: --insecure-fault-mode

Endpoints (JSON):
  POST /v1/tenants/{tenant}/work-orders               create (Idempotency-Key required)
  GET  /v1/tenants/{tenant}/work-orders?client_reference=R
  GET  /v1/tenants/{tenant}/work-orders/{id}
  POST /admin/fault        {"mode": ..., "seconds": ...}   arm a fault (test control)
  POST /admin/status       {"tenant_id","work_order_id","status"}  provider-side progress
  GET  /admin/count        ground-truth number of work orders ever created

Fault modes (one-shot unless noted):
  timeout_after_accept     store the order, then stall past the client timeout
  wrong_operation_success  create nothing; answer 201 naming another existing order
  malformed                store the order, answer with an unparseable body
  other_tenant_response    store the order, answer with another tenant's id in the body
  drop_without_effect      close the connection without storing anything
  no_idempotency           (persistent) ignore Idempotency-Key, so repeats duplicate
  status_flap              (persistent) GET alternates the reported status

This is a test provider. It is not a model of any specific vendor's API.
"""
from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from proofrail.crypto import hash_record, verify_signature
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FIELDS = ('facility_id', 'area_id', 'provider_id', 'problem_id', 'plan_id', 'plan_digest', 'scope_revision',
          'max_cost', 'currency', 'client_reference')


class ProviderState:
    def __init__(self, db_path: Path, trusted_gateways: dict | None = None):
        self.db_path = Path(db_path)
        # None intentionally preserves insecure fault-simulation mode. A map,
        # including an empty map, enables fail-closed provider authorization.
        self.trusted_gateways = trusted_gateways
        self.lock = threading.Lock()
        self.fault = {'mode': None, 'seconds': 0}
        self.persistent = set()
        self.flap = 0
        with closing(self.db()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS orders (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_order_id TEXT UNIQUE NOT NULL, tenant_id TEXT NOT NULL, idempotency_key TEXT,
                    body TEXT NOT NULL, status TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS idem ON orders (tenant_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL;''')

    def db(self):
        return sqlite3.connect(self.db_path, timeout=10, isolation_level=None)

    def take_fault(self):
        with self.lock:
            mode, seconds = self.fault['mode'], self.fault['seconds']
            self.fault = {'mode': None, 'seconds': 0}
            return mode, seconds

    def authorize_create(self, tenant: str, key: str, client_id: str, body: dict, token: str | None):
        """Verify a signed, scoped gateway capability using provider-owned trust pins.

        Authorization is checked at the provider, before the fault injection
        path or any SQLite write. Gateway headers alone confer no authority.
        """
        if self.trusted_gateways is None:
            return True, None  # insecure simulator mode, explicitly opt-in at deployment
        pin = self.trusted_gateways.get(tenant)
        if not isinstance(pin, dict) or not token or len(token) > 12000:
            return False, 'capability_required'
        try:
            raw = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))
            if len(raw) > 9000:
                return False, 'capability_oversized'
            cap = json.loads(raw)
            if not isinstance(cap, dict):
                return False, 'invalid_capability'
            expected_fields = {
                'kind': 'wrn.provider-create-capability.v1',
                'tenant_id': tenant,
                'method': 'POST',
                'path': f'/v1/tenants/{tenant}/work-orders',
                'client_id': client_id,
                'idempotency_key': key,
                'request_digest': hash_record(body),
                'principal_id': pin['principal_id'],
            }
            if any(cap.get(k) != v for k, v in expected_fields.items()):
                return False, 'capability_scope_mismatch'
            if cap.get('signature', {}).get('key_id') != pin['key_id']:
                return False, 'capability_key_mismatch'
            stamp = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))
            issued, expiry = stamp(cap['issued_at']), stamp(cap['expires_at'])
            now = datetime.now(timezone.utc)
            if issued.tzinfo is None or expiry.tzinfo is None:
                return False, 'invalid_capability_time'
            if issued > now + timedelta(seconds=30) or expiry <= now or expiry <= issued:
                return False, 'capability_expired_or_future'
            if expiry - issued > timedelta(minutes=2):
                return False, 'capability_too_long'
            raw_key = base64.b64decode(pin['public_key'], validate=True)
            verify_signature(cap, Ed25519PublicKey.from_public_bytes(raw_key))
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, Exception):
            # Do not disclose signature/parser internals or attempt fallback authorization.
            return False, 'invalid_capability'
        return True, None

    def create(self, tenant, key, body, *, honour_idempotency=True):
        with self.lock, closing(self.db()) as db:
            if honour_idempotency:
                row = db.execute('SELECT body, status FROM orders WHERE tenant_id=? AND idempotency_key=?',
                                 (tenant, key)).fetchone()
                if row:
                    return 200, {**json.loads(row[0]), 'status': row[1]}
            seq = (db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM orders').fetchone()[0])
            order = {'work_order_id': 'WO-%05d' % seq, 'tenant_id': tenant, **{k: body[k] for k in FIELDS}}
            db.execute('INSERT INTO orders (work_order_id,tenant_id,idempotency_key,body,status) VALUES (?,?,?,?,?)',
                       (order['work_order_id'], tenant, key if honour_idempotency else None,
                        json.dumps(order), 'open'))
            return 201, {**order, 'status': 'open'}

    def find(self, tenant, *, client_reference=None, work_order_id=None):
        with closing(self.db()) as db:
            rows = db.execute('SELECT body, status FROM orders WHERE tenant_id=? ORDER BY seq', (tenant,)).fetchall()
        out = []
        for body, status in rows:
            order = json.loads(body)
            if client_reference is not None and order['client_reference'] != client_reference:
                continue
            if work_order_id is not None and order['work_order_id'] != work_order_id:
                continue
            if 'status_flap' in self.persistent:
                self.flap += 1
                status = ('open', 'in_progress')[self.flap % 2]
            out.append({**order, 'status': status})
        return out

    def count(self):
        with closing(self.db()) as db:
            return db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]


def make_handler(state: ProviderState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet; the audit lives in the stores
            pass

        def reply(self, code, body):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            length = int(self.headers.get('Content-Length') or 0)
            return json.loads(self.rfile.read(length) or b'{}')

        def do_GET(self):
            parts = urlsplit(self.path)
            segs = parts.path.strip('/').split('/')
            if parts.path == '/admin/count':
                return self.reply(200, {'count': state.count()})
            if len(segs) >= 4 and segs[:2] == ['v1', 'tenants'] and segs[3] == 'work-orders':
                tenant = segs[2]
                if len(segs) == 5:
                    found = state.find(tenant, work_order_id=segs[4])
                    return self.reply(200, found[0]) if found else self.reply(404, {'error': 'not_found'})
                ref = parse_qs(parts.query).get('client_reference', [None])[0]
                return self.reply(200, {'work_orders': state.find(tenant, client_reference=ref)})
            return self.reply(404, {'error': 'not_found'})

        def do_POST(self):
            parts = urlsplit(self.path)
            segs = parts.path.strip('/').split('/')
            if parts.path == '/admin/fault':
                if state.trusted_gateways is not None:
                    return self.reply(403, {'error': 'admin_fault_disabled_in_enforced_mode'})
                b = self.body()
                if b['mode'] in ('no_idempotency', 'status_flap'):
                    state.persistent.add(b['mode'])
                else:
                    state.fault = {'mode': b['mode'], 'seconds': b.get('seconds', 0)}
                return self.reply(200, {'armed': b['mode']})
            if parts.path == '/admin/status':
                if state.trusted_gateways is not None:
                    return self.reply(403, {'error': 'admin_status_disabled_in_enforced_mode'})
                b = self.body()
                with closing(state.db()) as db:
                    db.execute('UPDATE orders SET status=? WHERE tenant_id=? AND work_order_id=?',
                               (b['status'], b['tenant_id'], b['work_order_id']))
                return self.reply(200, {'ok': True})
            if len(segs) == 4 and segs[:2] == ['v1', 'tenants'] and segs[3] == 'work-orders':
                tenant, key = segs[2], self.headers.get('Idempotency-Key')
                if not key or not self.headers.get('X-Client-Id'):
                    return self.reply(400, {'error': 'idempotency_key_and_client_required'})
                try:
                    body = self.body()
                except (ValueError, TypeError):
                    return self.reply(400, {'error': 'invalid_body'})
                if not isinstance(body, dict) or any(k not in body for k in FIELDS):
                    return self.reply(400, {'error': 'missing_fields'})
                authorized, reason = state.authorize_create(
                    tenant, key, self.headers.get('X-Client-Id'), body,
                    self.headers.get('X-ProofRail-Capability'))
                if not authorized:
                    return self.reply(403, {'error': reason})
                mode, seconds = state.take_fault()
                if mode == 'drop_without_effect':
                    self.close_connection = True
                    self.connection.shutdown(2)
                    return None
                if mode == 'wrong_operation_success':
                    others = state.find(tenant)
                    fake = others[0] if others else {'work_order_id': 'WO-99999', 'tenant_id': tenant,
                                                     **{k: body[k] for k in FIELDS}, 'status': 'open'}
                    return self.reply(201, fake)
                code, order = state.create(tenant, key, body,
                                           honour_idempotency=(state.trusted_gateways is not None or
                                                                'no_idempotency' not in state.persistent))
                if mode == 'timeout_after_accept':
                    time.sleep(seconds)
                if mode == 'malformed':
                    return self.reply(201, b'{"work_order_id": "WO-')
                if mode == 'other_tenant_response':
                    return self.reply(201, {**order, 'tenant_id': 'tenant-other'})
                return self.reply(code, order)
            return self.reply(404, {'error': 'not_found'})
    return Handler


def serve(db_path: Path, port: int = 0, *, trusted_gateways: dict | None = None,
          insecure_fault_mode: bool = False):
    if insecure_fault_mode == (trusted_gateways is not None):
        raise ValueError('choose exactly one provider mode: trusted gateways or explicit insecure fault tests')
    state = ProviderState(db_path, trusted_gateways=trusted_gateways)
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(state))
    server.daemon_threads = True
    return server, state


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--port-file', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--trusted-gateways', type=Path,
                       help='JSON tenant-to-externally-pinned gateway identity map; enables enforced mode')
    modes.add_argument('--insecure-fault-mode', action='store_true',
                       help='explicitly disable provider auth for local failure-injection tests only')
    args = parser.parse_args()
    trusted = json.loads(args.trusted_gateways.read_text()) if args.trusted_gateways else None
    server, _ = serve(args.db, args.port, trusted_gateways=trusted,
                      insecure_fault_mode=args.insecure_fault_mode)
    args.port_file.write_text(str(server.server_address[1]))
    server.serve_forever()


if __name__ == '__main__':
    main()
