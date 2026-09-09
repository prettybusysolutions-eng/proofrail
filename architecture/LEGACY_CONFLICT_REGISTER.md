# Legacy Semantic Conflict Register

Status: NON-NORMATIVE MIGRATION REGISTER

Purpose: identify existing ProofRail documents/schemas that predate the ESRM Repair 4 source and now express semantics that are incomplete, weaker, or incompatible with the Repair 4 kernel.

No legacy artifact is modified by this register. Migration must occur in a separately reviewed implementation/conformance change.

## Authority of Sources

For ESRM semantics covered by Repair 4:

```text
Repair 4 normative source
    > architecture interpretation
    > legacy ProofRail documents/schemas
```

This ordering does not erase historical behavior. It determines which semantics future ESRM-conforming work must follow.

## Conflict C-001 — Reconciliation Algebra Collapsed

Legacy source:
- `STATE_MACHINE.md`

Legacy behavior:
- terminal state `RECONCILIATION_FAILED` represents external ambiguity or contradiction.

Repair 4 behavior:
- reconciliation result set is exactly `MATCH`, `DIVERGED`, `INSUFFICIENT`, `UNRESOLVED` with mutually exclusive meanings;
- timeout does not imply divergence;
- open-window insufficient evidence and closed-window unresolved evidence must remain distinct.

Risk:
- operational code may incorrectly map temporary missing evidence to terminal failure;
- historical metrics may collapse epistemically different conditions;
- automatic retry logic may be triggered from a generic failure state.

Migration requirement:
- do not reuse `RECONCILIATION_FAILED` as a protocol reconciliation result;
- map runtime errors separately from protocol adjudication;
- create explicit four-way reconciliation artifacts.

## Conflict C-002 — Action Authority Envelope Forces Generic Idempotency

Legacy sources:
- `docs/ACTION_AUTHORITY_ENVELOPE_V1.md`
- `schemas/action_authority_envelope.schema.json`

Legacy behavior:
- adapter contract requires `idempotency_required = true`;
- documentation says an adapter must accept an idempotency key.

Repair 4 behavior:
- target capability classes are evidence-gated;
- `DURABLE_IDEMPOTENCY` is only one possible class;
- `QUERYABLE_EFFECT`, `OBSERVABLE_ONLY`, and `OPAQUE_TARGET` are valid classes;
- an adapter cannot acquire a recovery class by self-declaration.

Risk:
- an idempotency key field could be mistaken for proof of durable provider deduplication;
- opaque targets might be incorrectly treated as safe to retry;
- application-level idempotency intent could be confused with provider-backed at-most-one semantic effect.

Migration requirement:
- replace generic `idempotency_required` with committed target-capability evidence and class;
- define effect identity separately from transport attempt identity;
- test provider durability semantics, not merely key acceptance.

## Conflict C-003 — Retry Always Requires New Authority

Legacy sources:
- `docs/ACTION_AUTHORITY_ENVELOPE_V1.md`
- `schemas/action_authority_envelope.schema.json`

Legacy behavior:

```text
retry = NEW_AUTHORITY_REQUIRED
```

Repair 4 behavior:
- a consumed authority never becomes reusable;
- however, retransmission of the same semantic effect may be permitted when verified durable idempotency exists for the same effect identity and canonical payload;
- otherwise, recovery requires a new transition and new authority.

Important distinction:

```text
retransmit same effect under proven durable idempotency
    != reuse consumed authority as new authority
```

Risk:
- legacy semantics are safer than blind retry but unnecessarily reduce availability for targets with proven durable deduplication;
- implementers may fail to model transport attempts separately from semantic effects.

Migration requirement:
- encode the Repair 4 recovery function explicitly;
- preserve consumed authority while permitting evidence-gated same-effect retransmission.

## Conflict C-004 — Ambiguous Outcome Encoded as Runtime Failure

Legacy schema:
- `schemas/action_authority_envelope.schema.json`

Legacy behavior:

```text
ambiguous_outcome = RECONCILIATION_FAILED
```

Repair 4 behavior:
- once crossing is possible and conclusive external evidence is absent, effect status is `UNKNOWN`;
- reconciliation may be `INSUFFICIENT` while the window is open or `UNRESOLVED` after closure;
- unknown effect cannot become success, failure, or reusable authority by inference.

Risk:
- failure terminology can leak into business logic and trigger compensation/retry prematurely.

Migration requirement:
- represent effect knowledge and reconciliation state separately;
- distinguish operational observation failure from adjudicated `UNRESOLVED`.

## Conflict C-005 — Legacy Envelope Header Does Not Match ESRM Mandatory Header

