# Validation Plan - Repair 1

Required validation before audit:

1. JSON parse every registry, schema, manifest, and validation artifact.
2. Meta-validate JSON Schemas with Draft 2020-12.
3. Validate manifest instances against the binary-vector manifest schema.
4. Check artifact-type/domain/schema bijection against the closed registry.
5. Regenerate requirement inventory directly from `ESRM_CANONICAL_BASELINE_SECTIONS_22_48.md`.
6. Verify every RFC 2119/8174 requirement is mapped.
7. Verify file-hash manifest excludes itself and includes every other governed file.
8. Record file-hash manifest SHA-256 in `release-root.json`.
9. Reproduce the same results from a clean checkout of the pushed branch.

NO CLAIM OF CONFORMANCE.
