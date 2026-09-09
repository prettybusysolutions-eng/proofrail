# Validation and Build Gates

Status: NON-NORMATIVE EXECUTION PROGRAM

This document defines the order in which the architecture may become an implementation claim. The purpose is to prevent architectural ambition from outrunning evidence.

## 1. Governing Principle

No feature becomes a protocol, production, interoperability, or market claim merely because it is documented or implemented once.

Each claim class has a minimum evidence threshold.

```text
DOCUMENTED
  != IMPLEMENTED
  != TESTED
  != REPRODUCED
  != INDEPENDENTLY IMPLEMENTED
  != PRODUCTION VALIDATED
  != MARKET VALIDATED
```

The system should always publish the strongest true level and no stronger.

## 2. Gate 0 — Preserve Repair 4

Objective: keep the current ESRM Repair 4 source and evidence intact while architecture work proceeds.

Required:
- Repair 4 branch remains immutable except through a separately reviewed repair process;
- architecture changes occur on separate branches/directories;
- no architecture document claims conformance;
- no old artifacts are silently rewritten;
- existing reproducible ProofRail tests remain available.

Exit evidence:
- branch comparison proves no modification to Repair 4 source on the architecture branch before intentional implementation begins;
- architecture docs explicitly defer to the normative source.

Failure condition:
- any architectural convenience silently alters protocol semantics.

## 3. Gate 1 — Canonical Kernel Extraction

Objective: create one internally consistent machine-readable model of the already-frozen ESRM artifact roles and transitions.

Deliverables:
- artifact registry;
- transition/state registry;
- registered domain registry;
- reason-code registry;
- explicit epistemic-role mapping;
- reconciliation algebra tests;
- consumption/recovery invariants encoded as executable properties.

The extraction must not invent new normative requirements.

Testing:
- parser ambiguity corpus;
- duplicate-key corpus;
- Unicode/canonicalization corpus;
- numeric profile corpus;
- timestamp corpus;
- domain-separation corpus;
- signature-envelope corpus;
- authority-vs-attestation negative cases.

Exit evidence:
- every extracted rule maps back to a source location;
- no unmapped normative assertion in generated conformance material;
- independent review can trace generated tests to source.

## 4. Gate 2 — Two Independent Parsers / Verifiers

Objective: eliminate single-implementation self-consistency as evidence.

Required:
- Implementation A and Implementation B written independently;
- no shared parsing/canonicalization/signature/commitment code;
- both consume the same source-locked vectors;
- both emit deterministic reason codes for positive and negative cases.

Recommended languages:
- Rust;
- Go.

A Python harness may orchestrate tests but must not be the source of cryptographic/canonical truth for both implementations.

Exit evidence:

```text
same valid artifacts accepted
same invalid artifacts rejected
same commitments computed
same signatures verified
same reconciliation algebra produced
```

across both implementations.

Failure condition:
- both implementations share a hidden dependency that could reproduce the same bug.

## 5. Gate 3 — Full Authority Lifecycle Vertical Slice

Objective: implement the complete lifecycle for one execution domain rather than broad partial features.

Required vertical slice:

```text
proposal
-> evidence
-> deterministic evaluation
-> authority derivation
-> signed authority
-> atomic consumption
-> dispatch intent
-> crossing-possible record
-> provider call
-> executor claim
-> independent observation
-> reconciliation
-> settlement
-> portable bundle
-> independent verification
```

Initial domain recommendation: GitHub merge, because the repository already contains evidence and state-binding logic for it.

Exit evidence:
- deterministic end-to-end reproduction;
- stale state rejected;
- mutated parameters rejected;
- replay rejected;
- false executor success rejected;
- ambiguous network condition preserved as unknown;
- successful provider observation settles only under the committed predicate;
- portable bundle independently verifies.

## 6. Gate 4 — Crash and Ambiguity Campaign

Objective: prove the architecture under the exact conditions where ordinary agent systems become unsafe.

Inject crashes at every durable boundary:

```text
before authority issuance
after issuance before consumption
during atomic consumption
after consumption before dispatch intent
after dispatch intent before crossing record
after crossing record before write syscall
mid-write / connection interruption
after provider acceptance before response
before observer query
during observer query
before reconciliation append
before settlement append
```

For each crash point record:
- durable artifacts present;
- authority state;
- effect knowledge;
- legal recovery action;
- whether retry is forbidden/permitted;
- final reconciliation state.

Required property:

> no crash converts uncertain external effect status into false success, false failure, or restored authority.

Exit evidence:
- machine-readable crash matrix;
- deterministic replay of every injected crash class;
- no hidden adapter auto-retry bypasses recovery rules.

## 7. Gate 5 — Target Capability Evidence

Objective: prove that recovery behavior derives from target capability evidence rather than adapter claims.

