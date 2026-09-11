# ESRM Gate 1 — Source-Extracted Kernel and Conformance Baseline

Status: NON-NORMATIVE DERIVATION PACKAGE

Authoritative source remains:
`esrm-conformance/v0.1-repair4/docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md`

This directory converts Repair 4 semantics into traceable implementation inputs without modifying or superseding the frozen source.

## Gate 1 outputs

- `esrm-rule-registry.json` — stable rule identifiers mapped to Repair 4 sections, validation stages, affected roles/artifacts, and required test families.
- `artifact-role-registry.json` — epistemic roles and registered artifact domains, preserving the rule that no artifact may impersonate another role.
- `conformance-corpus-manifest.json` — deterministic positive/negative/ambiguity corpus families required before verifier implementation claims.
- `INDEPENDENT_IMPLEMENTATION_CONTRACT.md` — separation rules for future Rust and Go verifier tracks.
- `LEGACY_ISOLATION.md` — legacy semantics explicitly forbidden from entering the Gate 1 corpus.
- `tools/validate_gate1.py` — standard-library structural validator for registry/corpus coverage and selected legacy leakage.

## Structural validation

Run:

```bash
python3 gate1/tools/validate_gate1.py
```

A structural PASS means only that the derived package satisfies its machine-checkable Gate 1 shape and coverage assertions. It is not protocol conformance or independent semantic review.

## Gate discipline

This package does not claim ESRM conformance, production readiness, standard adoption, or exactly-once execution. A generated rule is only a traceability object. If a generated rule conflicts with Repair 4, Repair 4 wins and the generated object must be corrected.

No generated artifact in this directory may become normative merely by being consumed by code.

## Exit condition

Gate 1 is ready for implementation review only when:

1. every extracted normative rule maps to Repair 4 section(s);
2. every Section 22–40 safety requirement has at least one planned conformance test family;
3. reconciliation cases preserve MATCH, DIVERGED, INSUFFICIENT, and UNRESOLVED as distinct results;
4. consumed authority is never restored by any recovery case;
5. ambiguous crossing never becomes inferred success, inferred failure, or reusable authority;
6. durable idempotency requires committed capability evidence rather than adapter self-assertion; and
7. the Rust and Go tracks can be implemented without sharing security-critical parsing/canonicalization/state-machine code.