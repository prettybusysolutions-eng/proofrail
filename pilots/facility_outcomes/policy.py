"""Tenant policy and the approval checks shared by the authority issuer and the gateway.

The policy document is data; its digest is the ProofRail policy root. Changing
any policy value changes the root, which invalidates every outstanding envelope
for that tenant.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from records import PilotError, Registry, digest, require, utc, validate, without


class Policy:
    def __init__(self):
        self._docs: dict[str, dict[str, Any]] = {}

    def set(self, tenant_id: str, doc: dict[str, Any]) -> None:
        self._docs[tenant_id] = {'tenant_id': tenant_id, **doc}

    def doc(self, tenant_id: str) -> dict[str, Any]:
        require(tenant_id in self._docs, 'no_policy_for_tenant')
        return self._docs[tenant_id]

    def root(self, tenant_id: str) -> str:
        return digest(self.doc(tenant_id))

    def provider_organization(self, tenant_id: str, provider_id: str) -> str:
        providers = self.doc(tenant_id)['approved_providers']
        require(provider_id in providers, 'provider_not_approved')
        return providers[provider_id]['organization']

    def check_plan(self, problem: dict, plan: dict) -> None:
        validate('problem_record', problem)
        validate('intervention_plan', plan)
        doc = self.doc(problem['tenant_id'])
        require(plan['plan_digest'] == plan_digest(plan), 'plan_digest_mismatch')
        require(plan['problem_id'] == problem['problem_id'], 'plan_problem_mismatch')
        require(plan['target'] == {'tenant_id': problem['tenant_id'], 'facility_id': problem['facility_id'],
                                   'area_id': problem['asset_or_area_id']}, 'plan_target_mismatch')
        require(problem['status'] == 'CONFIRMED', 'problem_not_confirmed')
        require(problem['problem_type'] in doc['allowed_problem_types'], 'problem_type_not_permitted')
        require(problem['risk_class'] in doc['allowed_risk_classes'], 'risk_class_not_permitted')
        require(plan['policy_root'] == self.root(problem['tenant_id']), 'policy_changed')
        require(plan['currency'] == doc['currency'], 'currency_mismatch')
        require(plan['estimated_cost'] <= doc['max_work_order_cost'], 'cost_exceeds_policy')
        self.provider_organization(problem['tenant_id'], plan['provider_id'])
        window = plan['expected_completion_window']
        require(utc(window['start']) < utc(window['end']), 'invalid_completion_window')

    def check_approval(self, registry: Registry, problem: dict, plan: dict, approval: dict, *, now: datetime) -> None:
        self.check_plan(problem, plan)
        confirmer = registry.signer(problem, role='problem_reviewer', tenant_id=problem['tenant_id'])
        require(problem['evidence_root'] == evidence_root(problem['evidence_refs']), 'evidence_root_inconsistent')
        require(confirmer.principal_id != problem['reported_by'], 'problem_confirmed_by_its_reporter')
        validate('approval_record', approval)
        doc = self.doc(problem['tenant_id'])
        signer = registry.signer(approval, role='approver', tenant_id=problem['tenant_id'])
        require(signer.principal_id == approval['approver_principal'], 'approver_identity_mismatch')
        require(approval['approval_digest'] == approval_digest(approval), 'approval_digest_mismatch')
        require(approval['tenant_id'] == problem['tenant_id'], 'approval_tenant_mismatch')
        require(approval['approved_plan_digest'] == plan['plan_digest'], 'approval_scope_changed')
        require(approval['approved_provider'] == plan['provider_id'], 'provider_changed')
        require(approval['currency'] == plan['currency'], 'currency_mismatch')
        require(plan['estimated_cost'] <= approval['approved_maximum_cost'], 'cost_exceeds_approval')
        require(approval['approved_maximum_cost'] <= doc['max_work_order_cost'], 'cost_exceeds_policy')
        issued, expires = utc(approval['issued_at']), utc(approval['expires_at'])
        require(issued <= now, 'approval_not_yet_valid')
        require(now < expires, 'approval_expired')
        require(expires - issued <= timedelta(hours=doc['max_approval_validity_hours']), 'approval_validity_too_long')


def plan_digest(plan: dict) -> str:
    return digest(without(plan, 'plan_digest'))


def approval_digest(approval: dict) -> str:
    return digest(without(approval, 'approval_digest', 'record_hash', 'signature'))


def evidence_root(evidence_refs: list) -> str:
    return digest({'evidence_refs': sorted(evidence_refs, key=lambda e: (e['ref'], e['sha256']))})


__all__ = ['Policy', 'plan_digest', 'approval_digest', 'evidence_root', 'PilotError']
