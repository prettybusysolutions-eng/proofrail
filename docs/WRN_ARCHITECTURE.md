# WRN architecture: the facility-outcome pilot

Status: the layers below are implemented as a **local, synthetic pilot** in
`pilots/facility_outcomes/`. Nothing is deployed, no real provider or payment
system is connected, and no independent review has taken place. Proposed
architecture that is *not* built is marked as such.

## Principle

ProofRail stays the execution-authority foundation. Coordination and outcome
verification are built above it and cannot reach the provider's create call
except through ProofRail.

The pilot keeps eleven claims separate. Each is a different record, written by a
different role:

| # | Claim | Record | Who signs it |
|---|---|---|---|
| 1 | A problem was reported | `ProblemRecord` rev 1 | reporter |
| 2 | Evidence supports it | evidence refs + `evidence_root`, confirmed revision | problem reviewer |
| 3 | An intervention was proposed | `InterventionPlan` (+ `plan_digest`) | planner (unsigned plan; bound by approval) |
| 4 | An exact action was approved | `ApprovalRecord` | approver |
| 5 | Execution authority admitted it | Action Authority Envelope v1, consumed in the replay registry | authority issuer, then gateway |
| 6 | The executor attempted it | `provider_call` audit entry, written before the call | gateway |
| 7 | The external system shows the result | provider `ObservationRecord` (`provider_system_record`) | provider observer |
| 8 | The real-world outcome was assessed | inspection `ObservationRecord` + `OutcomeVerdict` | inspector, outcome reviewer |
| 9 | The buyer accepted or disputed it | `AcceptanceRecord` | buyer |
| 10 | Settlement was separately authorized | `SettlementDecision` (simulated) | settlement authorizer |
| 11 | Reusable evidence was produced | `LearningRecord` (no identifiers, `causal_claim: none`) | system, after closure |

None of these records is a success flag for another. For example, scenario D
leaves the execution reference `RECONCILED` while the outcome is `REJECTED`.

## Layers as built

| Layer | Module(s) | What exists |
|---|---|---|
| A. Problem intelligence | `pilot.submit_problem`, `confirm_problem` | Signed problem intake with evidence refs bound by digest. A human reviewer must confirm a problem before it can be planned. `provenance.ai_assisted` is recorded, and AI output never confirms a problem. **No** classification, duplicate detection or recommendation engine is built. |
| B. Coordination | `pilot.propose_plan`, `amend_plan`, `approve`, `policy.py` | A plan binds the exact target, provider, quote, criteria, window and policy root. The approval binds the plan digest, provider and cost cap. Amending a plan returns the case to `PLAN_PROPOSED`. **No** provider marketplace or quote collection is built. |
| C. ProofRail execution authority | `proofrail_gateway.py` | The issuer mints a standard v1 envelope. The gateway recomputes the effect and the four roots from current records, verifies with the core verifier plus the issuer, subject and not-before checks, consumes in a ProofRail-format replay registry, calls the provider once, and reconciles only from an independent read. |
| D. Outcome verification | `outcome_verifier.py` | Rule-computed verdicts from qualified inspections only. Every observation is used or excluded with a stated reason. The states are `VERIFIED`, `REJECTED`, `INSUFFICIENT_EVIDENCE` and `DISPUTED`. |
| E. Settlement | `settlement_simulator.py` | Eligibility decision with every applicable denial reason, one settlement per work order, provider-signed invoices, and `money_moved: false` always. |
| F. Learning | `pilot.learning_record` | Banded, identifier-free records with data rights and `causal_claim: "none"`. **No** aggregation or comparison across tenants is built. |
| Evidence | `evidence_export.py`, `verify_bundle.py` | A per-case bundle verifiable offline, reported in five separate dimensions. |

## Request path (execution)

```
approval ──► AuthorityIssuer.issue ──► envelope (signed, roots bound to current records)
                                              │
                         Gateway.admit ◄──────┘
   1. replay registry has this envelope?       → permit_replayed
   2. business store has admitted it?          → authority_already_admitted
   3. recompute effect + roots from records; core verifier + extra checks
   4. consume (BEGIN IMMEDIATE; unique permit hash and nonce)
   5. write CONSUMED reference + identity/policy/state snapshots
   6. recompute roots again; compare-and-set APPROVED → WORK_ORDER_PENDING
   7. audit "provider_call", then POST once (Idempotency-Key = envelope hash)
   8. Observer reads by client reference → signed observation
   9. RECONCILED only if exactly one order matches every parameter
      and nothing in the response contradicts it
```

Reconciliation after an unknown outcome repeats step 8 only. It never repeats
step 7, and a counter enforces that.

## Storage

- **Replay registry** (`retained/replay-registry.sqlite3`): ProofRail's
  `permit_claims` / `permit_events` schema and transaction, kept separate from
  business data.
- **Business store** (`business.sqlite3`): tenant-scoped records, compare-and-set
  work state, per-tenant hash-chained audit, and a unique settlement reservation.
- **Provider simulator** (`provider.sqlite3`): owned by the simulator process.

SQLite is used because no Docker daemon is available in this environment (see the
baseline). It is a pilot component, not multi-node storage.

## Not built (proposed only)

- HTTP API or UI for non-technical users;
- PostgreSQL / Compose;
- MCP adapter (Phase 5);
- A2A delegation (Phase 6);
- OpenTelemetry;
- evidence blob storage;
- real identity provider;
- key custody and rotation;
- a real provider integration.
