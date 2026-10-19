"""Pilot dispatcher. Journal and credentials are trusted service-owned resources.

A separately retained journal prevents replay after execution-DB rollback. It is
not a remote monotonic anchor: rolling back BOTH stores is outside this guarantee.
Recovery is read-only, including after ambiguous provider failures.
"""
import base64
import copy
import json
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from acceptance_bridge import require, verify_handoff, full_digest
from github_artifact import prepare_commit, verify_commit
from proofrail.trust import replay_registry_root


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('provider_redirect_rejected')


class GitHubAPI:
    """Fixed-origin transport; token comes from a service-owned secret file.

    No retries on writes. No request bodies, credentials, or response bodies in
    exceptions. App installation token scope must be configured independently.
    """
    def __init__(self, token_file):
        path = Path(token_file)
        require(path.is_file() and not path.is_symlink(), 'credential_file_required')
        require(path.stat().st_mode & 0o077 == 0, 'credential_permissions')
        self._token = path.read_text().strip()
        require(bool(self._token) and '\n' not in self._token and '\r' not in self._token,
                'invalid_credential')
        self._opener = build_opener(NoRedirect())

    def request(self, method, path, body=None):
        require(path.startswith('/repos/') and not any(c in path for c in '\r\n'), 'invalid_api_path')
        request = Request('https://api.github.com' + path,
            data=None if body is None else json.dumps(body).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self._token,
                     'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json',
                     'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'ProofRail-Pilot'})
        try:
            with self._opener.open(request, timeout=20) as response:
                return json.load(response)
        except Exception:
            raise RuntimeError('provider_outcome_unknown') from None


class Journal:
    """Explicitly initialized, separate replay domain; never auto-create on restore."""
    @classmethod
    def initialize(cls, path):
        path = Path(path)
        # Exclusive creation prevents accidental overwrite of retained state.
        import os
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with sqlite3.connect(path) as db:
            db.executescript('''
              CREATE TABLE dispatches (
                nonce TEXT PRIMARY KEY, authority TEXT NOT NULL UNIQUE,
                binding TEXT NOT NULL, execution_id TEXT UNIQUE,
                request TEXT, checkpoint_root TEXT, result TEXT);
            ''')
        return cls(path)

    def __init__(self, path):
        self.path = Path(path).resolve()
        require(self.path.is_file(), 'retained_journal_missing')
        with self.db() as db:
            db.execute('SELECT nonce FROM dispatches LIMIT 1')

    def db(self):
        # mode=rw avoids silently creating an empty journal after deletion.
        from contextlib import closing
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return closing(db)

    def verify_recovery_state(self, ledger):
        """A stale registry blocks new admissions, including different nonces."""
        with self.db() as db:
            rows = db.execute('SELECT * FROM dispatches').fetchall()
        for row in rows:
            require(row['execution_id'] is not None, 'incomplete_checkpoint_operator_recovery_required')
            record, started = ledger.get(row['execution_id'])
            request = json.loads(row['request'])
            require(started and full_digest(record) == request['consumption_digest'],
                    'recovery_checkpoint_mismatch')
            require(record['permit_nonce'] == row['nonce'] and
                    record['authority_digest'] == row['authority'], 'recovery_claim_mismatch')

    def reserve(self, authority, binding):
        with self.db() as db:
            try:
                db.execute('INSERT INTO dispatches(nonce,authority,binding) VALUES(?,?,?)',
                           (authority['nonce'], full_digest(authority), full_digest(binding)))
                db.commit()
            except sqlite3.IntegrityError:
                raise ValueError('retained_authority_already_reserved') from None

    def prepared(self, nonce, execution_id, request, checkpoint_root):
        with self.db() as db:
            cur = db.execute('UPDATE dispatches SET execution_id=?,request=?,checkpoint_root=? '
                             'WHERE nonce=? AND execution_id IS NULL',
                             (execution_id, json.dumps(request), checkpoint_root, nonce))
            require(cur.rowcount == 1, 'journal_prepare_conflict')
            db.commit()

    def get(self, nonce):
        with self.db() as db:
            row = db.execute('SELECT * FROM dispatches WHERE nonce=?', (nonce,)).fetchone()
        require(row is not None, 'journal_reservation_missing')
        return dict(row)

    def observed(self, nonce, result):
        with self.db() as db:
            db.execute('UPDATE dispatches SET result=? WHERE nonce=?', (json.dumps(result), nonce))
            db.commit()


class Dispatcher:
    def __init__(self, ledger, journal, api, *, repository, branch, path, trust):
        require(Path(ledger.path).resolve() != journal.path, 'separate_journal_required')
        require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) is not None,
                'invalid_repository')
        require(branch.startswith('trial/emergence-') and
                all(re.fullmatch(r'[A-Za-z0-9_-]+', x) for x in branch.split('/')),
                'invalid_branch')
        require(path.startswith('evidence/') and
                all(re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', x)
                    for x in path.split('/')), 'invalid_path')
        self.ledger, self.journal, self.api, self.trust = ledger, journal, api, trust
        self.repository, self.branch, self.path = repository, branch, path
        self.prefix = '/repos/' + repository

    def call(self, method, suffix, body=None):
        return self.api.request(method, self.prefix + suffix, body)

    def scope(self, contract):
        p = contract['parameters']
        require((p['repository'], p['branch'], p['path']) ==
                (self.repository, self.branch, self.path), 'dispatcher_scope_mismatch')
        require(contract['action_type'] == 'github_artifact_commit' and
                contract['capability'] == 'publish-artifact', 'unsupported_dispatch_action')
        require(all(re.fullmatch('[0-9a-f]{40}', p[k]) for k in ('parent_sha', 'base_tree')),
                'invalid_git_object')
        return p

    def dispatch(self, handoff, contract, *, clock=time.time):
        handoff, contract = copy.deepcopy(handoff), copy.deepcopy(contract)
        p = self.scope(contract)
        binding = verify_handoff(handoff, contract, self.trust, now=int(clock()))
        authority = handoff['payload']['authority']
        require('trust' not in authority, 'checkpoint_authority_not_supported')
        # Durable reservation precedes local consumption and all provider writes.
        # Any crash from here burns the permission; no automatic release/retry.
        self.journal.verify_recovery_state(self.ledger)
        self.journal.reserve(authority, binding)
        claim = self.ledger.consume(handoff, contract, self.trust, clock=clock)
        request = prepare_commit(self.ledger, claim['execution_id'], handoff, contract,
                                 self.trust, clock=clock)
        self.journal.prepared(authority['nonce'], claim['execution_id'], request,
                              replay_registry_root(self.ledger.path))
        head = self.call('GET', '/git/ref/heads/' + quote(self.branch, safe='/'))
        require(head['object']['sha'] == p['parent_sha'], 'branch_parent_changed')
        parent = self.call('GET', '/git/commits/' + p['parent_sha'])
        require(parent['tree']['sha'] == p['base_tree'], 'base_tree_not_parent_tree')
        verify_handoff(handoff, contract, self.trust, now=int(clock()))
        tree = self.call('POST', '/git/trees', {'base_tree': p['base_tree'], 'tree': [
            {'path': self.path, 'mode': '100644', 'type': 'blob', 'content': request['content']}]})
        commit = self.call('POST', '/git/commits', {'message': 'ProofRail execution ' + claim['execution_id'],
                            'tree': tree['sha'], 'parents': [p['parent_sha']]})
        # GitHub REST is fast-forward-only, NOT an expected-head CAS. Concurrent
        # divergence fails; hostile ref rewinds require external branch controls.
        verify_handoff(handoff, contract, self.trust, now=int(clock()))
        self.call('PATCH', '/git/refs/heads/' + quote(self.branch, safe='/'),
                  {'sha': commit['sha'], 'force': False})
        return self.recover(handoff, contract)

    def recover(self, handoff, contract):
        """Only GET requests. Unknown/mismatched effects never trigger another write."""
        handoff, contract = copy.deepcopy(handoff), copy.deepcopy(contract)
        self.scope(contract)
        authority = handoff['payload']['authority']
        row = self.journal.get(authority['nonce'])
        require(row['authority'] == full_digest(authority), 'journal_authority_changed')
        require(row['execution_id'] is not None, 'reservation_incomplete_no_retry')
        consumption, started = self.ledger.get(row['execution_id'])
        binding = verify_handoff(handoff, contract, self.trust, now=consumption['consumed_at'])
        require(row['binding'] == full_digest(binding), 'journal_binding_changed')
        require(started, 'restored_dispatch_state')
        # Reconstruct rather than trust journal-supplied destination bytes.
        head = self.call('GET', '/git/ref/heads/' + quote(self.branch, safe='/'))['object']['sha']
        require(re.fullmatch('[0-9a-f]{40}', head) is not None, 'invalid_provider_sha')
        commit = self.call('GET', '/git/commits/' + head)
        file = self.call('GET', '/contents/' + quote(self.path, safe='/') + '?ref=' + head)
        require(file.get('encoding') == 'base64', 'provider_encoding')
        content = base64.b64decode(''.join(file['content'].split()), validate=True).decode('utf-8')
        result = verify_commit(self.ledger, row['execution_id'], handoff, contract, self.trust,
            commit=commit, file_content=content, repository=self.repository, path=self.path, observed_ref=head)
        result['scope'] = 'Dispatcher-owned authenticated GitHub readback'
        result['recovery_writes'] = 0
        self.journal.observed(authority['nonce'], result)
        return result
