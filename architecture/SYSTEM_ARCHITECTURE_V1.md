# ProofRail / ESRM System Architecture v1

Status: NON-NORMATIVE ARCHITECTURE BASELINE

This document defines the deployment and component architecture around the current ESRM Repair 4 kernel. It is intentionally broader than the existing pilot runtime, but it does not claim that the broader architecture is implemented or conformant today.

## 1. System Objective

The system governs consequential machine-caused state transitions across trust boundaries.

A conforming deployment should make it possible to answer, with portable evidence:

```text
what was proposed?
what state was believed before execution?
what authority permitted the exact effect?
was that authority consumed?
could the protected effect boundary have been crossed?
what independently observed evidence says happened?
what adjudication followed?
what settlement state is justified?
what recovery or retry is now legal?
```

The core protocol is model-agnostic, framework-agnostic, transport-agnostic, and provider-agnostic.

## 2. Architectural Planes

The system is divided into six planes with sharply different trust semantics.

```text
+-------------------------------------------------------------+
|  INTELLIGENCE / PROPOSAL PLANE                              |
|  humans, agents, SSCE, CRL/TMM, planners                   |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|  AUTHORITY / CONTROL PLANE                                  |
|  evidence -> policy -> derivation -> admission -> authority |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|  EXECUTION PLANE                                            |
|  consume -> crossing -> adapter -> external target          |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|  OBSERVATION / ADJUDICATION PLANE                           |
|  independent reads -> observations -> reconciliation       |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|  SETTLEMENT / EVIDENCE PLANE                                |
|  settlement artifacts -> checkpoints -> portable receipts  |
+-------------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------------+
|  CLEARING / INTEROP PLANE                                   |
|  optional cross-domain registration, verification, routing |
+-------------------------------------------------------------+
```

No downward arrow grants permission to skip an intermediate semantic role.

## 3. Component Model

### 3.1 Proposal Gateway

Purpose: ingest a proposed state transition from humans, agents, automation, CRL/TMM, MCP tools, A2A tasks, CI systems, ERP workflows, or service APIs.

Responsibilities:
- normalize the proposal into a provider-neutral transition request;
- reject unsupported or ambiguous inputs before security canonicalization;
- preserve provenance of the proposing principal;
- produce no authority.

Security property:

```text
ProposalAccepted != Authorized
```

The gateway belongs outside the trusted settlement kernel wherever possible.

### 3.2 Evidence Collector

Purpose: collect the evidence required by the applicable policy and transition profile.

Evidence classes may include:
- current target state;
- approvals;
- identity assertions;
- business rules;
- change-window facts;
- risk signals;
- dependency states;
- target capability evidence;
- observer configuration;
- human authorization evidence.

Evidence collectors are replaceable. Their outputs must be committed, attributable where required, and freshness-bounded.

### 3.3 Identity Resolver

Purpose: resolve principals, workload identities, signing identities, and trust domains.

Possible inputs:
- SPIFFE/SPIRE SVIDs;
- OIDC identities;
- OAuth token metadata;
- cloud workload identity;
- enterprise IAM identity;
- hardware-backed device/workload attestation;
- human identity and approval systems.

The resolver outputs identity evidence. It does not output transition authority.

### 3.4 Policy Evaluator

Purpose: evaluate deterministic admission rules against committed evidence and current state.

Recommended implementation properties:
- deterministic input/output;
- reason codes;
- versioned rulesets;
- immutable evaluation record;
- no network side effects during decision;
- policy root committed into downstream authority.

External policy engines such as Cedar or OPA can be used, but their decision must be translated into a committed ProofRail evaluation artifact rather than trusted as hidden runtime context.

### 3.5 Authority Derivation Engine

Purpose: establish whether a valid chain of authority exists for the exact transition.

Checks include:
- signer/key validity;
- issuer recognition;
- authority lineage;
- subject binding;
- scope coverage;
- target and effect binding;
- temporal validity;
- state validity;
- evidence freshness;
- rule and policy commitments;
- required approvals;
- retry semantics;
- observer/settlement contract.

Output: authority/admission artifacts suitable for later consumption.

This component must preserve:

```text
SignatureValid != Authorized
```

### 3.6 Authority Issuer

