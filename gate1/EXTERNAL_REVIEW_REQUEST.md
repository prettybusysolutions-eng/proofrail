# External Review Request — ESRM Gate 1B

ProofRail is requesting an independent semantic review of a source-extracted conformance baseline.

This is not a product endorsement request, novelty review, code audit, or standardization request.

## Review question

Does the Gate 1 derivation at commit `a0a168e925ca28fc95967980fd99f3116f9f36ec` faithfully represent Repair 4 Sections 22–40 at source commit `651f34bb9768dfafd53ede612ef01c9a01bd534d`, without importing legacy semantics, weakening requirements, or inventing new normative behavior?

## Reviewer profile

A suitable reviewer should be independent of the Gate 1 authoring process and comfortable reviewing at least one of:

- security protocol specifications;
- cryptographic protocol implementations against written specifications;
- distributed-systems recovery / ambiguity semantics;
- formal or semi-formal conformance specifications;
- IETF-style normative text and test extraction.

The reviewer does not need prior ProofRail knowledge.

## Inputs

Start only with:

1. frozen source at `esrm-conformance/v0.1-repair4/docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md` from source commit `651f34bb9768dfafd53ede612ef01c9a01bd534d`;
2. Gate 1 derivation at target commit `a0a168e925ca28fc95967980fd99f3116f9f36ec`;
3. `gate1/INDEPENDENT_REVIEW_PACKET.md`;
4. `gate1/independent-review-result.schema.json`.

Do not use the existing ProofRail implementation as evidence that a derived rule is correct.

## Required output

For every source section 22–40 classify the derivation as:

- `MATCH`
- `PARTIAL`
- `MISSING`
- `OVERREACH`

Record defects as `BLOCKER`, `MAJOR`, `MINOR`, or `EDITORIAL` and return one final recommendation:

- `REJECT`
- `REVISE_AND_REVIEW`
- `READY_FOR_VECTOR_DESIGN`

A clean structural CI result is not evidence of semantic fidelity. The project intentionally requires external review before audited byte-vector design or independent verifier implementation begins.

## Disclosure

The project has already performed an internal fidelity red-team and corrected several under-extracted obligations. That review was authored inside the project and therefore does not count as independent evidence.