# ESRM Conformance Profile

Status: Repair 4 harness profile. This document contains harness mechanics only and does not assign protocol section numbers. No Rust, Go, vector, lifecycle, dispatch, reconciliation, settlement, or recovery implementation is started.

## Profile A - Source Lock

NORMATIVE:
- ESRM-CP-A-MUST-001: The harness MUST treat docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md as the Repair 4 ASCII semantic source lock.
- ESRM-CP-A-MUST-002: The harness MUST reject tab byte 0x09, backspace byte 0x08, carriage return byte 0x0d, replacement character U+FFFD, and LaTeX command sequences beginning with backslash in the ASCII source.
- ESRM-CP-A-MUST-003: The harness MUST validate exact section numbers 22 through 40 and exact section titles.
- ESRM-CP-A-MUST-004: The harness MUST validate required ASCII formula blocks.

## Profile B - Schema Scope

NORMATIVE:
- ESRM-CP-B-MUST-001: Schema meta-validation MUST be labeled STRUCTURAL_SUBSET_ONLY until a complete Draft 2020-12 validator is used.
- ESRM-CP-B-MUST-002: Schema instance validation MUST be labeled STRUCTURAL_SUBSET_ONLY until a complete Draft 2020-12 validator is used.
- ESRM-CP-B-MUST-003: Structural tests MUST reject protocol_version ESRM-v0.1.
- ESRM-CP-B-MUST-004: Structural tests MUST reject empty pre_state, rules, authority, transition, execution, and settlement objects.
- ESRM-CP-B-MUST-005: Structural tests MUST reject noncritical_extensions as an array.
- ESRM-CP-B-MUST-006: Structural tests MUST reject unknown nested transition members.
- ESRM-CP-B-MUST-007: Structural tests MUST reject missing registered domains and lowercase domain substitutes.
- ESRM-CP-B-MUST-008: Structural tests MUST reject every mismatched signed_artifact_type and signed_artifact_domain pair.
- ESRM-CP-B-MUST-009: Semantic timestamp tests MUST reject invalid month, invalid day for month and year, invalid hour, invalid minute, invalid second, and leap-second value 60.

## Profile C - Extensions

NORMATIVE:
- ESRM-CP-C-MUST-001: Repair 4 MUST fail closed on extensions with EXTENSIONS_PRESENT_BUT_NONE_REGISTERED_V0_1.
- ESRM-CP-C-MUST-002: critical_extensions MUST have maxItems 0.
- ESRM-CP-C-MUST-003: noncritical_extensions MUST have maxProperties 0 and additionalProperties false.

## Profile D - Manifests and Gates

NORMATIVE:
- ESRM-CP-D-MUST-001: The file manifest MUST enumerate governed Repair 4 files except itself and release-root record.
- ESRM-CP-D-MUST-002: file-manifest hash and release-root-record hash MUST be reported separately.
- ESRM-CP-D-MUST-003: Repair 4 MUST NOT generate binary vectors.
- ESRM-CP-D-MUST-004: Repair 4 MUST NOT begin Rust or Go implementation.
- ESRM-CP-D-MUST-005: Repair 4 MUST NOT claim conformance.