Purpose: sign the exact authority object after successful derivation.

Production requirements:
- KMS/HSM-backed signing;
- issuer role isolation;
- explicit key-status and revocation semantics;
- auditable issuance counters;
- no direct execution credentials;
- no model-controlled private keys.

### 3.7 Consumption Registry

Purpose: establish monotonic, replay-safe consumption.

The registry is one of the highest-value consistency boundaries in the system.

Required semantics:
- atomic claim on authority/effect identifiers;
- append-only consumption fact;
- crash-safe durability before external crossing;
- replay rejection;
- checkpoint integration;
- no restoration of consumed state.

Pilot SQLite may remain useful for local testing. Production profiles require a persistence substrate whose durability and concurrency semantics are independently tested.

Possible production patterns:
- single-writer strongly durable service plus external checkpoints;
- transactional relational store with serializable claim path;
- replicated consensus store for multi-region issuance/consumption;
- HSM-backed monotonic counter combined with durable ledger;
- database plus independently retained transparency/checkpoint service.

The protocol should specify observable semantics, not mandate one database product.

### 3.8 Dispatch Boundary Manager

Purpose: durably separate preparation, consumption, and first possible protected effect crossing.

State progression:

```text
UNDISPATCHED
-> DISPATCH_INTENT_RECORDED
-> AUTHORITY_CONSUMED
-> CROSSING_POSSIBLE
-> transport-specific attempt state
```

The boundary manager must commit the consumption and crossing facts before external release.

It must never claim that `CROSSING_POSSIBLE` proves transmission or effect.

### 3.9 Execution Adapter

Purpose: translate a provider-neutral semantic transition into one provider-specific protected operation.

Every adapter has a signed/versioned adapter profile containing:
- supported transition type;
- canonical target grammar;
- canonical operation grammar;
- preflight procedure;
- dispatch procedure;
- effect identity construction;
- timeout semantics;
- idempotency behavior;
- conditional mutation capability;
- independent observation method;
- known ambiguity states;
- recovery restrictions.

The adapter itself is not allowed to assert its recovery class. The profile must reference separately verified target-capability evidence.

### 3.10 External Target

Examples:
- GitHub;
- PostgreSQL;
- cloud control plane;
- payment processor;
- ERP;
- ticketing/change-management system;
- identity platform;
- robotics controller;
- regulated filing endpoint.

ProofRail does not assume the target participates in ESRM. Participation improves guarantees but is not required for observable-only profiles.

### 3.11 Observation Adapter

Purpose: independently collect admissible empirical evidence after possible effect crossing.

Observation should use separate credentials, pathways, or authorities from execution when feasible.

Observation profile defines:
- source identity;
- query semantics;
- whether data is authoritative;
- whether negative results are closed-world;
- freshness;
- observation quorum;
- normalization and canonical commitment;
- evidence window.

A production observer must not reuse an executor response as independent truth merely by wrapping it in another artifact.

### 3.12 Reconciliation Engine

Purpose: adjudicate committed observations against the committed settlement predicate.

Output must be one of:

```text
MATCH
DIVERGED
INSUFFICIENT
UNRESOLVED
```

No fifth convenience state should bypass these semantics.

The engine should be deterministic and independently implementable.

### 3.13 Settlement Engine

Purpose: determine whether a transition has sufficient committed evidence and adjudication to become SETTLED under its settlement profile.

Settlement is a protocol fact, not a billing event and not merely a database status.

A settlement artifact should bind at minimum:
- transition commitment;
- authority and consumption commitments;
- dispatch/crossing commitments;
- observation set root;
- reconciliation commitment;
- settlement predicate/version;
- settlement epoch;
- settler identity;
- prior settlement/recovery links where applicable.

### 3.14 Recovery Engine

Purpose: determine what can legally happen after a crash, ambiguous dispatch, divergence, non-occurrence proof, or provider recovery event.

Decision kernel:

```text
if authoritative evidence says occurred:
    reconcile against the intended predicate
else if authoritative final evidence proves non-occurrence:
    require a NEW transition + NEW authority
else if durable idempotency is verified for same effect identity/payload:
    retransmit same semantic effect
else:
    UNRESOLVED; automatic retry forbidden
```

Recovery is not an adapter-local exception mechanism.

