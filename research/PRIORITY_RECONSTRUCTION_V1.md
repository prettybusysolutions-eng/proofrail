# ProofRail Priority Reconstruction V1

Status: RESEARCH BASELINE — NOT A LEGAL OPINION — NO WORLD-FIRST CLAIM

Date of reconstruction: 2026-09-11

## Purpose

This document reconstructs what can and cannot presently be claimed about the technical priority of ProofRail. It deliberately separates:

1. the name/brand;
2. individual technical primitives;
3. the composition actually documented by Marcus / Pretty Busy Solutions in June 2026; and
4. later ESRM semantics that MUST NOT be backdated into the June evidence.

The governing rule is: evidence determines the claim. Later architecture improvements do not create earlier priority.

## Current conclusion

The broad statement **“ProofRail was the first system to use pre-execution permits, exact-action binding, single-use authority, or post-execution evidence” is rejected by the evidence reviewed so far.**

Multiple earlier systems, papers, drafts, public repositories, and patent filings contain substantial subsets of those mechanisms.

The narrower question remains unresolved:

> Was the June 2026 ProofRail composition an independently developed and potentially early combination of exact single-use authority, atomic authority consumption before side effect, provider/external observation before accepted success, replay denial, and non-retryable handling of ambiguous outcomes?

This document does **not** answer that question yes. It records it as a falsifiable hypothesis for further prior-art search.

## Marcus / Pretty Busy Solutions priority evidence

### June 9, 2026 (America/New_York local date)

A sent outreach message described ProofRail as already built to:

- block unsupported actions before mutation;
- bind governance to the exact state/action being executed; and
- produce verified provider receipts for independent audit afterward.

The message was transmitted at 2026-06-10 02:06:56 UTC, which is June 9 local EDT.

Evidence source: Gmail message id `19eaf4866b065bc3`, subject `Exact-state assurance for Salesforce DevOps agents`.

### June 12, 2026

A sent evaluation message described ProofRail as an evaluation-stage system that:

- creates a signed, single-use permit for one exact action;
- consumes that authority before execution;
- verifies provider state afterward; and
- preserves replayable evidence.

Evidence source: Gmail message id `19ebe0fbf2229026`, subject `Four-week evaluation for one governed schema migration`.

A separate reproduction request the same day described ProofRail as issuing single-use signed authority for exact autonomous-agent actions against a frozen implementation commit.

Evidence source: Gmail message id `19ebe0f758b8789a`, subject `Independent reproduction request: single-use authority for autonomous agents`.

### June 14, 2026 — verified public GitHub root

Public repository root commit:

`f127dea9df95850f27356e5b68f49d2bb4a55b5f`

Commit message:

`Open-source ProofRail protocol and reference implementation`

The root README publicly states:

- single-use cryptographic authority for autonomous execution;
- exact action / target / evidence / policy / approval / expected-outcome binding;
- authority consumed before side effect;
- provider state checked after execution;
- changed or ambiguous conditions fail closed;
- atomic permit consumption before side effects;
- state-drift and replay denial;
- provider observation before claimed success becomes reconciled truth;
- non-retryable handling of ambiguous outcomes; and
- demonstrations in GitHub exact-head merge and SQLite schema migration domains.

This is the cleanest verified public priority anchor currently held by Pretty Busy Solutions.

## Earlier overlapping work

### Bryan Morton McCaa — Pre-Execution Governance Control Layer

Patent application filed: **2026-03-02**.

Observed overlap:

- control layer intercepts AI execution requests before execution;
- default-deny execution posture;
- immutable governance record before authorization;
- machine-verifiable / cryptographic authorization artifacts;
- artifacts bound to specific execution requests;
- usage limits expressly include single-use authorization.

Observed distinction in the material inspected:

- the central claims focus on pre-execution governance rather than ProofRail's provider-observation / ambiguous-effect settlement loop.

This filing defeats any claim that ProofRail invented pre-execution cryptographic authorization or single-use AI execution authorization in general.

### Uchi Uchibeke — OAP / deterministic pre-action authorization

Public paper: March 2026.

Observed overlap:

- interception before tool execution;
- deterministic policy validation;
- fail-closed authorization;
- signed authorization/audit decisions.

No evidence reviewed so far establishes ProofRail-style irreversible authority consumption plus external-effect reconciliation.

### Nirmal Singh Baid — Hardened AI agent OS automation

Patent application filed: **2026-04-08** (with earlier claimed family priority).

Observed overlap:

- approval token cryptographically bound to action descriptor and pre-execution state hash;
- token described as single-use;
- immediate pre-execution state recapture and stale-state refusal;
- post-execution state capture and verification against expected transition;
- tamper-evident chained provenance.

This materially overlaps exact-state approval + single-use authorization + post-execution verification and defeats a broad first-invention claim over that combination.

No reviewed evidence yet establishes the later ProofRail/ESRM ambiguity-preservation and recovery semantics in this filing.

### Pinar Emirdag — SCITT AI Agent Execution Profile

Internet-Draft published April 2026.

Observed overlap:

- signed records for material autonomous-agent actions;
- independent Evidence Custodian / Transparency Service;
- tamper-evident append-only evidence;
- relying-party verification after the fact.

This is prior art for independently custodied post-execution agent evidence, not ProofRail-specific authority consumption.