Test target classes:
- DURABLE_IDEMPOTENCY;
- CONDITIONAL_MUTATION;
- QUERYABLE_EFFECT;
- OBSERVABLE_ONLY;
- OPAQUE_TARGET.

For each profile:
- capability evidence artifact created before transition;
- evidence includes target/version/scope/durability semantics;
- recovery engine consumes the committed evidence;
- changing capability after crash does not retroactively change recovery rights.

Critical negative test:

```text
adapter says idempotent
but capability evidence absent/invalid
=> automatic retry denied
```

## 8. Gate 6 — Second Execution Domain

Objective: prove that the semantics are not GitHub-specific.

Recommended domain: production-capable database migration profile or cloud IAM mutation.

Requirements:
- same core authority artifact family;
- same consumption semantics;
- same crossing semantics;
- same reconciliation algebra;
- domain-specific adapter/observer only where necessary;
- no special-case bypass of kernel invariants.

Exit evidence:
- two domains pass the same core conformance suite;
- differences are isolated to versioned adapter/settlement profiles.

## 9. Gate 7 — Independent Author / External Reproduction

Objective: move beyond internally authored tests.

Required:
- evaluator receives public source, vectors, and reproduction procedure;
- evaluator operates in a clean environment;
- evaluator records toolchain and hashes;
- evaluator intentionally mutates artifacts and confirms deterministic rejection;
- evaluator publishes or signs a reproduction record.

Stronger evidence:
- evaluator authors additional negative tests not supplied by ProofRail;
- ProofRail implementation fails at least one novel test, is repaired, and the repair becomes part of the corpus.

A discovered defect is useful evidence if handled transparently. A test suite that never finds faults is not automatically strong evidence.

## 10. Gate 8 — Framework / Transport Interoperability

Objective: prove that ESRM is not coupled to one agent transport.

Profiles:
- direct REST/gRPC execution;
- MCP-carried transition reference;
- A2A-carried delegated task artifact.

Required invariants:
- transport identity does not become transition authority;
- delegation cannot expand authority;
- transport retry does not silently create new semantic transition attempts;
- settlement remains transport-independent.

Exit evidence:
- same portable settlement verifier validates equivalent transitions transported through at least two unrelated mechanisms.

## 11. Gate 9 — Workload Identity / Key Custody Productionization

Objective: remove pilot-grade identity and key assumptions.

Requirements:
- KMS/HSM signing for authority issuers;
- separately controlled observer credentials;
- key-status/revocation path;
- workload identity (SPIFFE/SPIRE, cloud workload identity, or equivalent);
- tenant-scoped trust roots;
- rotation test;
- compromised/retired key negative tests;
- documented emergency recovery.

Exit evidence:
- no long-lived signing private key in model-accessible process memory or repository secrets;
- issuer compromise blast radius is bounded and testable.

## 12. Gate 10 — Durable Multi-Writer Consumption

Objective: solve the current pilot serialization limitation without weakening replay guarantees.

Required tests:
- concurrent consumers racing same authority;
- concurrent independent authorities;
- checkpoint advance under concurrency;
- database/process crash during claim;
- network partition behavior;
- failover behavior;
- stale replica behavior;
- restored snapshot/replay attempt.

Required property:

```text
for one single-use authority:
number_of_successful_consumption_claims <= 1
```

No availability optimization may permit two successful claims.

## 13. Gate 11 — External Checkpoint / Transparency Independence

Objective: make rewrite/tail-truncation detection independent of the mutable primary evidence store.

Implement at least two checkpoint retention paths, for example:
- customer-controlled object-lock/WORM storage;
- independent transparency service / SCITT-compatible registration;
- external auditor-held signed checkpoints.

Tests:
- tail truncation;
- historical record replacement;
- checkpoint omission;
- fork/equivocation attempt;
- unavailable transparency service.

The settlement bundle must remain verifiable even if one checkpoint service disappears, subject to the profile's availability assumptions.

## 14. Gate 12 — Security Review

Objective: obtain adversarial review by parties who did not design the protocol.

Scope:
- parser/canonicalization differential attacks;
- cryptographic misuse;
- authority confusion;
- replay and race attacks;
- TOCTOU;
- identity federation confusion;
- observer collusion/false evidence;
- ledger truncation/forking;
- retry ambiguity;
- profile downgrade;
- malicious adapter;
- compromised verifier;
- cross-tenant isolation;
- denial of service around the crossing boundary.

Required output:
- findings with severity;
- reproducible test cases;
- dispositions;
- explicit residual risk.

Do not market 'audited' without naming the exact scope/version/date of the review.

## 15. Gate 13 — Paid Design Partner

Objective: establish willingness to pay for the runtime assurance primitive.