### 3.15 Evidence Ledger

Purpose: retain the ordered committed fact history.

Requirements:
- append-only logical model;
- hash linking;
- domain-separated artifact commitments;
- externally retainable checkpoints;
- sequence/range commitments;
- historical supersession rather than mutation;
- exportable artifact bundles.

A local hash chain alone is insufficient against valid tail truncation. Independent checkpoints or transparency registration are required for stronger rewrite detection.

### 3.16 Checkpoint / Transparency Bridge

Purpose: make ledger state externally retainable and independently verifiable.

The architecture should support multiple mechanisms:
- independently stored signed checkpoints;
- cloud object-lock/WORM copies;
- customer-controlled anchors;
- third-party transparency services;
- SCITT-compatible registration where semantics align.

Transparency proves registration/history properties. It does not replace authority or empirical verification.

### 3.17 Portable Verifier

Purpose: verify settlement bundles without a ProofRail-managed online service.

This is strategically mandatory.

A bundle verifier must be able to:
- strict-parse the artifacts;
- verify domain commitments and signatures;
- validate key status/authority lineage inputs supplied by the profile;
- reconstruct transition links;
- verify consumption uniqueness evidence;
- verify observation/reconciliation/settlement links;
- produce deterministic reason codes;
- surface unsupported or missing dependencies instead of guessing.

The managed service may improve convenience but must not own truth.

## 4. Canonical Transaction Flow

```text
1  proposal received
2  proposal canonicalized into semantic transition intent
3  pre-state and other required evidence collected
4  evidence commitments frozen
5  deterministic policy evaluated
6  authority lineage and scope validated
7  transition admitted
8  signed authority issued
9  immediate preflight revalidates bound mutable state
10 consumption registry atomically claims authority/effect identity
11 authority consumption durably recorded
12 dispatch intent durably recorded
13 crossing-possible artifact durably recorded
14 execution adapter may release protected instruction
15 executor receipt recorded as a claim
16 observation adapter independently queries target/world
17 observation artifacts committed
18 reconciliation engine emits MATCH/DIVERGED/INSUFFICIENT/UNRESOLVED
19 settlement engine settles only if profile predicates are satisfied
20 checkpoints/transparency records emitted
21 portable receipt/bundle exported
```

No system may jump from 14 or 15 directly to 19 solely because the provider returned HTTP 200.

## 5. Failure Matrix

| Failure point | Authority state | Effect knowledge | Automatic action |
| --- | --- | --- | --- |
| before issuance | unissued | no effect | reevaluate allowed |
| after issuance, before consumption | unconsumed until expiry/invalidation | no crossing by ProofRail | execution may still occur if authority remains valid |
| after consumption, before crossing record | consumed | no protected dispatch should occur | no authority restoration |
| after crossing record, before transport | consumed | unknown/non-effect possible | reconcile; no blind retry |
| transport timeout | consumed | unknown | query authoritative source; retry only under verified durable idempotency |
| provider definite rejection | consumed | likely/non-effect only if admissible evidence proves it | new transition/authority for later attempt |
| executor says success, observer disagrees | consumed | empirical divergence | DIVERGED or profile-specific adjudication |
| observer unavailable before deadline | consumed | insufficient | INSUFFICIENT |
| observer unavailable after window | consumed | unresolved | UNRESOLVED |
| later evidence arrives | consumed | new empirical evidence | new observation/reconciliation epoch; do not rewrite history |

## 6. Trust-Domain Topology

### 6.1 Single Enterprise

```text
Agent/CI
   |
Proposal Gateway
   |
Authority Service ---- KMS/HSM
   |
Consumption Registry
   |
Execution Adapter ---- Provider Write API
   |
Observer Service ----- Provider Read API / audit source
   |
Reconciler / Settler
   |
Evidence Ledger ---- external customer checkpoint
```

Recommended initial commercial topology: customer VPC/VNet or customer-controlled cluster with customer key custody.

### 6.2 Cross-Organization

```text
Organization A                 Organization B
--------------                 --------------
Proposer / Authority  --->  Receiving Verifier
                              |
                         Local Admission Policy
                              |
                         Local Consumption Gate
                              |
                         Target Execution
                              |
                         Independent Observation
                              |
                         Settlement Receipt
                              |
             <--- portable result / receipt ---
```

