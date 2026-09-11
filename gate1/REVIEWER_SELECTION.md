# Gate 1B Reviewer Selection

Status: REVIEW GOVERNANCE — NON-NORMATIVE

## Objective

Select a reviewer who can challenge source fidelity without becoming another project author.

The engagement is intentionally narrower than a full code or cryptography audit: compare frozen Repair 4 Sections 22–40 with the Gate 1 derivation target and return the required machine-readable classifications and defects.

## Minimum independence

The reviewer must not have:

- authored Repair 4;
- authored the Gate 1 derivation;
- authored the current ProofRail runtime implementation;
- participated in the internal fidelity red-team;
- a requirement to defend prior ProofRail architectural decisions.

A reviewer may communicate clarification questions to the project, but project answers are explanatory evidence only and cannot override the frozen source.

## Minimum capability

The reviewer should demonstrate experience in at least two of:

- security protocol specification review;
- specification-to-implementation or specification-to-test conformance analysis;
- cryptographic protocol design or review;
- distributed-system crash/recovery semantics;
- formal/semi-formal methods;
- IETF-style normative language;
- security test-vector design.

## Preferred engagement order

### Tier A — recognized protocol/security assessment team

Use when external credibility and later implementation audit continuity matter most.

Request a narrow, time-boxed specification/source-fidelity review first. Do not purchase a full runtime assessment before Gate 1B passes and the vector/verifier surfaces exist.

### Tier B — independent protocol/formal-methods engineer

Use when cost or scheduling makes a full assessment team premature. The output contract is identical. Identity may be public or pseudonymous if verifiable evidence of competence and independence is retained.

### Tier C — open-source community review

Useful as additional adversarial evidence but should not be the sole basis for a high-confidence Gate 1B pass unless reviewer competence and independence are established.

## Conflict test

Before accepting a review result, record:

- reviewer identity or stable pseudonym;
- professional/public evidence supporting relevant competence;
- declared relationship to ProofRail or its authors;
- whether compensation was provided;
- target source commit;
- target derivation commit;
- whether the reviewer used only the permitted evidence set for source-fidelity conclusions.

Compensation does not invalidate independence. Authorship or dependence on the derived artifacts for the review conclusion does.

## Acceptance

A reviewer result is admissible for Gate 1B only when:

1. it targets source commit `651f34bb9768dfafd53ede612ef01c9a01bd534d`;
2. it targets derivation commit `a0a168e925ca28fc95967980fd99f3116f9f36ec`;
3. all Sections 22–40 are classified;
4. the required adversarial questions are answered;
5. defects include severity and disposition;
6. no unresolved BLOCKER or MAJOR defect remains for a `READY_FOR_VECTOR_DESIGN` recommendation; and
7. the project preserves the original reviewer output rather than replacing it with a project-authored summary.

## Later audit separation

Passing Gate 1B does not eliminate later independent review. At minimum, distinct later reviews are expected for:

- audited byte-vector correctness;
- Rust verifier implementation;
- Go verifier implementation;
- disagreement harness behavior;
- lifecycle/crash semantics;
- production key custody and observation trust;
- cross-organization receipt verification.

Gate 1B proves only source-extraction fidelity sufficient to begin the next evidence gate.