Legacy schema:
- `schemas/action_authority_envelope.schema.json`

Legacy fields include:
- `kind`;
- `state`;
- `record_hash`;
- embedded signature object.

Repair 4 requires every security-relevant signed ESRM artifact to carry the mandatory header fields:

```text
artifact_type
protocol_version = 0.1
crypto_suite = PR-ESRM-JCS-SHA256-ED25519-v1
critical_extensions = []
noncritical_extensions = {}
```

and defines a separate signed-envelope construction/domain model.

Risk:
- the old Action Authority Envelope may be mistaken for an ESRM v0.1 artifact even though its wire contract predates the frozen intake/header/signature rules.

Migration requirement:
- label the old envelope as legacy/non-ESRM;
- do not retrofit it in place;
- create new ESRM artifact schemas from the frozen source with source mapping and vectors.

## Conflict C-006 — Legacy Timestamp Profile Too Broad

Legacy schema:
- `schemas/action_authority_envelope.schema.json`

Legacy behavior:
- `issued_at` / `expires_at` use generic JSON Schema `format: date-time`.

Repair 4 behavior:
- timestamps use the narrow grammar `YYYY-MM-DDTHH:MM:SSZ`;
- UTC only;
- no offset;
- no fractional seconds;
- strict calendar validity;
- leap-second value 60 rejected.

Risk:
- multiple textual representations of the same instant can pass a broad date-time validator;
- cross-implementation canonical/security semantics can diverge.

Migration requirement:
- enforce the ESRM timestamp lexical and semantic profile against original tokens/strings.

## Conflict C-007 — Top-Level State Machine Lacks Dispatch Boundary Roles

Legacy source:
- `STATE_MACHINE.md`

Legacy progression:

```text
PERMITTED -> EXECUTING -> CONSUMED -> RECONCILED
```

Repair 4 requires explicit lifecycle distinctions including:

```text
UNDISPATCHED
DISPATCH_INTENT_RECORDED
AUTHORITY_CONSUMED
CROSSING_POSSIBLE
DISPATCH_ACKNOWLEDGED
EFFECT_CONFIRMED
EFFECT_REJECTED
EFFECT_UNRESOLVED
```

Risk:
- `EXECUTING` is too coarse to reason rigorously about crash location and whether the protected effect boundary may have been crossed.

Migration requirement:
- retain any UI/job status states separately;
- use explicit ESRM dispatch artifacts for protocol reasoning.

## Conflict C-008 — M-of-N Success Wording Is Too GitHub-Specific

Legacy source:
- `STATE_MACHINE.md`

Legacy behavior:
- `CONSUMED -> RECONCILED` requires M-of-N signed observations confirming a PR is merged.

Repair 4 behavior:
- observation and settlement predicates are transition/profile specific;
- reconciliation can produce four outcomes;
- observer policies may vary by target capability and risk class.

Risk:
- domain-specific behavior can leak into the universal state model.

Migration requirement:
- move GitHub-specific observer requirements into a GitHub settlement/observation profile;
- keep the kernel provider-neutral.

## Conflict C-009 — Existing README / Product Claims Are Narrower Than Architecture

Source:
- `README.md`

Current claim:
- single-use cryptographic authority for autonomous execution;
- two demonstrated domains;
- not third-party validated;
- not production infrastructure.

Architecture direction:
- authority-and-settlement for consequential machine-caused state transitions;
- optional clearing/network layer.

This is not currently a correctness conflict. It is a claim-boundary issue.

Migration requirement:
- do not broaden README/product claims until evidence gates are met;
- architecture remains directional until implemented and independently validated.

## Conflict C-010 — Architecture vs Protocol Ownership

Potential future risk:
- architectural documents may introduce attractive concepts such as risk classes, APIs, cell topology, observer marketplaces, or clearing profiles.

Rule:
- none becomes ESRM normative merely by appearing under `architecture/`;
- normative migration requires source identifiers, schemas, vectors, independent implementation, and conformance review.

## Migration Order

Recommended sequence:

```text
1. freeze this conflict register
2. produce source-to-artifact traceability matrix
3. generate new ESRM artifact registry from Repair 4
4. build conformance vectors
5. implement independent verifier tracks
6. migrate runtime state representations
7. deprecate legacy envelope/state-machine semantics explicitly
8. update public product language only after evidence gates
```

## Non-Destructive Rule

Do not delete legacy files to make conflicts disappear.

Historical artifacts should remain available for provenance. New files should state which protocol generation they implement and which older artifacts they supersede.

The goal is not cosmetic consistency. The goal is a traceable semantic migration with no silent changes.