Cross-company operation must not require B to trust A's internal executor logs.

B verifies the portable authority/evidence chain under an agreed profile and may add its own local admission artifact before execution.

### 6.3 Federated Trust

Use explicit trust-domain configuration. Identity federation can be supplied by SPIFFE federation, OIDC federation, enterprise PKI, or other mechanisms. Federation proves which identities/keys are accepted; ESRM still determines whether the exact transition is authorized.

## 7. Interface Boundaries

The implementation should expose a small stable semantic API rather than leaking storage internals.

### Proposal API

```text
SubmitTransitionProposal
GetProposalStatus
```

### Evidence API

```text
CollectEvidence
RegisterEvidence
VerifyEvidence
```

### Authority API

```text
EvaluateTransition
DeriveAuthority
IssueAuthority
VerifyAuthority
```

### Consumption API

```text
ClaimAuthority
GetConsumptionProof
```

### Dispatch API

```text
PrepareDispatch
RecordCrossingPossible
Dispatch
```

### Observation API

```text
ObserveTransition
SubmitObservation
VerifyObservation
```

### Reconciliation / Settlement API

```text
Reconcile
Settle
GetSettlementBundle
```

### Recovery API

```text
AssessRecovery
AuthorizeRetransmission
CreateReplacementTransition
```

Exact wire schemas should be generated only after the artifact model is source-locked and conformance vectors exist.

## 8. Control Plane vs Data Plane

### Control Plane

Handles:
- schemas;
- registered domains;
- policy versions;
- adapter profiles;
- target-capability evidence;
- observer profiles;
- key registries/status;
- governance;
- conformance metadata.

### Transaction Data Plane

Handles:
- proposals;
- evidence commitments;
- authority objects;
- consumptions;
- dispatch/crossing artifacts;
- observations;
- reconciliations;
- settlements;
- recoveries.

Control-plane mutation must never retroactively rewrite the meaning of already committed transactions. Every transaction references the exact versions it relied upon.

## 9. Multi-Tenant SaaS Architecture

Managed ProofRail should use a cell-based architecture rather than a single global mutable authority service.

Recommended shape:

```text
Global non-authoritative routing/control
          |
   +------+------+------+
   | Cell A | Cell B | Cell C |
   +------+------+------+
      |        |        |
 tenant-key tenant-key tenant-key
 isolated ledgers / registries / observers
```

Properties:
- tenant-scoped encryption keys;
- tenant-scoped trust roots;
- no cross-tenant consumption namespace collision;
- explicit regional residency;
- blast-radius containment;
- portable export at all times;
- customer-held anchor/checkpoint option;
- BYOK/HYOK option for high-consequence buyers.

The global service must not be able to manufacture a settled artifact without the tenant's required trust material.

## 10. Performance Architecture

The hot path should distinguish precomputable work from crossing-critical work.

### Precomputable

- schema validation;
- policy compilation;
- static authority-lineage validation;
- adapter-profile loading;
- capability-evidence verification;
- nonvolatile evidence retrieval;
- canonicalization of static structures.

### Crossing-Critical

- mutable pre-state refresh;
- final scope/state comparison;
- atomic consumption claim;
- durable consumption append;
- durable crossing append;
- provider dispatch.

Optimization target: minimize time between final preflight and provider mutation while retaining durability.

Do not remove the durable consumption/crossing barrier merely to reduce latency.

## 11. Availability Model

ProofRail intentionally sacrifices some availability to avoid duplicated or falsely classified high-consequence effects.

Risk-class profiles should exist:

```text
R0  read-only / no external effect
R1  reversible low-cost effect
R2  consequential but compensatable effect
R3  high-value / regulated / hard-to-reverse effect
R4  irreversible or safety-critical effect
```

Higher classes increase:
- authority quorum;
- key isolation;
- observation independence;
- checkpoint durability;
- settlement evidence requirements;
- recovery conservatism.

The protocol should define semantics common to all classes; profiles define deployment requirements.

## 12. CRL / TMM / SSCE Integration

The intelligence stack belongs strictly upstream of authority.

