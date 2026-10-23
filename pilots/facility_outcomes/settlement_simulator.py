"""Simulated settlement. Decides eligibility and records it; never moves money.

A verified outcome is not payment authorization. A decision is SIMULATED_AUTHORIZED
only if every condition holds. Otherwise it is DENIED with every reason that
applied, in a fixed order, so a decision can be audited without rerunning it.
"""
from __future__ import annotations

import uuid

from records import Identity, PilotError, Registry, digest, require, validate

POLICY = {'name': 'wrn.settlement.v1',
          'rules': ['verified_outcome', 'latest_and_only_verdict_state_verified', 'buyer_acceptance_bound_to_verdict',
                    'provider_signed_invoice_for_this_work_order', 'currency_matches', 'amount_within_approved_cap',
                    'authorizer_independent_of_performer_and_reviewer', 'one_settlement_per_work_order']}
POLICY_DIGEST = digest(POLICY)


def decide(authorizer: Identity, *, registry: Registry, store, tenant_id: str, work_order_id: str,
           verdicts: list, acceptance: dict | None, invoice: dict | None, approval: dict, authority: dict,
           provider_organization: str, contractors: set, now) -> dict:
    a = authorizer.principal
    require('settlement_authorizer' in a.roles and a.tenant_id == tenant_id, 'authorizer_not_permitted')
    reasons = []
    ref = authority['reference']
    if ref['authority_state'] != 'RECONCILED' or ref['provider_operation_reference'] != work_order_id:
        reasons.append('work_order_not_reconciled_for_this_authority')
    mine = [v for v in verdicts if v['work_order_id'] == work_order_id]
    valid = []
    for v in mine:
        try:
            registry.signer(v, role='outcome_reviewer', tenant_id=tenant_id)
            valid.append(v)
        except PilotError:
            reasons.append('verdict_signature_invalid')
    latest = valid[-1] if valid else None
    if latest is None or latest['assessment_state'] != 'VERIFIED':
        reasons.append('outcome_not_verified')
    if any(v['assessment_state'] != 'VERIFIED' for v in valid):
        reasons.append('outcome_previously_rejected_or_disputed')
    if latest is not None and (latest['reviewer_principal'] == a.principal_id or a.principal_id in contractors
                               or a.organization == provider_organization):
        reasons.append('authorizer_not_independent')
    if acceptance is None:
        reasons.append('buyer_acceptance_missing')
    else:
        try:
            buyer = registry.signer(acceptance, role='buyer', tenant_id=tenant_id)
            if buyer.principal_id != acceptance['buyer_principal']:
                reasons.append('buyer_identity_mismatch')
        except PilotError:
            reasons.append('buyer_acceptance_signature_invalid')
        if latest is None or acceptance['outcome_id'] != latest['outcome_id'] or \
                acceptance['outcome_digest'] != latest['record_hash']:
            reasons.append('acceptance_not_bound_to_latest_verdict')
        if acceptance['decision'] != 'ACCEPTED':
            reasons.append('buyer_disputed')
    amount = 0
    if invoice is None:
        reasons.append('invoice_missing')
    else:
        try:
            signer = registry.signer(invoice, role='provider', tenant_id=tenant_id)
            if signer.organization != provider_organization or invoice['provider_id'] != approval['approved_provider']:
                reasons.append('invoice_not_from_approved_provider')
        except PilotError:
            reasons.append('invoice_signature_invalid')
        if invoice['work_order_id'] != work_order_id:
            reasons.append('invoice_for_other_work_order')
        if invoice['currency'] != approval['currency']:
            reasons.append('currency_mismatch')
        if invoice['amount'] > approval['approved_maximum_cost']:
            reasons.append('amount_exceeds_approved_cap')
        amount = invoice['amount']
    settlement_id = 'set-' + uuid.uuid4().hex[:16]
    duplicate = 'UNIQUE'
    if not reasons and not store.reserve_settlement(tenant_id, work_order_id, settlement_id):
        duplicate = 'DUPLICATE'
        reasons.append('duplicate_settlement')
    authorized = not reasons
    decision = {'kind': 'wrn.settlement-decision.v1', 'settlement_id': settlement_id, 'tenant_id': tenant_id,
                'work_order_id': work_order_id, 'outcome_id': latest['outcome_id'] if latest else 'none',
                'invoice_id': invoice['invoice_id'] if invoice else None,
                'approved_amount': amount if authorized else 0,
                'currency': approval['currency'], 'authorization_status': 'SIMULATED_AUTHORIZED' if authorized else 'DENIED',
                'denial_reasons': sorted(set(reasons), key=reasons.index), 'duplicate_check_result': duplicate,
                'dispute_status': 'DISPUTED' if acceptance and acceptance['decision'] == 'DISPUTED' else 'NONE',
                'simulation_reference': ('sim-' + settlement_id) if authorized else None,
                'settlement_policy_digest': POLICY_DIGEST, 'authorizer_principal': a.principal_id,
                'decided_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'money_moved': False}
    signed = authorizer.sign(decision)
    validate('settlement_decision', signed)
    return signed
