# Settlement Kernel Invariants

Status: NON-NORMATIVE ARCHITECTURE BASELINE

This document extracts architectural invariants from the current ESRM Repair 4 source. The Repair 4 source remains authoritative. If this document conflicts with it, Repair 4 wins.

## 1. Fundamental Separation

For a transition `tau`, the system MUST architecturally preserve:

```text
SignatureValid(tau)
  != Authorized(tau)
  != DispatchClaim(tau)
  != EmpiricalEffect(tau)
  != Reconciliation(tau)
  != Settlement(tau)
```

No implementation shortcut, adapter abstraction, UI state, API response, model output, trace, or administrator convenience may collapse those roles.

## 2. Epistemic Domains

All security-relevant artifacts belong to one role and may not impersonate another.

### SPECULATIVE

Represents proposed or derived claims before empirical confirmation.

Examples:
- agent plans;
- CRL/TMM proposed graph mutations;
- policy evaluations;
- expected post-state;
- executor intent;
- retry proposals.

SPECULATIVE material may justify evaluation. It cannot establish external truth.

### ATTESTED / AUTHORITY

Represents cryptographically attributable claims and valid authority derivation.

Examples:
- signed identity assertions;
- key-status statements;
- authority lineage;
- admissions;
- consumption records.

A signature proves attribution under a key. Authority additionally requires valid lineage, scope, state, time, and policy predicates.

### EMPIRICAL

Represents independently obtained evidence about an external target or world state.

Examples:
- provider GET response from a separately authenticated observation path;
- database state root independently computed after execution;
- payment-network status returned by an authoritative source;
- cloud-resource state observed through an independent read identity.

The executor's own success message is not empirical evidence merely because it describes an outcome.

### ADJUDICATED

Represents a deterministic conclusion over admissible empirical evidence and committed settlement predicates.

Valid reconciliation algebra:

```text
MATCH
DIVERGED
INSUFFICIENT
UNRESOLVED
```

A reconciliation result is not itself an observation.

### SETTLED

Represents final protocol acceptance of the transition outcome under the committed settlement policy and reconciliation epoch.

Settlement requires independently distinguishable committed artifacts for the relevant state, derivation, authority, admission, consumption, dispatch, observation, reconciliation, and settlement roles.

## 3. Authority Invariants

### K-AUTH-001 — Exact Scope

Authority must bind the complete protected semantic effect. Target, operation, parameters, preconditions, expected effect, and relevant policy/evidence/state commitments cannot be inferred later from mutable external context.

### K-AUTH-002 — Authority Derivation

A valid signature is necessary only where the protocol requires it. It is never sufficient to establish authority.

### K-AUTH-003 — Single Use

Consumption is monotonic and irreversible.

```text
Consumed(a) = TRUE
```

can never become false.

### K-AUTH-004 — No Resurrection

Provider rejection, transport failure, crash, timeout, proof of non-occurrence, reconciliation failure, or administrator intent cannot restore a consumed authority object.

A legitimate later action requires either a protocol-permitted retransmission under verified durable idempotency or a new transition with newly derived authority.

### K-AUTH-005 — Delegation Cannot Expand Scope

Any downstream authority derived from upstream authority must be equal to or narrower than the upstream scope. Delegation cannot create new targets, effects, time windows, evidence assumptions, or retry rights.

## 4. Effect-Boundary Invariants

### K-EFFECT-001 — Consume Before Crossing

The system must durably commit authority consumption before releasing the first externally visible instruction or byte capable of creating the protected effect.

### K-EFFECT-002 — Crossing Is Not Effect

A durable crossing record proves only that the system became capable of crossing the protected effect boundary. It does not prove transmission, acknowledgement, execution, or semantic effect.

### K-EFFECT-003 — No Universal Exactly Once

The kernel must never claim universal exactly-once external execution.

At-most-once semantic behavior may be claimed only for a transition/target combination with committed and verified capability evidence that supports it.

### K-EFFECT-004 — Effect Identity

Every consequential transition needs a stable effect identity sufficient to reason about retries, deduplication, provider observations, and later reconciliation.

### K-EFFECT-005 — Adapter Capability Is Evidence-Gated

An adapter cannot self-promote into a stronger recovery class. Capabilities such as durable idempotency, conditional mutation, authoritative query, or atomic participation require committed capability evidence applicable to the exact target/version/scope.

## 5. Observation and Reconciliation Invariants

### K-OBS-001 — Independent Observation Path

Production deployments must separate executor authority from the observation path sufficiently that an executor cannot unilaterally make its own success claim become settled truth.

Separation may be cryptographic, identity-based, infrastructure-based, organizational, or quorum-based depending on risk class.

### K-OBS-002 — Absence Requires Closed World

Missing evidence is not evidence of non-occurrence.

Negative conclusions require committed evidence that the observer source has authoritative closed-world coverage for the relevant domain and interval.

### K-OBS-003 — Four-Way Algebra

