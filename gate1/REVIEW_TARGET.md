# Gate 1B Semantic Review Target V2

Status: REVIEW TARGET — NO CONFORMANCE CLAIM

Authoritative Repair 4 source commit:

`651f34bb9768dfafd53ede612ef01c9a01bd534d`

Current Gate 1 derivation review target before this marker commit:

`f81f0ca55b065d60e8c8439eb85d6358c608a45b`

## Superseded target

The earlier target:

`a0a168e925ca28fc95967980fd99f3116f9f36ec`

is **superseded and must not be reviewed as the current Gate 1B candidate**. A second internal source-fidelity pass found concrete PARTIAL/OVERREACH defects in that target, including Section 22 wording that strengthened the source, incomplete Section 25 signature-input extraction, omitted Section 29 timestamp whitespace rejection, an under-explicit Section 35 dispatch-intent field requirement, omitted Section 38 recovery-input admissibility preconditions, and unsupported global-finality wording for SETTLED.

Those findings are evidence that internal green checks do not establish semantic correctness.

## V2 repair content

At target `f81f0ca55b065d60e8c8439eb85d6358c608a45b`:

- Section 22 tracks temporal/state predicates that hold without adding a commitment requirement to that rule;
- Section 25 explicitly preserves the signing input `ASCII(PROOFRAIL:SIGNATURE:V1) || NUL || UTF8(JCS(E_tau))`;
- Section 29 explicitly preserves the signed-timestamp no-whitespace rule;
- Section 35 explicitly preserves `transition_id` as a frozen dispatch-intent field;
- Section 38 explicitly preserves the required validity/admissibility qualifications on D, K, Q, and F before recovery branch selection;
- the SETTLED epistemic-role description no longer imports a stronger global-finality claim than Repair 4;
- Gate 1 structural CI contains regression checks for these repaired obligations;
- `Gate 1 Structure` completed successfully;
- `Attestation Check` completed successfully.

The marker commit containing this file is not itself part of the semantic extraction under review. Reviewers must evaluate the V2 target commit above against Repair 4 at the source commit above.

## Required reviewer input/output contract

- `gate1/INDEPENDENT_REVIEW_PACKET.md`
- `gate1/independent-review-result.schema.json`

The reviewer remains free to classify any section 22–40 as `MATCH`, `PARTIAL`, `MISSING`, or `OVERREACH` and to find defects we have not found.

Gate 1B passes only if an independent reviewer returns `READY_FOR_VECTOR_DESIGN` with no unresolved BLOCKER or MAJOR defects. Structural CI, internal red-team work, authorship, or this marker cannot satisfy that condition.
