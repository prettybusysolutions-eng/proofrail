# Gate 1B Semantic Review Target

Status: REVIEW TARGET — NO CONFORMANCE CLAIM

Authoritative Repair 4 source commit:

`651f34bb9768dfafd53ede612ef01c9a01bd534d`

Gate 1 derivation review target before this marker commit:

`a0a168e925ca28fc95967980fd99f3116f9f36ec`

The marker commit containing this file is not itself part of the semantic extraction under review. Reviewers must evaluate the derivation at the target commit above against Repair 4 at the source commit above.

At target commit `a0a168e925ca28fc95967980fd99f3116f9f36ec`:

- `Gate 1 Structure` completed successfully.
- `Attestation Check` completed successfully.
- an internal fidelity red-team had already identified under-extracted source obligations;
- the rule registry and corpus manifest were expanded to represent those known obligations;
- the internal red-team is explicitly not independent validation;
- the external reviewer remains free to classify any section as MATCH, PARTIAL, MISSING, or OVERREACH and to find additional defects.

Required reviewer input/output contract:

- `gate1/INDEPENDENT_REVIEW_PACKET.md`
- `gate1/independent-review-result.schema.json`

Gate 1B passes only if an independent reviewer returns `READY_FOR_VECTOR_DESIGN` with no unresolved BLOCKER or MAJOR defects. Structural CI, authorship, or this marker cannot satisfy that condition.