Design partner requirements:
- real consequential workflow;
- existing system of record/provider;
- measurable current failure/audit burden;
- production-like identities and keys;
- defined success metric;
- paid engagement.

Preferred commercial structure:
- $15k–$30k scoped pilot;
- buyer supplies real workflow and subject-matter owner;
- ProofRail supplies adapter/profile, evidence bundle, failure campaign, and evaluation report;
- explicit conversion path to recurring platform contract.

Exit evidence:
- buyer pays;
- workflow executes under agreed profile;
- buyer independently verifies artifacts;
- buyer can state what risk/cost ProofRail reduced.

## 16. Gate 14 — Two Independent Organizations

Objective: establish the minimum evidence for clearing/network behavior.

Required:
- Organization A originates or authorizes a transition;
- Organization B receives/verifies/executes or relies on it;
- both can independently verify the resulting portable receipt;
- neither needs to trust the other's agent/executor logs;
- trust profile is explicit and versioned.

This gate matters more than raw transaction volume.

## 17. Gate 15 — Clearing Pilot

Objective: introduce optional network services only after portable interoperability exists.

Build only:
- receipt registration;
- profile discovery;
- retained checkpoint service;
- verification API;
- optional observer routing.

Do not initially build:
- proprietary global consensus;
- token/cryptocurrency economics;
- universal legal arbitration;
- blockchain dependency;
- autonomous credit/reputation scoring.

Exit evidence:
- network service improves discovery/retention/operations while offline independent verification still works.

## 18. Gate 16 — Standardization Candidate

Objective: determine whether ESRM deserves external standards work.

Minimum prerequisites:
- two independent implementations;
- two execution domains;
- external security review;
- independent reproduction;
- at least one cross-organization receipt exchange;
- stable source and conformance corpus;
- documented interoperability with adjacent standards;
- no requirement for proprietary ProofRail service.

Only then is formal standards-body submission strategically credible.

## 19. Red-Team Matrix

Every release candidate should face at least these adversarial families:

### Artifact attacks
- duplicate keys;
- invalid Unicode;
- noncanonical Base64url;
- numeric alternate forms;
- timestamp edge cases;
- unknown domains;
- cross-type signature substitution;
- extension confusion;
- schema smuggling.

### Authority attacks
- valid signature / invalid scope;
- valid signer / revoked key;
- correct scope / stale state;
- delegation expansion;
- replayed authority;
- reused nonce;
- policy rollback;
- checkpoint rollback.

### Execution attacks
- parameter mutation after approval;
- target substitution;
- TOCTOU state change;
- concurrent consumption;
- hidden retry;
- transport duplication;
- crash at every boundary.

### Observation attacks
- executor self-observation;
- stale observer;
- fabricated negative evidence;
- non-closed-world absence inference;
- quorum key compromise;
- contradictory observers;
- observation after deadline.

### Settlement attacks
- MATCH without required evidence;
- timeout -> DIVERGED;
- insufficient -> success;
- late evidence mutates prior reconciliation;
- settlement profile downgrade;
- missing consumption artifact;
- missing crossing artifact.

## 20. Release Labels

Use precise release claims:

```text
EXPERIMENTAL
  implementation exists; semantics may change

REPRODUCIBLE
  published procedure recreates claimed results

CONFORMANCE-CANDIDATE
  source/vectors stable enough for independent implementation

CROSS-IMPLEMENTATION VERIFIED
  independent implementations agree on corpus

PILOT-VALIDATED
  production-like workflow exercised with design partner

PRODUCTION PROFILE
  deployment/security/operations requirements defined and independently reviewed

INTEROPERABLE
  unrelated organizations/implementations exchange and verify artifacts
```

Avoid 'production-ready', 'standard', 'solved', 'exactly once', 'trustless', or 'unhackable' unless an exact qualified claim can survive independent review.

## 21. Commercial Stop Conditions

Stop adding protocol breadth and focus on sales/integration when:
- one vertical slice is independently reproducible;
- one high-consequence adapter is production-credible;
- one external evaluator accepts the evidence model;
- a buyer can run the verifier without ProofRail cloud.

Stop building the clearing network if:
- buyers only value local controls;
- counterparties do not ask to verify receipts;
- receipt portability does not reduce integration/audit cost.

Network architecture is a hypothesis until counterparty behavior validates it.

## 22. Immediate Next Work Package

The next engineering package should be narrow:

```text
A. freeze architecture docs for review
B. generate source-to-invariant traceability matrix
C. define machine-readable artifact/role registry from Repair 4
D. create independent implementation boundary plan (Rust vs Go)
E. build full lifecycle vectors for consumption/crossing/reconciliation
F. run differential conformance harness
```

Do not add another execution domain, clearing service, or intelligence feature before A–F are complete.

The architecture wins by becoming harder to falsify, not by becoming larger faster.