```text
SSCE
  generates candidate capabilities / plans
      |
CRL
  represents causal/topological state
      |
TMM
  serializes proposed graph mutation
      |
ProofRail Proposal Gateway
  converts accepted mutation into exact transition proposal
      |
ESRM Authority + Settlement Kernel
```

Rules:
- TMM is SPECULATIVE input;
- causal confidence does not equal authority;
- self-generated capability cannot grant itself execution rights;
- ProofRail evaluates concrete external mutations, not the language model's internal intent;
- newly synthesized tools/adapters begin with the weakest target-capability class until independently evidenced.

This preserves self-improving intelligence without self-expanding authority.

## 13. OpenClaw Integration

OpenClaw is an execution harness, not the source of authority.

Integration contract:
- OpenClaw receives an exact approved transition/effect reference;
- ProofRail controls whether a protected adapter call may proceed;
- OpenClaw returns structured executor evidence;
- executor evidence remains a claim until independent observation;
- OpenClaw cannot promote its own PASS result into settlement;
- local fallback models may propose/read/analyze according to policy but cannot bypass capability/authority gates.

This matches the existing evidence-oriented operating model and prevents executor self-certification.

## 14. External Standards Mapping

### MCP

Use as a transport/tool interface. MCP OAuth answers whether a client can access a protected MCP resource. ProofRail additionally binds one exact consequential effect, consumes transition authority, and reconciles external outcome.

### A2A

Use for discovery/delegation/task transport. Any ProofRail authority passed through A2A remains scope-bound and non-expandable.

### SPIFFE/SPIRE

Use for portable workload identity and trust-domain federation. SPIFFE identity becomes ProofRail identity evidence, not ProofRail authority.

### OpenTelemetry

Use for metrics/traces/correlation. Emit transition/authority/consumption/reconciliation identifiers as telemetry attributes, while keeping telemetry outside authoritative settlement unless a profile explicitly promotes a source.

### in-toto

Use for software supply-chain attestations and bridge execution artifacts where appropriate. Do not conflate in-toto attestation with runtime transition authority.

### SCITT / transparency services

Use for registration and independently verifiable receipts/checkpoint retention. Registration proves transparency properties, not truth of the underlying statement.

## 15. Minimum Production Stack

A credible first enterprise production profile should include:

```text
API gateway / mTLS
workload identity (SPIFFE/SPIRE or cloud equivalent)
policy evaluator
ProofRail authority service
KMS/HSM issuer keys
serializable consumption registry
append-only artifact store
external checkpoint store
one high-consequence execution adapter
separately credentialed observer
reconciliation + settlement service
portable verifier
OpenTelemetry diagnostics
conformance runner
```

Optional initially:
- clearing network;
- multi-party settlement federation;
- blockchain;
- custom consensus protocol;
- globally replicated public log.

Avoid building those before independent conformance and paid deployment evidence.

## 16. Scale Model

The architecture scales by partitioning independent transition namespaces, not by centralizing all authority globally.

Partition keys may include:
- tenant;
- trust domain;
- target provider;
- protected resource namespace;
- regulatory region.

Cross-partition transitions require an explicit multi-resource or clearing profile rather than accidental distributed transactions.

## 17. Security Non-Goals

The architecture does not claim to:
- decide whether a business policy is wise;
- guarantee uncompromised roots of trust;
- make opaque providers Byzantine fault tolerant;
- prove physical-world truth without adequate sensors/authoritative evidence;
- create universal exactly-once execution;
- eliminate the need for provider-native controls;
- replace KMS, IAM, databases, backups, or provider audit systems.

Its claim is narrower and stronger:

> uncertainty about consequential external effects is preserved as uncertainty; authority is explicit and consumable; empirical outcome is independently distinguishable from execution claims; settlement is evidence-gated and portable.

## 18. Implementation Boundary

This document is architecture, not protocol conformance.

The next code-producing work should target the smallest missing vertical slice that exercises the architecture without broadening claims:

```text
neutral transition schema
-> deterministic authority verification
-> durable consumption
-> crash-safe crossing artifact
-> one provider-neutral adapter interface
-> separate observation interface
-> four-way reconciliation
-> settlement artifact
-> portable verification bundle
```

Only after that vertical slice passes independent implementation/reproduction should cross-company clearing become an implementation target.