# WRN state machines: facility-outcome pilot

Two separate state machines. Neither is written into or inferred from the other.

## 1. Work / intervention lifecycle

Source of truth: `pilots/facility_outcomes/lifecycle.py` (`TRANSITIONS`). The
table below is generated from it, and `tests/test_contracts.py` fails if the two
diverge.

- Every transition is applied with compare-and-set (`Store.move`), so two
  concurrent transitions cannot both succeed.
- Every transition writes an immutable audit entry to the tenant's hash chain.

States: `REPORTED`, `UNDER_REVIEW`, `PLAN_PROPOSED`, `APPROVED`, `WORK_ORDER_PENDING`, `WORK_ORDER_CREATED`, `WORK_IN_PROGRESS`, `COMPLETION_CLAIMED`, `OUTCOME_REVIEW`, `ACCEPTED`, `REJECTED`, `DISPUTED`, `CLOSED`, `CANCELLED`.

<!-- BEGIN GENERATED TRANSITIONS -->
| Event | From | To | Actor | Required evidence | Side effect | On failure |
|---|---|---|---|---|---|---|
| `submit_problem` | NONE | REPORTED | reporter | signed ProblemRecord with evidence refs and evidence root | none | invalid_problem_record |
| `begin_review` | REPORTED | UNDER_REVIEW | problem_reviewer | none | none | transition_not_allowed |
| `propose_plan` | UNDER_REVIEW | PLAN_PROPOSED | planner | InterventionPlan bound to the confirmed problem and the current policy root | none | invalid_intervention_plan / policy refusal |
| `amend_plan` | PLAN_PROPOSED, APPROVED | PLAN_PROPOSED | planner | amended InterventionPlan (new digest); any prior approval no longer matches it | none | transition_not_allowed (after admission the scope is fixed) |
| `approve_plan` | PLAN_PROPOSED | APPROVED | approver | signed ApprovalRecord naming the exact plan digest, provider and cost cap | none | approval refusal |
| `admit_work_order` | APPROVED | WORK_ORDER_PENDING | gateway | ProofRail envelope verified against current roots and consumed in the replay registry | one provider create-work-order request, never retried | authority refusal (no provider call) |
| `confirm_work_order` | WORK_ORDER_PENDING | WORK_ORDER_CREATED | provider_observer | independent provider read matching the exact authorized effect | none (reads only) | stays WORK_ORDER_PENDING; authority EXECUTION_UNKNOWN or RECONCILIATION_FAILED |
| `start_work` | WORK_ORDER_CREATED | WORK_IN_PROGRESS | provider_observer | provider read showing the work order in progress | none (reads only) | transition_not_allowed |
| `claim_completion` | WORK_ORDER_CREATED, WORK_IN_PROGRESS | COMPLETION_CLAIMED | contractor | signed completion claim (performer_claim; never sufficient for an outcome) | none | transition_not_allowed (e.g. after cancellation) |
| `submit_inspection` | COMPLETION_CLAIMED, OUTCOME_REVIEW | OUTCOME_REVIEW | inspector | signed inspection by a buyer-designated, independent inspector | none | observation refusal |
| `accept_outcome` | OUTCOME_REVIEW | ACCEPTED | buyer | VERIFIED OutcomeVerdict and a signed buyer AcceptanceRecord bound to its digest | none | acceptance refusal |
| `reject_outcome` | OUTCOME_REVIEW | REJECTED | outcome_reviewer | REJECTED OutcomeVerdict | none | transition_not_allowed |
| `flag_dispute` | OUTCOME_REVIEW | DISPUTED | outcome_reviewer | DISPUTED OutcomeVerdict (qualified observations conflict, or reviewers disagree) | none | transition_not_allowed |
| `dispute_outcome` | OUTCOME_REVIEW, ACCEPTED | DISPUTED | buyer | signed buyer AcceptanceRecord with decision DISPUTED | none | transition_not_allowed |
| `close` | ACCEPTED, REJECTED | CLOSED | settlement_authorizer | SettlementDecision (SIMULATED_AUTHORIZED or DENIED) | simulated settlement record; no money moves | settlement refusal |
| `cancel` | REPORTED, UNDER_REVIEW, PLAN_PROPOSED, APPROVED | CANCELLED | tenant_admin | none | none (a created work order needs a separate, manual cancellation) | transition_not_allowed |
<!-- END GENERATED TRANSITIONS -->

Compensating procedures:
- Cancelling a created work order is **not** automated. It needs a separate,
  manually authorized action.
- A case stuck in `WORK_ORDER_PENDING`, with authority `RECONCILIATION_FAILED`,
  needs operator review and **new** authority. It is never retried automatically.

## 2. ProofRail authority (per envelope), on `ExecutionAuthorityReference`

```
PERMITTED ──(consume: replay registry claim)──► CONSUMED
CONSUMED ──(provider read matches the exact effect)──► RECONCILED
CONSUMED ──(response lost / provider unreadable / nothing yet)──► EXECUTION_UNKNOWN
CONSUMED ──(success claimed but not observed; mismatch; duplicates; inconsistent response)──► RECONCILIATION_FAILED
EXECUTION_UNKNOWN ──(read-only reconcile: exact match)──► RECONCILED
EXECUTION_UNKNOWN ──(read-only reconcile: still nothing)──► EXECUTION_UNKNOWN
CONSUMED (aborted before any provider call) ──► not reconcilable; new authority required
```

- `CONSUMED` with no outcome recorded (a crash while the call was in flight) is
  resolved like `EXECUTION_UNKNOWN`, by reads only.
- A reconciliation that would issue a provider write is refused
  (`reconciliation_issued_provider_write`).
- The core ProofRail permit states, execution status and reconciliation status
  for the GitHub and migration adapters are unchanged by this pilot.

## Races exercised

| Race | Result | Test |
|---|---|---|
| Two worker processes consume one envelope | exactly one provider order; the other process is refused | `test_concurrent_admission_from_two_processes` |
| Two envelopes for one case | the second is refused by the state root | `test_two_approved_envelopes_for_one_case` |
| Approval revoked during admission | authority spent, no provider call, not reconcilable | `test_revoked_during_admission_stops_the_provider_call` |
| Completion claim after cancellation | refused | `test_completion_claim_after_cancellation_is_refused` |
| Scope changed after approval | the original envelope is refused | `test_B_changed_scope_rejects_the_original_authority` |
| Reviewers differ | definite disagreement is a dispute; insufficient → verified is progression | `test_insufficient_then_verified_is_progression_not_dispute`, `test_reviewers_cannot_reach_different_verdicts_on_the_same_evidence` |
| Settlement requested twice | the second is denied as a duplicate | `test_duplicate_settlement_request`, `test_replayed_settlement_authorization_after_close` |
| Evidence changed after its root was approved | refused (`evidence_root_changed`) | `test_evidence_changed_after_its_root_was_approved` |
| Provider confirms after a timeout | resolved by read-only reconcile | `test_E3_provider_dies_after_accepting_then_confirms_after_restart` |
| Tenant identity changes between authorization and dispatch | refused (`identity_root_changed`) | `test_identity_changed_between_authorization_and_dispatch` |
