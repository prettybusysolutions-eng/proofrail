# ProofRail Epistemic Claim Gate

Status: PROJECT GOVERNANCE CONTROL

Purpose: prevent internal checks, author confidence, or repeated self-review from being described as stronger evidence than they are.

This policy governs architectural, protocol, conformance, validation, audit, and readiness claims in this repository.

## Constitutional rule

Evidence determines the claim level. Claim wording MUST NOT exceed the strongest evidence class actually obtained.

Internal authorship, internal review, CI success, passing tests, demonstrations, and repeated self-review are never independent evidence merely because they are performed at different times or under different prompts.

## Claim ladder

The allowed claim states are ordered and non-interchangeable:

1. `DRAFT`
   - concept or derivation exists;
   - no completeness claim.

2. `INTERNALLY_CHECKED`
   - internal tests/review passed;
   - may still contain semantic errors, omissions, or overreach.

3. `READY_FOR_INDEPENDENT_REVIEW`
   - internal falsification attempts are complete for the declared scope;
   - bidirectional traceability is complete;
   - no known unresolved internal BLOCKER/MAJOR defects remain;
   - this is still not independent validation.

4. `INDEPENDENTLY_REVIEWED`
   - a reviewer independent of the authoring process evaluated the frozen target;
   - review evidence and dispositions are retained;
   - this does not by itself establish implementation conformance.

5. `READY_FOR_VECTOR_DESIGN`
   - independent semantic review explicitly recommends vector design;
   - no unresolved BLOCKER/MAJOR semantic-review defects remain.

6. `IMPLEMENTATION_CONFORMANCE_CANDIDATE`
   - frozen vectors/schemas and independent implementations exist;
   - disagreement/fault evidence exists;
   - external reproduction is still required for stronger claims.

7. `CONFORMANT`
   - only an explicitly defined conformance program may establish this state;
   - the required evidence must be identified before the claim is made.

No state may be inferred from a lower state.

## Mandatory falsification rule

Before advancing a semantic derivation to `READY_FOR_INDEPENDENT_REVIEW`, the project MUST perform bidirectional traceability:

```text
SOURCE -> DERIVATION
Every normative source obligation maps to explicit derived rule/test coverage.

DERIVATION -> SOURCE
Every derived semantic rule maps back to sufficient source authority.
```

The following sets MUST both be empty:

```text
unmapped_source_obligations = {}
unsupported_or_overreaching_derived_rules = {}
```

If either set is non-empty, advancement is blocked.

## Independence rule

The author, co-author, originating agent, execution agent, or system operating under the same authoring direction MUST NOT be counted as an independent reviewer.

A different prompt, model persona, time, context window, or self-adversarial pass does not create independence.

Internal red-team work is valuable evidence but remains `INTERNAL` evidence.

## Green-CI rule

`CI = PASS` means only that the encoded checks passed.

It MUST NOT be paraphrased as:

- semantically correct;
- independently validated;
- protocol correct;
- conformant;
- production safe;
- formally proven;
- externally reproduced.

unless the separate evidence required for that claim exists.

## Falsified-target rule

If a frozen review target is later falsified:

1. the target remains immutable evidence of what failed;
2. it is marked `SUPERSEDED`;
3. defects and dispositions are retained;
4. a new commit becomes the next candidate target;
5. prior passing checks MUST NOT be reused as evidence for the new target unless rerun against that exact target.

## Unknown rule

When evidence is incomplete, unavailable, contradictory, or not independently established, the system MUST state the unresolved status rather than promote a stronger claim.

`UNKNOWN` and `NOT YET PROVEN` are legitimate results.

## Forward-progress prohibition

No implementation stage may begin merely because the previous stage is convenient, mostly complete, or internally green.

A downstream stage unlocks only when its declared upstream evidence gate is satisfied.

For the current ESRM Gate 1 sequence:

```text
source extraction
  -> bidirectional traceability
  -> independent semantic review
  -> audited byte vectors
  -> independent verifiers
  -> disagreement harness
  -> complete artifact schemas
  -> lifecycle implementation
  -> crash/fault campaign
  -> real execution domains
  -> external reproduction
  -> paid high-consequence pilot
  -> cross-organization receipt verification
  -> clearing network
```

Skipping a gate requires an explicit governance change; it must never occur implicitly.

## Communication rule

Any project status statement using words such as `correct`, `validated`, `verified`, `audited`, `independent`, `conformant`, `complete`, `production-ready`, or `proven` MUST identify the evidence class supporting that word.

If the evidence class is weaker than the wording, the wording is prohibited.

## Current lesson encoded

The immediate reason for this policy is an observed failure mode: a source extraction passed structural CI and internal review, was described too strongly, and a later direct source comparison still found PARTIAL and OVERREACH defects.

The control response is not increased confidence. The control response is stricter evidence-to-claim coupling, bidirectional traceability, immutable supersession, and independent review before advancement.