### Rong Xiang — PEA separation-of-powers architecture

Public paper: April 2026.

Observed overlap:

- deterministic authorization layer;
- cryptographically signed capability tokens;
- single-use invalidation on redemption;
- state/version binding to resist replay after state changes.

The inspected paper did not establish a ProofRail-style post-crossing reconciliation/recovery protocol.

### Keel Permit — strongest public overlap found so far

Public repository initial Permit Spec v1.0.0 commit:

`824e414bd242115fee886d7c98aee4d1fa8c9d1f`

Date: **2026-05-10**.

The initial public specification already contained:

- a pre-execution Permit decision record;
- exact canonical provider/tool request binding before dispatch;
- an idempotency key;
- signed Closure Records linking Permits to execution outcomes;
- provider-response and client-response digests;
- closure statuses including `timeout`, `dispatch_error`, `provider_error`, and `missing_closure`;
- verification of Permit/dispatch/closure relationships; and
- explicit forbidden overclaims about what receipt boundaries prove.

A Permit Chains commit on **2026-05-15** added bounded delegated authority and execution receipts. Its v1 text explicitly says the Permit is a recorded artifact rather than a portable bearer grant, and the inspected version does not define ProofRail-style irreversible one-time consumption of the Permit before external effect.

Keel therefore defeats any broad claim that ProofRail was the first pre-execution authorization + post-execution closure/evidence architecture.

At the same time, the historical Keel material inspected so far does not show the same June ProofRail rule that exact single-use authority is atomically consumed before the side effect and remains non-retryable when the provider outcome is ambiguous.

That narrower distinction remains a search target, not a proven novelty claim.

## Historical feature matrix

| Mechanism | Known earlier than ProofRail public root? | Current priority assessment |
| --- | --- | --- |
| Pre-action interception / policy gate | Yes | Not novel to ProofRail |
| Cryptographic authorization artifact | Yes | Not novel to ProofRail |
| Exact action/request binding | Yes | Not novel to ProofRail |
| Single-use authorization/capability | Yes | Not novel to ProofRail |
| State-bound authorization / stale-state refusal | Yes | Not novel to ProofRail |
| Tamper-evident execution evidence | Yes | Not novel to ProofRail |
| Post-execution state/effect verification | Yes | Not novel to ProofRail |
| Permit + post-dispatch closure record | Yes (Keel May 10) | Not novel to ProofRail |
| Provider-response evidence | Yes (Keel May 10) | Not novel to ProofRail |
| Authority consumed atomically before side effect | Not yet matched in reviewed pre-June sources | UNRESOLVED |
| Consumed authority never restored after ambiguous effect | Not yet matched in reviewed pre-June sources | UNRESOLVED |
| Executor success insufficient; external/provider observation gates accepted truth | Partial predecessors exist | UNRESOLVED as exact composition |
| Ambiguous provider outcome is non-retryable under the same authority | Not yet matched in reviewed pre-June sources | UNRESOLVED |
| Integrated exact-authority → consume → effect → provider observation → reconciled truth loop | Strong partial predecessor in Keel; exact equivalence not established | UNRESOLVED |

## No backdating rule

The following later ESRM features MUST NOT be attributed to June 2026 unless contemporaneous evidence is found:

- the exact four-way `MATCH / DIVERGED / INSUFFICIENT / UNRESOLVED` algebra;
- the explicit `CROSSING_POSSIBLE` durability boundary;
- the full target-capability class registry;
- the Repair 4 recovery function;
- the complete protocol-domain registry;
- later clearing-network architecture.

Those features may be important ProofRail developments, but later development is not evidence of earlier priority.

## Claim language currently allowed

Supported:

> ProofRail was independently developed by Pretty Busy Solutions in June 2026 and publicly released on June 14 with an integrated single-use exact-authority, pre-side-effect consumption, provider-observation, replay-denial, and ambiguity-fail-closed model.

Supported with caution:

> In the prior art reviewed so far, earlier work contains many individual components and even permit-to-closure architectures, but an exact pre-June match for ProofRail's irreversible authority-consumption + ambiguous-effect non-retry composition has not yet been established.

Not supported:

> ProofRail was the first AI authorization system.

> ProofRail invented single-use agent permits.

> ProofRail invented pre-execution governance.

> ProofRail invented post-execution verification.

> ProofRail is proven to be the first system in the world with its full architecture.

## Next falsification targets

The remaining priority hypothesis should be attacked in these source families before any stronger claim is made:

- payment and financial authorization/settlement protocols;
- distributed transaction and exactly-once / uncertain-outcome recovery literature;
- capability-security and one-shot authority systems;
- autonomous-agent patents filed before June 2026;
- cloud/IAM approval-bound execution systems;
- robotics / industrial-control command authorization and verified readback;
- database migration and infrastructure-change authorization systems;
- unpublished patent applications that become discoverable later.

## Research state

`BROAD_WORLD_FIRST_CLAIM = REJECTED`

`INDEPENDENT_DEVELOPMENT = SUPPORTED`

`JUNE_14_PUBLIC_PRIORITY_ANCHOR = VERIFIED`

`NARROW_COMPOSITION_PRIORITY = UNRESOLVED`

`PATENTABILITY_OR_LEGAL_PRIORITY_OPINION = NOT_ESTABLISHED`
