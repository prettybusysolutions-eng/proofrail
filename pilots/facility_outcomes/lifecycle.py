"""Work/intervention lifecycle. Separate from ProofRail's authority state.

TRANSITIONS is the single source of truth: docs/WRN_STATE_MACHINES.md is checked
against it by a test. Every transition names its authorized actor role, the
states it may leave, the evidence it requires, the side effect it may cause and
the failure outcome. Authority state (PERMITTED, CONSUMED, EXECUTION_UNKNOWN,
RECONCILED, RECONCILIATION_FAILED) lives on the ExecutionAuthorityReference and is
never inferred from, or written into, the work state.
"""
from __future__ import annotations

from dataclasses import dataclass

from records import PilotError

STATES = ('REPORTED', 'UNDER_REVIEW', 'PLAN_PROPOSED', 'APPROVED', 'WORK_ORDER_PENDING',
          'WORK_ORDER_CREATED', 'WORK_IN_PROGRESS', 'COMPLETION_CLAIMED', 'OUTCOME_REVIEW',
          'ACCEPTED', 'REJECTED', 'DISPUTED', 'CLOSED', 'CANCELLED')

AUTHORITY_STATES = ('PERMITTED', 'CONSUMED', 'EXECUTION_UNKNOWN', 'RECONCILED', 'RECONCILIATION_FAILED')


@dataclass(frozen=True)
class Transition:
    event: str
    sources: tuple
    target: str
    actor_role: str
    evidence: str
    side_effect: str
    failure: str


TRANSITIONS = (
    Transition('submit_problem', ('NONE',), 'REPORTED', 'reporter',
               'signed ProblemRecord with evidence refs and evidence root', 'none', 'invalid_problem_record'),
    Transition('begin_review', ('REPORTED',), 'UNDER_REVIEW', 'problem_reviewer',
               'none', 'none', 'transition_not_allowed'),
    Transition('propose_plan', ('UNDER_REVIEW',), 'PLAN_PROPOSED', 'planner',
               'InterventionPlan bound to the confirmed problem and the current policy root', 'none',
               'invalid_intervention_plan / policy refusal'),
    Transition('amend_plan', ('PLAN_PROPOSED', 'APPROVED'), 'PLAN_PROPOSED', 'planner',
               'amended InterventionPlan (new digest); any prior approval no longer matches it', 'none',
               'transition_not_allowed (after admission the scope is fixed)'),
    Transition('approve_plan', ('PLAN_PROPOSED',), 'APPROVED', 'approver',
               'signed ApprovalRecord naming the exact plan digest, provider and cost cap', 'none',
               'approval refusal'),
    Transition('admit_work_order', ('APPROVED',), 'WORK_ORDER_PENDING', 'gateway',
               'ProofRail envelope verified against current roots and consumed in the replay registry',
               'one provider create-work-order request, never retried', 'authority refusal (no provider call)'),
    Transition('confirm_work_order', ('WORK_ORDER_PENDING',), 'WORK_ORDER_CREATED', 'provider_observer',
               'independent provider read matching the exact authorized effect', 'none (reads only)',
               'stays WORK_ORDER_PENDING; authority EXECUTION_UNKNOWN or RECONCILIATION_FAILED'),
    Transition('start_work', ('WORK_ORDER_CREATED',), 'WORK_IN_PROGRESS', 'provider_observer',
               'provider read showing the work order in progress', 'none (reads only)', 'transition_not_allowed'),
    Transition('claim_completion', ('WORK_ORDER_CREATED', 'WORK_IN_PROGRESS'), 'COMPLETION_CLAIMED', 'contractor',
               'signed completion claim (performer_claim; never sufficient for an outcome)', 'none',
               'transition_not_allowed (e.g. after cancellation)'),
    Transition('submit_inspection', ('COMPLETION_CLAIMED', 'OUTCOME_REVIEW'), 'OUTCOME_REVIEW', 'inspector',
               'signed inspection by a buyer-designated, independent inspector', 'none', 'observation refusal'),
    Transition('accept_outcome', ('OUTCOME_REVIEW',), 'ACCEPTED', 'buyer',
               'VERIFIED OutcomeVerdict and a signed buyer AcceptanceRecord bound to its digest', 'none',
               'acceptance refusal'),
    Transition('reject_outcome', ('OUTCOME_REVIEW',), 'REJECTED', 'outcome_reviewer',
               'REJECTED OutcomeVerdict', 'none', 'transition_not_allowed'),
    Transition('flag_dispute', ('OUTCOME_REVIEW',), 'DISPUTED', 'outcome_reviewer',
               'DISPUTED OutcomeVerdict (qualified observations conflict, or reviewers disagree)', 'none',
               'transition_not_allowed'),
    Transition('dispute_outcome', ('OUTCOME_REVIEW', 'ACCEPTED'), 'DISPUTED', 'buyer',
               'signed buyer AcceptanceRecord with decision DISPUTED', 'none', 'transition_not_allowed'),
    Transition('close', ('ACCEPTED', 'REJECTED'), 'CLOSED', 'settlement_authorizer',
               'SettlementDecision (SIMULATED_AUTHORIZED or DENIED)', 'simulated settlement record; no money moves',
               'settlement refusal'),
    Transition('cancel', ('REPORTED', 'UNDER_REVIEW', 'PLAN_PROPOSED', 'APPROVED'), 'CANCELLED', 'tenant_admin',
               'none', 'none (a created work order needs a separate, manual cancellation)', 'transition_not_allowed'),
)

BY_EVENT = {t.event: t for t in TRANSITIONS}


def transition(current: str, event: str, actor_roles) -> str:
    """Return the next state, or refuse. Never changes state silently."""
    rule = BY_EVENT.get(event)
    if rule is None:
        raise PilotError('unknown_transition', event)
    if current not in rule.sources:
        raise PilotError('transition_not_allowed', f'{event} from {current}')
    if rule.actor_role not in actor_roles:
        raise PilotError('actor_not_permitted', f'{event} requires {rule.actor_role}')
    return rule.target


def markdown_table() -> str:
    rows = ['| Event | From | To | Actor | Required evidence | Side effect | On failure |',
            '|---|---|---|---|---|---|---|']
    for t in TRANSITIONS:
        rows.append(f"| `{t.event}` | {', '.join(t.sources)} | {t.target} | {t.actor_role} | "
                    f'{t.evidence} | {t.side_effect} | {t.failure} |')
    return '\n'.join(rows) + '\n'
