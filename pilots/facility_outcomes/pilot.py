"""The facility intervention workflow, one tenant-scoped call per step.

Every step takes the acting Identity and the tenant, applies its lifecycle
transition with compare-and-set, and appends to the audit chain. The only path to
the provider's create call is ProofRailGateway.admit.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

import lifecycle
import outcome_verifier
import settlement_simulator
from policy import Policy, approval_digest, evidence_root, plan_digest
from proofrail_gateway import AuthorityIssuer, Gateway, Observer, ProviderClient
from records import Clock, Identity, PilotError, Registry, digest, require, stamp, validate
from store import Store


class FacilityPilot:
    def __init__(self, workdir: Path, clock: Clock, provider_url: str, *, provider_timeout: float = 5.0):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.clock, self.registry, self.policy = clock, Registry(), Policy()
        self.store = Store(self.workdir / 'business.sqlite3')
        self.replay_registry = self.workdir / 'retained' / 'replay-registry.sqlite3'
        self.replay_registry.parent.mkdir(exist_ok=True)
        self.provider_url, self.provider_timeout = provider_url, provider_timeout
        self.issuers: dict[str, AuthorityIssuer] = {}
        self.gateways: dict[str, Gateway] = {}

    # ------------------------------------------------------------------ setup
    def install_tenant(self, tenant_id: str, *, issuer: Identity, gateway: Identity, observer: Identity,
                       policy: dict) -> None:
        self.policy.set(tenant_id, policy)
        self.issuers[tenant_id] = AuthorityIssuer(issuer, self.registry, self.store, self.policy, self.clock)
        observer_client = ProviderClient(self.provider_url, 'observer-' + tenant_id, timeout=self.provider_timeout)
        self.gateways[tenant_id] = Gateway(
            gateway, registry=self.registry, store=self.store, policy=self.policy, clock=self.clock,
            replay_registry=self.replay_registry, issuer_id=issuer.principal.principal_id,
            provider=ProviderClient(self.provider_url, 'gateway-' + tenant_id, timeout=self.provider_timeout),
            observer=Observer(observer, observer_client, self.clock))

    def _move(self, actor: Identity, tenant_id: str, problem_id: str, event: str) -> str:
        require(actor.principal.tenant_id == tenant_id, 'actor_tenant_mismatch')
        current = self.store.state(tenant_id, problem_id)
        new = lifecycle.transition(current, event, actor.principal.roles)
        self.store.move(tenant_id, problem_id, current, new)
        self.store.audit(tenant_id, event, problem_id, {'from': current, 'to': new,
                                                         'actor': actor.principal.principal_id})
        return new

    def _contractors(self, provider_org: str) -> set:
        return {p.principal_id for p in self.registry.principals()
                if p.organization == provider_org and p.roles & {'contractor', 'provider'}}

    # ------------------------------------------------------------------ layer A: problem intelligence
    def submit_problem(self, reporter: Identity, tenant_id: str, *, facility_id: str, area_id: str,
                       description: str, evidence_refs: list, ai_assisted: bool = False) -> dict:
        record = {'kind': 'wrn.problem-record.v1', 'problem_id': 'prb-' + uuid.uuid4().hex[:12],
                  'tenant_id': tenant_id, 'facility_id': facility_id, 'asset_or_area_id': area_id,
                  'reported_at': self.clock.text(), 'reported_by': reporter.principal.principal_id,
                  'problem_type': 'non_hazardous_debris', 'description': description, 'risk_class': 'non_hazardous',
                  'evidence_refs': evidence_refs, 'evidence_root': evidence_root(evidence_refs),
                  'status': 'REPORTED', 'revision': 1,
                  'provenance': {'source': 'operator_report', 'ai_assisted': ai_assisted}}
        signed = reporter.sign(record)
        validate('problem_record', signed)
        self.registry.signer(signed, role='reporter', tenant_id=tenant_id)
        self.store.put(tenant_id, 'problem', record['problem_id'], signed)
        self._move(reporter, tenant_id, record['problem_id'], 'submit_problem')
        return signed

    def confirm_problem(self, reviewer: Identity, tenant_id: str, problem_id: str) -> dict:
        """Human review of a consequential conclusion. AI assistance never confirms a problem."""
        self._move(reviewer, tenant_id, problem_id, 'begin_review')
        problem = self.store.get(tenant_id, 'problem', problem_id)
        revised = reviewer.sign({**{k: v for k, v in problem.items() if k not in ('record_hash', 'signature')},
                                 'status': 'CONFIRMED', 'revision': problem['revision'] + 1})
        validate('problem_record', revised)
        self.store.put(tenant_id, 'problem', problem_id, revised, replace=True)
        self.store.audit(tenant_id, 'problem_confirmed', problem_id, {'revision': revised['revision']})
        return revised

    # ------------------------------------------------------------------ layer B: coordination
    def propose_plan(self, planner: Identity, tenant_id: str, problem_id: str, *, provider_id: str, quote: int,
                     criteria: list, window_hours: int = 48, scope_revision: int = 1) -> dict:
        problem = self.store.get(tenant_id, 'problem', problem_id)
        start = self.clock.now()
        plan = {'kind': 'wrn.intervention-plan.v1', 'plan_id': 'pln-' + uuid.uuid4().hex[:12],
                'problem_id': problem_id, 'scope_revision': scope_revision, 'requested_action': 'create_work_order',
                'target': {'tenant_id': tenant_id, 'facility_id': problem['facility_id'],
                           'area_id': problem['asset_or_area_id']},
                'provider_id': provider_id, 'estimated_cost': quote, 'currency': self.policy.doc(tenant_id)['currency'],
                'acceptance_criteria': criteria,
                'expected_completion_window': {'start': stamp(start), 'end': stamp(start + timedelta(hours=window_hours))},
                'required_observers': [{'role': 'inspector', 'independence_class': 'buyer_designated_inspector'}],
                'policy_root': self.policy.root(tenant_id)}
        plan['plan_digest'] = plan_digest(plan)
        self.policy.check_plan(problem, plan)
        self._move(planner, tenant_id, problem_id, 'propose_plan')
        self.store.put(tenant_id, 'plan', plan['plan_id'], plan)
        return plan

    def amend_plan(self, planner: Identity, tenant_id: str, plan_id: str, **changes) -> dict:
        plan = self.store.get(tenant_id, 'plan', plan_id)
        amended = {**plan, **changes}
        if 'target' in changes or 'provider_id' in changes or 'estimated_cost' in changes:
            amended['scope_revision'] = plan['scope_revision'] + 1
        amended['plan_digest'] = plan_digest(amended)
        validate('intervention_plan', amended)
        self._move(planner, tenant_id, plan['problem_id'], 'amend_plan')
        self.store.put(tenant_id, 'plan', plan_id, amended, replace=True)
        return amended

    def approve(self, approver: Identity, tenant_id: str, plan_id: str, *, maximum_cost: int,
                validity_hours: int = 24) -> dict:
        plan = self.store.get(tenant_id, 'plan', plan_id)
        record = {'kind': 'wrn.approval-record.v1', 'approval_id': 'apr-' + uuid.uuid4().hex[:12],
                  'tenant_id': tenant_id, 'approver_principal': approver.principal.principal_id,
                  'approval_role': 'approver', 'approved_plan_digest': plan['plan_digest'],
                  'approved_maximum_cost': maximum_cost, 'currency': plan['currency'],
                  'approved_provider': plan['provider_id'], 'issued_at': self.clock.text(),
                  'expires_at': stamp(self.clock.now() + timedelta(hours=validity_hours))}
        record['approval_digest'] = approval_digest(record)
        signed = approver.sign(record)
        problem = self.store.get(tenant_id, 'problem', plan['problem_id'])
        self.policy.check_approval(self.registry, problem, plan, signed, now=self.clock.now())
        self._move(approver, tenant_id, plan['problem_id'], 'approve_plan')
        self.store.put(tenant_id, 'approval', record['approval_id'], signed)
        return signed

    def revoke_approval(self, admin: Identity, tenant_id: str, approval_id: str) -> None:
        require(admin.principal.tenant_id == tenant_id and admin.principal.roles & {'tenant_admin', 'approver'},
                'revocation_not_permitted')
        self.store.get(tenant_id, 'approval', approval_id)
        self.store.put(tenant_id, 'revocation', approval_id,
                       {'approval_id': approval_id, 'revoked_by': admin.principal.principal_id,
                        'revoked_at': self.clock.text()})
        self.store.audit(tenant_id, 'approval_revoked', approval_id, {'by': admin.principal.principal_id})

    def cancel(self, admin: Identity, tenant_id: str, problem_id: str) -> str:
        return self._move(admin, tenant_id, problem_id, 'cancel')

    # ------------------------------------------------------------------ layer C: ProofRail execution authority
    def request_authority(self, tenant_id: str, *, problem_id: str, plan_id: str, approval_id: str) -> dict:
        gateway = self.gateways[tenant_id]
        return self.issuers[tenant_id].issue(tenant_id, problem_id=problem_id, plan_id=plan_id,
                                             approval_id=approval_id,
                                             gateway_id=gateway.identity.principal.principal_id)

    def admit(self, tenant_id: str, envelope: dict) -> dict:
        return self.gateways[tenant_id].admit(tenant_id, envelope)

    def reconcile(self, tenant_id: str, envelope_id: str) -> dict:
        return self.gateways[tenant_id].reconcile(tenant_id, envelope_id)

    def _authority_for(self, tenant_id: str, problem_id: str) -> dict:
        found = [a for a in self.store.all(tenant_id, 'authority')
                 if a['envelope']['effect']['parameters']['problem_id'] == problem_id]
        reconciled = [a for a in found if a['reference']['authority_state'] == 'RECONCILED']
        require(len(reconciled) == 1, 'execution_not_reconciled')
        return reconciled[0]

    # ------------------------------------------------------------------ layer D: outcome verification
    def _observation(self, actor: Identity, tenant_id: str, work_order_id: str, *, observation_type: str,
                     role: str, independence: str, evidence_refs: list, criteria: dict | None) -> dict:
        findings = {'criteria': criteria} if criteria is not None else {}
        record = {'kind': 'wrn.observation-record.v1', 'observation_id': 'obs-' + uuid.uuid4().hex[:16],
                  'tenant_id': tenant_id, 'observer_principal': actor.principal.principal_id,
                  'observer_role': role, 'observed_subject': {'kind': 'work_order', 'id': work_order_id},
                  'observation_type': observation_type, 'observation_time': self.clock.text(),
                  'evidence_refs': evidence_refs, 'findings': findings, 'observation_digest': digest(findings),
                  'credential_reference': actor.principal.key_id, 'independence_class': independence}
        signed = actor.sign(record)
        validate('observation_record', signed)
        return signed

    def claim_completion(self, contractor: Identity, tenant_id: str, problem_id: str, *,
                         evidence_refs: list) -> dict:
        authority = self._authority_for(tenant_id, problem_id)
        self._move(contractor, tenant_id, problem_id, 'claim_completion')
        obs = self._observation(contractor, tenant_id, authority['reference']['provider_operation_reference'],
                                observation_type='completion_claim', role='contractor',
                                independence='performer_claim', evidence_refs=evidence_refs,
                                criteria=None)
        self.store.put(tenant_id, 'observation', obs['observation_id'], obs)
        return obs

    def submit_inspection(self, inspector: Identity, tenant_id: str, problem_id: str, *, criteria: dict,
                          evidence_refs: list, subject: str | None = None) -> dict:
        authority = self._authority_for(tenant_id, problem_id)
        self._move(inspector, tenant_id, problem_id, 'submit_inspection')
        obs = self._observation(inspector, tenant_id,
                                subject or authority['reference']['provider_operation_reference'],
                                observation_type='inspection', role='inspector',
                                independence='buyer_designated_inspector', evidence_refs=evidence_refs,
                                criteria=criteria)
        self.store.put(tenant_id, 'observation', obs['observation_id'], obs)
        return obs

    def assess(self, reviewer: Identity, tenant_id: str, problem_id: str) -> dict:
        require(reviewer.principal.tenant_id == tenant_id, 'actor_tenant_mismatch')
        authority = self._authority_for(tenant_id, problem_id)
        plan = self.store.get(tenant_id, 'plan', authority['envelope']['effect']['parameters']['plan_id'])
        problem = self.store.get(tenant_id, 'problem', problem_id)
        provider_org = self.policy.provider_organization(tenant_id, plan['provider_id'])
        work_order_id = authority['reference']['provider_operation_reference']
        envelope_id = authority['envelope']['envelope_id']
        observations = [o for o in self.store.all(tenant_id, 'observation')
                        if (o['observation_type'] == 'provider_work_order_state' and o['observed_subject']['id'] == envelope_id)
                        or (o['observation_type'] != 'provider_work_order_state' and o['observed_subject']['id'] == work_order_id)]
        verdict = outcome_verifier.assess(
            reviewer, registry=self.registry, tenant_id=tenant_id, problem=problem, plan=plan,
            authority=authority, observations=observations, provider_organization=provider_org,
            contractors=self._contractors(provider_org),
            grace_hours=self.policy.doc(tenant_id)['inspection_grace_hours'],
            policy_digest=digest({'outcome_policy': 'wrn.outcome.v1', 'criteria': plan['acceptance_criteria']}),
            now=self.clock.now())
        previous = [v for v in self.store.all(tenant_id, 'verdict') if v['work_order_id'] == work_order_id]
        self.store.put(tenant_id, 'verdict', verdict['outcome_id'], verdict)
        self.store.audit(tenant_id, 'outcome_assessed', verdict['outcome_id'],
                         {'state': verdict['assessment_state'], 'reviewer': reviewer.principal.principal_id})
        disagreement = any(v['assessment_state'] != verdict['assessment_state'] for v in previous)
        if self.store.state(tenant_id, problem_id) == 'OUTCOME_REVIEW':
            if verdict['assessment_state'] == 'DISPUTED' or disagreement:
                self._move(reviewer, tenant_id, problem_id, 'flag_dispute')
            elif verdict['assessment_state'] == 'REJECTED':
                self._move(reviewer, tenant_id, problem_id, 'reject_outcome')
        return verdict

    def buyer_decide(self, buyer: Identity, tenant_id: str, problem_id: str, *, decision: str, reason: str) -> dict:
        authority = self._authority_for(tenant_id, problem_id)
        work_order_id = authority['reference']['provider_operation_reference']
        verdicts = [v for v in self.store.all(tenant_id, 'verdict') if v['work_order_id'] == work_order_id]
        require(verdicts, 'no_verdict')
        latest = verdicts[-1]
        if decision == 'ACCEPTED':
            require(latest['assessment_state'] == 'VERIFIED', 'outcome_not_verified')
        record = buyer.sign({'kind': 'wrn.acceptance-record.v1', 'acceptance_id': 'acc-' + uuid.uuid4().hex[:12],
                             'tenant_id': tenant_id, 'outcome_id': latest['outcome_id'],
                             'outcome_digest': latest['record_hash'], 'buyer_principal': buyer.principal.principal_id,
                             'decision': decision, 'decided_at': self.clock.text(), 'reason': reason})
        validate('acceptance_record', record)
        self.registry.signer(record, role='buyer', tenant_id=tenant_id)
        self._move(buyer, tenant_id, problem_id, 'accept_outcome' if decision == 'ACCEPTED' else 'dispute_outcome')
        self.store.put(tenant_id, 'acceptance', record['acceptance_id'], record)
        return record

    # ------------------------------------------------------------------ layer E: settlement (simulated)
    def submit_invoice(self, provider: Identity, tenant_id: str, *, work_order_id: str, amount: int,
                       currency: str | None = None) -> dict:
        record = provider.sign({'kind': 'wrn.invoice-record.v1', 'invoice_id': 'inv-' + uuid.uuid4().hex[:12],
                                'tenant_id': tenant_id, 'provider_id': self._provider_id_for(provider, tenant_id),
                                'work_order_id': work_order_id, 'amount': amount,
                                'currency': currency or self.policy.doc(tenant_id)['currency'],
                                'issued_at': self.clock.text()})
        validate('invoice_record', record)
        self.store.put(tenant_id, 'invoice', record['invoice_id'], record)
        return record

    def _provider_id_for(self, provider: Identity, tenant_id: str) -> str:
        for pid, info in self.policy.doc(tenant_id)['approved_providers'].items():
            if info['organization'] == provider.principal.organization:
                return pid
        return 'unapproved-' + provider.principal.organization

    def settle(self, authorizer: Identity, tenant_id: str, problem_id: str, *, invoice_id: str | None) -> dict:
        authority = self._authority_for(tenant_id, problem_id)
        work_order_id = authority['reference']['provider_operation_reference']
        approval = next(a for a in self.store.all(tenant_id, 'approval')
                        if a['approval_digest'] == authority['envelope']['approval_digest'])
        verdicts = [v for v in self.store.all(tenant_id, 'verdict') if v['work_order_id'] == work_order_id]
        latest = verdicts[-1] if verdicts else None
        acceptances = [a for a in self.store.all(tenant_id, 'acceptance')
                       if latest and a['outcome_id'] == latest['outcome_id']]
        invoice = self.store.get(tenant_id, 'invoice', invoice_id) if invoice_id else None
        provider_org = self.policy.provider_organization(tenant_id, approval['approved_provider'])
        decision = settlement_simulator.decide(
            authorizer, registry=self.registry, store=self.store, tenant_id=tenant_id, work_order_id=work_order_id,
            verdicts=verdicts, acceptance=acceptances[-1] if acceptances else None, invoice=invoice,
            approval=approval, authority=authority, provider_organization=provider_org,
            contractors=self._contractors(provider_org), now=self.clock.now())
        self.store.put(tenant_id, 'settlement', decision['settlement_id'], decision)
        self.store.audit(tenant_id, 'settlement_decided', decision['settlement_id'],
                         {'status': decision['authorization_status'], 'reasons': decision['denial_reasons']})
        state = self.store.state(tenant_id, problem_id)
        if (decision['authorization_status'] == 'SIMULATED_AUTHORIZED' and state == 'ACCEPTED') or state == 'REJECTED':
            self._move(authorizer, tenant_id, problem_id, 'close')
        return decision

    # ------------------------------------------------------------------ layer F: learning
    def learning_record(self, tenant_id: str, problem_id: str, *, area_type: str, debris_volume_class: str,
                        shareable: bool) -> dict:
        require(self.store.state(tenant_id, problem_id) == 'CLOSED', 'case_not_closed')
        authority = self._authority_for(tenant_id, problem_id)
        work_order_id = authority['reference']['provider_operation_reference']
        verdict = [v for v in self.store.all(tenant_id, 'verdict') if v['work_order_id'] == work_order_id][-1]
        settled = [s for s in self.store.all(tenant_id, 'settlement') if s['work_order_id'] == work_order_id
                   and s['authorization_status'] == 'SIMULATED_AUTHORIZED']
        cost = settled[0]['approved_amount'] if settled else None
        band = 'not_accepted' if cost is None else ('under_250' if cost < 25000 else
                                                    '250_to_500' if cost <= 50000 else 'over_500')
        problem = self.store.get(tenant_id, 'problem', problem_id)
        hours = int((self.clock.now() - outcome_verifier.utc(problem['reported_at'])).total_seconds() // 3600)
        record = {'kind': 'wrn.learning-record.v1', 'intervention_category': 'non_hazardous_debris_removal',
                  'context_features': {'area_type': area_type, 'debris_volume_class': debris_volume_class},
                  'observed_duration_hours': hours, 'accepted_cost_band': band,
                  'outcome_verdict': verdict['assessment_state'], 'rework_indicator': False,
                  'follow_up_window_days': 0,
                  'data_rights': {'shareable': shareable, 'scope': 'aggregate_only' if shareable else 'tenant_only'},
                  'aggregation_version': 'wrn.learning.v1',
                  'source_evidence_refs': sorted([verdict['record_hash']] + [s['record_hash'] for s in settled]),
                  'causal_claim': 'none'}
        validate('learning_record', record)
        self.store.put(tenant_id, 'learning', 'lrn-' + problem_id, record)
        return record


__all__ = ['FacilityPilot', 'PilotError']
