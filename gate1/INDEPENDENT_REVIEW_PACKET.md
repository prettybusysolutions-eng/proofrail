# ESRM Gate 1 Independent Semantic Review Packet

Status: REVIEW INPUT — NO CONFORMANCE CLAIM

## Reviewer mission

Determine whether the Gate 1 derivation faithfully represents Repair 4 Sections 22–40 without importing legacy ProofRail semantics or inventing new normative behavior.

The reviewer is not being asked whether ProofRail is a good product, whether ESRM is novel, or whether the architecture should be adopted. The review target is narrower: **source fidelity and implementation neutrality**.

## Authoritative source

`esrm-conformance/v0.1-repair4/docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md`

If any Gate 1 artifact conflicts with that source, the Gate 1 artifact is wrong.

## Derived artifacts to inspect

1. `gate1/esrm-rule-registry.json`
2. `gate1/artifact-role-registry.json`
3. `gate1/conformance-corpus-manifest.json`
4. `gate1/INDEPENDENT_IMPLEMENTATION_CONTRACT.md`
5. `gate1/LEGACY_ISOLATION.md`
6. `gate1/tools/validate_gate1.py`

## Required review procedure

For every Repair 4 section 22 through 40:

1. identify each security-relevant MUST / MUST NOT / SHALL / forbidden inference / global safety property;
2. locate its Gate 1 rule ID or corpus family;
3. mark the mapping as `MATCH`, `PARTIAL`, `MISSING`, or `OVERREACH`;
4. identify any Gate 1 text that strengthens, weakens, or changes the source semantics;
5. identify any source requirement that cannot yet be made into a deterministic implementation-independent expected result;
6. identify any place where a registered domain or epistemic role was incorrectly treated as proof of a frozen standalone wire schema.

## Mandatory adversarial questions

The reviewer must answer these explicitly:

- Can a cryptographically valid signature become `AUTHORIZED` without every Section 22 authority predicate?
- Can artifact-supplied domain text select the commitment domain?
- Can duplicate keys survive by being collapsed into a host-language map first?
- Can a generic RFC3339/JSON-Schema `date-time` value pass where ESRM's narrower timestamp profile should reject it?
- Can `INSUFFICIENT` and `UNRESOLVED` collapse into one failure state?
- Can timeout alone imply `DIVERGED`?
- Can silence prove absence without committed closed-world coverage?
- Can consumed authority ever become reusable after proof of non-effect?
- Can `CROSSING_POSSIBLE` prove transmission or semantic effect?
- Can an adapter self-declare `DURABLE_IDEMPOTENCY`?
- Can a retransmission mutate target, effect identity, canonical payload, or semantic transition while keeping old authority?
- Can an executor response count as independent empirical observation?
- Can the derived package claim universal exactly-once execution?
- Can settlement be established when any required epistemic role is missing or impersonated?

Any `YES` answer to one of the forbidden cases is a Gate 1 defect.

## Reviewer output format

Return one machine-readable table or JSON object containing:

- `reviewer_identity_or_pseudonym`
- `review_date`
- `source_commit`
- `gate1_head_commit`
- `section_results` for 22..40
- `defects` with severity `BLOCKER`, `MAJOR`, `MINOR`, or `EDITORIAL`
- `missing_rules`
- `overreaching_rules`
- `ambiguous_source_points`
- `legacy_leakage_findings`
- `recommendation`: `REJECT`, `REVISE_AND_REVIEW`, or `READY_FOR_VECTOR_DESIGN`

## Independence expectation

The reviewer should not use the existing ProofRail implementation as evidence that the derived semantics are correct. Review Repair 4 against Gate 1 directly. Existing code may explain history but must not override the frozen source.

## Gate decision

Only a review with no unresolved BLOCKER/MAJOR defects may recommend `READY_FOR_VECTOR_DESIGN`. That recommendation still does not establish ESRM conformance; it only authorizes the next evidence-building gate.