`MATCH`, `DIVERGED`, `INSUFFICIENT`, and `UNRESOLVED` remain distinct.

- MATCH: admissible evidence establishes the settlement predicate.
- DIVERGED: admissible evidence establishes its negation or committed divergence condition.
- INSUFFICIENT: current evidence cannot establish either while the reconciliation window remains open.
- UNRESOLVED: the committed window closed without sufficient evidence for MATCH or DIVERGED.

### K-OBS-004 — Timeout Is Not Failure

A timeout cannot be mapped automatically to DIVERGED, failure, or reusable authority.

### K-OBS-005 — Later Evidence Is Append-Only

Later observations create new artifacts and, where appropriate, new reconciliation epochs. They do not mutate historical observations or adjudications.

## 6. Recovery Invariants

### K-REC-001 — Ambiguity Dominates Availability

When external effect status is unknown, safety wins over automatic completion.

```text
UnknownEffect(tau)
  -> NOT Settled(tau)
  -> NOT FailedByInference(tau)
  -> Consumed(authority_tau)
```

### K-REC-002 — Retry Gate

A retry is legal only when one of the following is true:

1. committed target-capability evidence proves durable idempotency for the same effect identity and canonical payload, allowing retransmission of the same semantic transition; or
2. a new transition is created and new authority is derived.

### K-REC-003 — No Semantic Drift on Retransmission

A retransmission under durable idempotency must preserve target, effect identity, canonical operation, and semantic transition. Any security-relevant mutation turns it into a new transition.

### K-REC-004 — Recovery Is Explicit

Recovery produces dedicated artifacts. It may not be hidden inside an adapter retry loop.

## 7. Data and Cryptographic Invariants

### K-DATA-001 — Raw Bytes Before Meaning

Security artifacts enter through resource limits, strict UTF-8, duplicate-key detection, lexical validation, schema validation, semantic validation, canonicalization, commitment, signature attestation, authority validation, then protocol validation.

### K-DATA-002 — Closed Domains

Security domain separation values are protocol-registered and versioned. An artifact cannot choose the domain under which it will be verified.

### K-DATA-003 — Deterministic Canonicalization

Canonical commitments must produce the same bytes across conforming independent implementations.

### K-DATA-004 — Append-Only Corrections

Corrections, revocations, recoveries, and later observations are new linked facts. Prior security-relevant facts are not overwritten.

### K-DATA-005 — No Hidden Security Semantics

Security-relevant meaning may not enter through uncommitted metadata, logging fields, UI state, tracing baggage, model context, environment variables, or adapter-local caches.

## 8. Role-Separation Invariants

The architecture recognizes at least these logical roles:

```text
PROPOSER
EVIDENCE_COLLECTOR
POLICY_EVALUATOR
AUTHORITY_VERIFIER / ISSUER
CONSUMPTION_REGISTRY
EXECUTOR
OBSERVER
RECONCILER
SETTLER
GOVERNOR
AUDITOR
```

A deployment may colocate roles only when its risk profile permits it and the trust impact is explicit. High-consequence production profiles should separate adjacent roles, especially issuer/executor, executor/observer, observer/reconciler, and learner/governor.

## 9. External-System Invariants

### K-EXT-001 — Identity Is Input, Not Authority

OAuth, OIDC, SPIFFE/SPIRE, cloud IAM, mTLS identities, API keys, and human authentication can establish identity or access context. None automatically proves ESRM transition authority.

### K-EXT-002 — Policy Is Input, Not Settlement

Cedar, OPA, IAM policy, approval systems, or enterprise rules may supply policy evidence or admission decisions. They do not establish empirical effect or settlement.

### K-EXT-003 — Transport Is Input, Not Settlement

MCP, A2A, HTTP, queues, RPC, and message buses may transport intents and artifacts. Successful transport does not establish semantic effect.

### K-EXT-004 — Telemetry Is Diagnostic by Default

OpenTelemetry traces, logs, and metrics are useful for operations but are not authoritative empirical evidence unless an explicit observation profile upgrades a particular source with committed trust semantics.

### K-EXT-005 — Transparency Is Not Truth

Transparency-log inclusion or a valid registration receipt proves that a statement was registered under a transparency service's semantics. It does not prove the statement's authority or empirical truth.

## 10. Architectural Acceptance Test

Any proposed component, optimization, network service, or protocol extension fails architecture review if it can cause any of the following:

- a valid signature to be treated as sufficient authority;
- an executor claim to become empirical truth without the required observation contract;
- missing evidence or timeout to become inferred failure/success;
- consumed authority to become reusable;
- an adapter to self-assert stronger retry semantics;
- a transport retry to create an untracked potential new semantic effect;
- historical evidence to be rewritten rather than superseded;
- security meaning to depend on uncommitted context;
- a centralized ProofRail service to become necessary for local independent verification;
- a network operator to unilaterally rewrite settlement history.

The architecture should optimize aggressively everywhere else. These invariants are the line that does not move.