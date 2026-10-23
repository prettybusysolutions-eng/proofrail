"""ProofRail-governed work-order creation: the only path to the provider's create call.

New capability (see docs/WRN_BASELINE_ASSESSMENT.md): on main the Action Authority
Envelope v1 can be minted and verified but is not connected to any execution path.
This module connects it:

  AuthorityIssuer.issue  validates a signed approval against current records and
                         policy, then mints a standard envelope with
                         proofrail.envelope.mint_action_authority_envelope.
  Gateway.admit          at the moment of execution recomputes the expected effect
                         and all four roots from CURRENT records, verifies the
                         envelope with proofrail.envelope.verify_action_authority_envelope
                         plus the checks that function does not make (issuer role,
                         issuer key, subject, not-before, no unsupported trust
                         block), consumes it atomically in a ProofRail replay
                         registry (same tables and transaction as
                         proofrail.permit.consume_permit), re-checks revocation and
                         roots after consumption, then calls the provider once.
  Observer.observe       reads provider state independently and signs what it saw.
  Gateway.reconcile      reads only. Never repeats the create call.

A provider response is never treated as proof of the authorized effect (lesson of
evidence/live-github-2026-10-19): only an independent read that matches the exact
authorized parameters reconciles.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from proofrail.envelope import mint_action_authority_envelope, verify_action_authority_envelope
from proofrail.permit import PERMIT_ISSUER_ROLES
from proofrail.trust import replay_claim_exists

import lifecycle
from consumption_provenance import read_registry_claim
from policy import evidence_root
from records import Clock, Identity, PilotError, Registry, decode_public, digest, require, utc, validate
from store import Store

ACTION_TYPE = 'facility.create_work_order'
UNKNOWN = 'provider_outcome_unknown'
ADAPTER_CONTRACT = {'name': 'wrn-facility-work-order', 'version': 'v1', 'idempotency_required': True}


def work_order_target(p: dict) -> str:
    return 'workorder:%s:%s:%s:%s' % (p['provider_id'], p['tenant_id'], p['facility_id'], p['area_id'])


def expected_parameters(problem: dict, plan: dict, approval: dict, client_reference: str) -> dict:
    return {'tenant_id': problem['tenant_id'], 'facility_id': plan['target']['facility_id'],
            'area_id': plan['target']['area_id'], 'provider_id': plan['provider_id'],
            'problem_id': problem['problem_id'], 'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'],
            'scope_revision': plan['scope_revision'], 'max_cost': approval['approved_maximum_cost'],
            'currency': plan['currency'], 'client_reference': client_reference}


def current_roots(store: Store, registry: Registry, policy_root: str, tenant_id: str, problem_id: str,
                  plan_id: str, approval_id: str) -> dict:
    """The four ProofRail roots, recomputed from the records as they are now."""
    problem = store.get(tenant_id, 'problem', problem_id)
    state = state_inputs(store, tenant_id, problem_id, plan_id, approval_id)
    # Recompute the evidence root from the evidence references: the stored field alone is a claim.
    return {'identity': registry.root(tenant_id), 'evidence': evidence_root(problem['evidence_refs']), 'policy': policy_root,
            'state': digest(state)}


def state_inputs(store: Store, tenant_id: str, problem_id: str, plan_id: str, approval_id: str) -> dict:
    problem = store.get(tenant_id, 'problem', problem_id)
    plan = store.get(tenant_id, 'plan', plan_id)
    approval = store.get(tenant_id, 'approval', approval_id)
    return {'problem_id': problem_id, 'problem_revision': problem['revision'], 'problem_status': problem['status'],
            'problem_digest': digest(problem), 'plan_digest': plan['plan_digest'],
            'approval_digest': approval['approval_digest'],
            'approval_revoked': any(r['approval_id'] == approval_id for r in store.all(tenant_id, 'revocation')),
            'work_state': store.state(tenant_id, problem_id)}


def success_predicate(parameters: dict) -> str:
    return digest({'predicate': 'exactly_one_provider_work_order_matching_all_parameters',
                   'parameters': parameters})


class AuthorityIssuer:
    """Holds the authority signing key (ProofRail issuer role 'verifier'). Separate from the gateway."""

    def __init__(self, identity: Identity, registry: Registry, store: Store, policy, clock: Clock):
        require('authority_issuer' in identity.principal.roles, 'issuer_role_required')
        self.identity, self.registry, self.store, self.policy, self.clock = identity, registry, store, policy, clock

    def issue(self, tenant_id: str, *, problem_id: str, plan_id: str, approval_id: str, gateway_id: str,
              validity_minutes: int = 60) -> dict:
        problem = self.store.get(tenant_id, 'problem', problem_id)
        plan = self.store.get(tenant_id, 'plan', plan_id)
        approval = self.store.get(tenant_id, 'approval', approval_id)
        self.policy.check_approval(self.registry, problem, plan, approval, now=self.clock.now())
        require(not any(r['approval_id'] == approval_id for r in self.store.all(tenant_id, 'revocation')),
                'approval_revoked')
        require(self.store.state(tenant_id, problem_id) == 'APPROVED', 'work_not_approved')
        envelope_id = str(uuid.uuid4())
        parameters = expected_parameters(problem, plan, approval, envelope_id)
        expires = min(utc(approval['expires_at']), self.clock.now() + timedelta(minutes=validity_minutes))
        envelope = mint_action_authority_envelope(
            roots=current_roots(self.store, self.registry, self.policy.root(tenant_id), tenant_id,
                                problem_id, plan_id, approval_id),
            approval_digest=approval['approval_digest'], action_type=ACTION_TYPE,
            target=work_order_target(parameters), parameters=parameters,
            subject_principal_id=gateway_id, subject_role='executor',
            issuer_principal_id=self.identity.principal.principal_id, issuer_role='verifier',
            adapter_contract=ADAPTER_CONTRACT,
            observation_contract={'name': 'wrn-provider-read', 'version': 'v1', 'minimum_confirmations': 1,
                                  'success_predicate_digest': success_predicate(parameters)},
            nonce=secrets.token_hex(32), expires_at=expires, private_key=self.identity.private_key,
            key_id=self.identity.principal.key_id, now=self.clock.now(), envelope_id=envelope_id)
        self.store.audit(tenant_id, 'authority_issued', envelope_id,
                         {'envelope_digest': envelope['record_hash'], 'effect_digest': envelope['effect']['effect_digest']})
        return envelope


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('provider_redirect_rejected')


class ProviderClient:
    """HTTP client for one provider origin. Any failure is an unknown outcome, never a refusal."""

    def __init__(self, base_url: str, client_id: str, timeout: float = 5.0):
        require(base_url.startswith('http://127.0.0.1:') or base_url.startswith('https://'), 'provider_origin')
        self.base_url, self.client_id, self.timeout = base_url.rstrip('/'), client_id, timeout
        self._opener = build_opener(NoRedirect())

    def call(self, method: str, path: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, Any]:
        request = Request(self.base_url + path, method=method,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', 'X-Client-Id': self.client_id,
                                   **(headers or {})})
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, None
        except Exception:
            raise PilotError(UNKNOWN) from None


class Observer:
    """Independent provider read, signed by the observer's own key (independence: provider_system_record)."""

    def __init__(self, identity: Identity, client: ProviderClient, clock: Clock):
        require('provider_observer' in identity.principal.roles, 'observer_role_required')
        self.identity, self.client, self.clock = identity, client, clock

    def observe(self, tenant_id: str, client_reference: str) -> dict:
        try:
            status, body = self.client.call(
                'GET', '/v1/tenants/%s/work-orders?client_reference=%s' % (quote(tenant_id), quote(client_reference)))
        except PilotError:
            status, body = None, None
        readable = status == 200 and isinstance(body, dict) and isinstance(body.get('work_orders'), list)
        orders = body['work_orders'] if readable else None
        findings = {'work_order': {'readable': readable, 'orders': orders}}
        record = {'kind': 'wrn.observation-record.v1', 'observation_id': 'obs-' + uuid.uuid4().hex[:16],
                  'tenant_id': tenant_id, 'observer_principal': self.identity.principal.principal_id,
                  'observer_role': 'provider_observer',
                  'observed_subject': {'kind': 'work_order', 'id': client_reference},
                  'observation_type': 'provider_work_order_state', 'observation_time': self.clock.text(),
                  'evidence_refs': [], 'findings': findings, 'observation_digest': digest(findings),
                  'credential_reference': self.identity.principal.key_id,
                  'independence_class': 'provider_system_record'}
        signed = self.identity.sign(record)
        validate('observation_record', signed)
        return signed


