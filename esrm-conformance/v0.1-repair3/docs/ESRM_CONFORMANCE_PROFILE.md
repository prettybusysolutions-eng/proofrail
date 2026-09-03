# ESRM Conformance Profile

Status: Source-lock Repair 3 harness profile. This document describes validation, schema, corpus, independence, manifest, and release mechanics only. It does not assign protocol section numbers and it does not define lifecycle, dispatch, reconciliation, settlement, recovery, Rust, Go, or vector-generation implementation.

Normative terms: RFC 2119/RFC 8174 terms are normative only in this profile document's explicit requirements.

## Profile A - Raw Intake and Resource Limits

NORMATIVE:
- ESRM-CP-A-MUST-001: Harness validation MUST treat `docs/ESRM_PROTOCOL_SECTIONS_22_40_VERBATIM.md` as the source-locked protocol document.
- ESRM-CP-A-MUST-002: Harness validation MUST keep raw-byte diagnostic hashes outside subject artifacts.
- ESRM-CP-A-MUST-003: Harness validation MUST enforce resource-limit checks recursively where structural validation is implemented.
- ESRM-CP-A-MUST-NOT-001: Harness validation MUST NOT rewrite or normalize the verbatim protocol source.

## Profile B - Schema Scope

NORMATIVE:
- ESRM-CP-B-MUST-001: Repair 3 MUST provide closed schemas only for `proofrail.transition` and `proofrail.signature`.
- ESRM-CP-B-MUST-002: Schema validation labels MUST say `STRUCTURAL_SUBSET_ONLY` until a complete Draft 2020-12 validator is used.
- ESRM-CP-B-MUST-003: Structural validation MUST reject `protocol_version` values other than `0.1`.
- ESRM-CP-B-MUST-004: Structural validation MUST reject empty transition nested objects for `pre_state`, `rules`, `authority`, `transition`, `execution`, and `settlement`.
- ESRM-CP-B-MUST-005: Structural validation MUST reject `noncritical_extensions` when it is an array.
- ESRM-CP-B-MUST-006: Structural validation MUST reject unknown nested transition members.
- ESRM-CP-B-MUST-007: Structural validation MUST reject a missing registered domain.
- ESRM-CP-B-MUST-008: Structural validation MUST reject lowercase domain substitutes.

## Profile C - Corpus and Vectors

NORMATIVE:
- ESRM-CP-C-MUST-001: Repair 3 MUST NOT generate binary vectors.
- ESRM-CP-C-MUST-002: Repair 3 MUST keep requirement inventory separate from any future binary-vector manifest.
- ESRM-CP-C-MUST-003: Planned vector mappings MUST remain plan-only until implementation is explicitly authorized.

## Profile D - Independence

NORMATIVE:
- ESRM-CP-D-MUST-001: Future Rust and Go tracks MUST share no parsing implementation.
- ESRM-CP-D-MUST-002: Future Rust and Go tracks MUST share no canonicalization implementation.
- ESRM-CP-D-MUST-003: Future Rust and Go tracks MUST share no Base64 implementation.
- ESRM-CP-D-MUST-004: Future Rust and Go tracks MUST share no Ed25519 implementation.
- ESRM-CP-D-MUST-005: Future Rust and Go tracks MUST share no schema-validation implementation.
- ESRM-CP-D-MUST-006: Future Rust and Go tracks MUST share no commitment implementation.

## Profile E - Manifest and Release Root

NORMATIVE:
- ESRM-CP-E-MUST-001: The file manifest MUST enumerate governed Repair 3 files except the file manifest itself and release-root record.
- ESRM-CP-E-MUST-002: `file_manifest_hash` and `release_root_record_hash` MUST be reported as separate values.
- ESRM-CP-E-MUST-003: The validator command MUST be committed and runnable from a clean checkout using Python standard library only.
- ESRM-CP-E-MUST-NOT-001: Repair 3 MUST NOT claim conformance.