class Gateway:
    """The authority boundary. Holds no authority key; it can only spend authority issued to it."""

    def __init__(self, identity: Identity, *, registry: Registry, store: Store, policy, clock: Clock,
                 replay_registry: Path, issuer_id: str, provider: ProviderClient, observer: Observer):
        require('gateway' in identity.principal.roles, 'gateway_role_required')
        require(Path(replay_registry).resolve() != Path(store.path).resolve(), 'separate_replay_registry_required')
        self.identity, self.registry, self.store, self.policy, self.clock = identity, registry, store, policy, clock
        self.replay_registry = Path(replay_registry)
        self.issuer_id, self.provider, self.observer = issuer_id, provider, observer
        self.provider_calls = 0          # counted from calls actually issued

    # -------------------------------------------------------------- admission
    def _verify(self, tenant_id: str, envelope: dict) -> dict:
        require(isinstance(envelope, dict) and isinstance(envelope.get('effect'), dict), 'invalid_envelope')
        params = envelope['effect'].get('parameters')
        require(isinstance(params, dict) and params.get('tenant_id') == tenant_id, 'tenant_mismatch')
        problem = self.store.get(tenant_id, 'problem', params.get('problem_id', ''))
        plan = self.store.get(tenant_id, 'plan', params.get('plan_id', ''))
        approvals = [a for a in self.store.all(tenant_id, 'approval')
                     if a['approval_digest'] == envelope.get('approval_digest')]
        require(len(approvals) == 1, 'approval_scope_changed')
        approval = approvals[0]
        # Expected values come from current records, never from the envelope itself.
        expected = expected_parameters(problem, plan, approval, envelope.get('envelope_id', ''))
        roots = current_roots(self.store, self.registry, self.policy.root(tenant_id), tenant_id,
                              problem['problem_id'], plan['plan_id'], approval['approval_id'])
        issuer = self.registry.get(self.issuer_id)
        require('authority_issuer' in issuer.roles and issuer.tenant_id == tenant_id, 'issuer_not_trusted')
        # Checks verify_action_authority_envelope does not make (WRN_THREAT_MODEL F-1, F-2):
        require(envelope.get('issuer') == {'principal_id': issuer.principal_id, 'role': 'verifier'} and
                envelope['issuer']['role'] in PERMIT_ISSUER_ROLES, 'issuer_changed')
        require((envelope.get('signature') or {}).get('key_id') == issuer.key_id, 'issuer_key_changed')
        require(envelope.get('subject') == {'principal_id': self.identity.principal.principal_id,
                                            'role': 'executor'}, 'subject_changed')
        require('trust' not in envelope, 'checkpoint_authority_not_supported')
        try:
            verify_action_authority_envelope(
                envelope, public_key=decode_public(issuer.public_key), expected_roots=roots,
                expected_approval_digest=approval['approval_digest'], action_type=ACTION_TYPE,
                target=work_order_target(expected), parameters=expected, now=self.clock.now())
        except PilotError:
            raise
        except Exception as exc:  # PermitError carries a stable .code; anything else is an invalid envelope
            raise PilotError(getattr(exc, 'code', None) or 'invalid_envelope') from None
        require(utc(envelope['issued_at']) <= self.clock.now(), 'authority_not_yet_valid')
        require(envelope['observation_contract']['success_predicate_digest'] == success_predicate(expected),
                'predicate_changed')
        self.policy.check_approval(self.registry, problem, plan, approval, now=self.clock.now())
        return {'problem': problem, 'plan': plan, 'approval': approval, 'parameters': expected, 'roots': roots}

    def _consume(self, envelope: dict) -> str:
        """Same registry schema and transaction as proofrail.permit.consume_permit."""
        with closing(sqlite3.connect(self.replay_registry, isolation_level=None, timeout=10)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS permit_claims (permit_hash TEXT PRIMARY KEY, nonce TEXT NOT NULL UNIQUE,
                    executor_id TEXT NOT NULL, executing_at TEXT NOT NULL, consumed_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS permit_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    permit_hash TEXT NOT NULL, state TEXT NOT NULL, observed_at TEXT NOT NULL,
                    executor_id TEXT NOT NULL);''')
            db.execute('BEGIN IMMEDIATE')
            try:
                now, executor = self.clock.text(), self.identity.principal.principal_id
                db.execute('INSERT INTO permit_claims VALUES (?,?,?,?,?)',
                           (envelope['record_hash'], envelope['nonce'], executor, now, now))
                db.execute('INSERT INTO permit_events (permit_hash,state,observed_at,executor_id) VALUES '
                           '(?,?,?,?),(?,?,?,?)', (envelope['record_hash'], 'EXECUTING', now, executor,
                                                   envelope['record_hash'], 'CONSUMED', now, executor))
                db.execute('COMMIT')
            except sqlite3.IntegrityError:
                db.execute('ROLLBACK')
                raise PilotError('permit_replayed') from None
            except BaseException:
                db.execute('ROLLBACK')
                raise
        return digest({'permit_hash': envelope['record_hash'], 'nonce': envelope['nonce'],
                       'executor': self.identity.principal.principal_id})

    def _attest_consumption(self, tenant_id: str, envelope: dict) -> dict:
        """Sign a digest of the committed registry rows before any provider write.

        This is a gateway attestation, not an independent checkpoint/anchor.
        Any failure aborts admission after permit spending and before the effect.
        """
        rowset = read_registry_claim(self.replay_registry, envelope['record_hash'])
        claim = rowset['claim']
        require(claim['nonce'] == envelope['nonce'] and
                claim['executor_id'] == self.identity.principal.principal_id and
                [event['state'] for event in rowset['events']] == ['EXECUTING', 'CONSUMED'],
                'registry_consumption_inconsistent')
        record = {'kind': 'wrn.consumption-attestation.v1',
                  'tenant_id': tenant_id,
                  'envelope_digest': envelope['record_hash'],
                  'nonce': claim['nonce'],
                  'executor_principal': claim['executor_id'],
                  'consumed_at': claim['consumed_at'],
                  'registry_claim_digest': digest(rowset)}
        signed = self.identity.sign(record)
        validate('consumption_attestation', signed)
        return signed

    def _reference(self, tenant_id: str, envelope: dict, state: str, *, consumption=None, operation=None,
                   reconciliation=None, replace=True) -> dict:
        ref = {'kind': 'wrn.execution-authority-reference.v1', 'tenant_id': tenant_id,
               'envelope_id': envelope['envelope_id'], 'envelope_digest': envelope['record_hash'],
               'effect_digest': envelope['effect']['effect_digest'], 'approval_digest': envelope['approval_digest'],
               'target': envelope['effect']['target'], 'authority_state': state,
               'consumption_reference': consumption, 'provider_operation_reference': operation,
               'reconciliation_reference': reconciliation}
        validate('execution_authority_reference', ref)
        body = {'reference': ref, 'envelope': envelope}
        if replace:   # update the reference; keep snapshots and markers recorded earlier
            body = {**self.store.get(tenant_id, 'authority', envelope['envelope_id']), **body}
        self.store.put(tenant_id, 'authority', envelope['envelope_id'], body, replace=replace)
        return ref

    def admit(self, tenant_id: str, envelope: dict) -> dict:
        """Verify, consume, call the provider once, then reconcile by independent observation."""
        require(isinstance(envelope, dict) and isinstance(envelope.get('record_hash'), str) and
                isinstance(envelope.get('envelope_id'), str), 'invalid_envelope')
        # Layered single-use checks, each with its own reason:
        #  1. ProofRail's replay registry (survives restarts);
        #  2. the business store's own record of admitted envelopes (survives a rollback of the
        #     replay registry alone);
        #  3. the state root inside verification (work state has moved on after admission).
        if self.replay_registry.exists() and replay_claim_exists(self.replay_registry, envelope['record_hash']):
            raise PilotError('permit_replayed')
        require(not self._admitted(tenant_id, envelope['envelope_id']), 'authority_already_admitted')
        checked = self._verify(tenant_id, envelope)        # refusals here leave no trace in the registry
        problem_id = checked['problem']['problem_id']
        consumption = self._consume(envelope)             # single use; from here the authority is spent
        try:
            self._reference(tenant_id, envelope, 'CONSUMED', consumption=consumption, replace=False)
            attestation = self._attest_consumption(tenant_id, envelope)
            recorded = self.store.get(tenant_id, 'authority', envelope['envelope_id'])
            self.store.put(tenant_id, 'authority', envelope['envelope_id'],
                           {**recorded, 'consumption_attestation': attestation}, replace=True)
        except PilotError as exc:
            if exc.reason == 'record_exists':     # lost a race against a concurrent admission
                raise PilotError('authority_already_admitted') from None
            raise
        # Keep the exact inputs the roots were computed from, so an exported case can be
        # re-verified offline (identity and policy roots recomputed from these snapshots).
        stored = self.store.get(tenant_id, 'authority', envelope['envelope_id'])
        self.store.put(tenant_id, 'authority', envelope['envelope_id'],
                       {**stored, 'identity_snapshot': self.registry.snapshot(tenant_id),
                        'policy_snapshot': self.policy.doc(tenant_id),
                        'state_inputs': state_inputs(self.store, tenant_id, problem_id, checked['plan']['plan_id'],
                                                     checked['approval']['approval_id'])}, replace=True)
        self.store.audit(tenant_id, 'authority_consumed', envelope['envelope_id'], {'consumption': consumption})
        # Re-check after consumption: a revocation, a role change or a concurrent transition that
        # landed between verification and the claim must stop the provider call.
        try:
            after = current_roots(self.store, self.registry, self.policy.root(tenant_id), tenant_id, problem_id,
                                  checked['plan']['plan_id'], checked['approval']['approval_id'])
            require(after == checked['roots'], 'state_changed_during_admission')
            self.store.move(tenant_id, problem_id, 'APPROVED',
                            lifecycle.transition('APPROVED', 'admit_work_order', {'gateway'}))
        except PilotError as exc:
            stored = self.store.get(tenant_id, 'authority', envelope['envelope_id'])
            self.store.put(tenant_id, 'authority', envelope['envelope_id'], {**stored, 'aborted': exc.reason},
                           replace=True)
            self.store.audit(tenant_id, 'admission_aborted_after_consumption', envelope['envelope_id'],
                             {'reason': exc.reason})
            raise
        self.store.audit(tenant_id, 'provider_call', envelope['envelope_id'], {'idempotency_key': envelope['record_hash']})
        self.provider_calls += 1
        try:
            status, response = self.provider.call(
                'POST', '/v1/tenants/%s/work-orders' % quote(tenant_id), checked['parameters'],
                headers={'Idempotency-Key': envelope['record_hash']})
            claimed = response if status in (200, 201) and isinstance(response, dict) else None
            outcome = 'claimed_success' if claimed else UNKNOWN
        except PilotError:
            claimed, outcome = None, UNKNOWN
        return self._reconcile(tenant_id, envelope, checked['parameters'], claimed, outcome)

    def still_matches(self, tenant_id: str, envelope_id: str) -> bool:
        """Fresh read: does exactly one order still match every authorized parameter? Reads only."""
        stored = self.store.get(tenant_id, 'authority', envelope_id)
        parameters = stored['envelope']['effect']['parameters']
        observation = self.observer.observe(tenant_id, envelope_id)
        self.store.put(tenant_id, 'observation', observation['observation_id'], observation)
        seen = observation['findings']['work_order']
        if not seen['readable'] or len(seen['orders']) != 1:
            return False
        order = seen['orders'][0]
        return (order.get('tenant_id') == tenant_id and
                order.get('work_order_id') == stored['reference']['provider_operation_reference'] and
                all(order.get(k) == v for k, v in parameters.items() if k != 'tenant_id'))

    def _reconcile(self, tenant_id, envelope, parameters, claimed, outcome) -> dict:
        observation = self.observer.observe(tenant_id, envelope['envelope_id'])
        self.store.put(tenant_id, 'observation', observation['observation_id'], observation)
        seen = observation['findings']['work_order']
        problem_id = parameters['problem_id']
        if not seen['readable']:
            state, reason, order = 'EXECUTION_UNKNOWN', 'provider_unreadable', None
        else:
            orders = seen['orders']
            exact = [o for o in orders if o.get('tenant_id') == tenant_id and
                     all(o.get(k) == v for k, v in parameters.items() if k != 'tenant_id')]
            order = exact[0] if len(exact) == 1 and len(orders) == 1 else None
            if len(orders) > 1:
                state, reason = 'RECONCILIATION_FAILED', 'duplicate_work_orders'
            elif len(orders) == 1 and order is None:
                state, reason = 'RECONCILIATION_FAILED', 'work_order_differs_from_authorized_effect'
            elif order is not None and claimed is not None and (
                    claimed.get('work_order_id') != order['work_order_id'] or claimed.get('tenant_id') != tenant_id):
                state, reason = 'RECONCILIATION_FAILED', 'provider_response_inconsistent_with_observation'
            elif order is not None:
                state, reason = 'RECONCILED', 'observed_exact_effect'
            elif claimed is not None:
                state, reason = 'RECONCILIATION_FAILED', 'provider_success_not_observed'
            else:
                state, reason = 'EXECUTION_UNKNOWN', 'not_yet_observed'
        ref = self._reference(tenant_id, envelope, state,
                              consumption=self.store.get(tenant_id, 'authority', envelope['envelope_id'])
                              ['reference']['consumption_reference'],
                              operation=order['work_order_id'] if state == 'RECONCILED' else None,
                              reconciliation=observation['record_hash'])
        if state == 'RECONCILED' and self.store.state(tenant_id, problem_id) == 'WORK_ORDER_PENDING':
            self.store.move(tenant_id, problem_id, 'WORK_ORDER_PENDING',
                            lifecycle.transition('WORK_ORDER_PENDING', 'confirm_work_order', {'provider_observer'}))
        self.store.audit(tenant_id, 'reconciliation', envelope['envelope_id'],
                         {'authority_state': state, 'reason': reason, 'provider_outcome': outcome,
                          'observation': observation['record_hash']})
        return {'authority_state': state, 'reason': reason, 'provider_outcome': outcome,
                'work_order_id': ref['provider_operation_reference'], 'observation': observation['record_hash'],
                'reference': ref}

    def _admitted(self, tenant_id: str, envelope_id: str) -> bool:
        try:
            self.store.get(tenant_id, 'authority', envelope_id)
            return True
        except PilotError:
            return False

    def reconcile(self, tenant_id: str, envelope_id: str) -> dict:
        """Read-only follow-up for an unknown outcome. Never repeats the create call.

        CONSUMED without a recorded outcome means the process stopped after consuming
        (for example a crash while the provider call was in flight): it is resolved the
        same way as EXECUTION_UNKNOWN, by reads only. An admission aborted before any
        provider call is not reconcilable; it needs new authority.
        """
        stored = self.store.get(tenant_id, 'authority', envelope_id)
        state = stored['reference']['authority_state']
        require(not stored.get('aborted'), 'admission_aborted_before_provider_call', stored.get('aborted', ''))
        require(state in ('EXECUTION_UNKNOWN', 'CONSUMED'), 'reconciliation_not_pending', state)
        calls_before = self.provider_calls
        result = self._reconcile(tenant_id, stored['envelope'], stored['envelope']['effect']['parameters'],
                                 None, UNKNOWN)
        require(self.provider_calls == calls_before, 'reconciliation_issued_provider_write')
        return result
