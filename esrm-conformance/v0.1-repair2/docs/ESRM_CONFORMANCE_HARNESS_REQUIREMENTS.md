# ESRM Conformance Harness Requirements

Status: Repair 2 repository artifact. These requirements govern the conformance laboratory, registries, schemas, manifests, validation, release roots, corpus planning, and implementation gates. They do not reuse ESRM protocol section numbers and they do not define lifecycle, dispatch, reconciliation, settlement, or recovery engines.

Normative terms: The key words MUST, MUST NOT, SHALL, SHALL NOT, and REQUIRED are interpreted as RFC 2119/RFC 8174 terms only in NORMATIVE paragraphs.

## H1 - Schema Dialect

NORMATIVE:
- ESRM-H1-MUST-001: JSON Schemas MUST use Draft 2020-12.
- ESRM-H1-MUST-002: JSON Schemas MUST contain explicit `$schema` fields.
- ESRM-H1-MUST-003: JSON Schemas MUST contain stable `$id` fields.
- ESRM-H1-MUST-004: Governed artifact schemas MUST set `additionalProperties` to false.
- ESRM-H1-MUST-NOT-001: JSON Schema `format` assertions MUST NOT be normative for ESRM v0.1 conformance.
- ESRM-H1-MUST-NOT-002: Validators MUST NOT rely on library-specific `format` behavior for pass/fail decisions.

## H2 - Closed Registries

NORMATIVE:
- ESRM-H2-MUST-001: The artifact/domain registry MUST be closed.
- ESRM-H2-MUST-002: The registry MUST map `proofrail.transition` to `PROOFRAIL:TRANSITION:V1`.
- ESRM-H2-MUST-003: The registry MUST map `proofrail.signature` to `PROOFRAIL:SIGNATURE:V1`.
- ESRM-H2-MUST-004: The registry MUST reject lowercase descriptive domain substitutes.
- ESRM-H2-MUST-005: The rejection-stage and reason-code registry MUST be closed.

## H3 - Resource Limits

NORMATIVE:
- ESRM-H3-MUST-001: Raw artifact byte length MUST be no more than 1048576 bytes unless a later protocol revision changes the limit.
- ESRM-H3-MUST-002: JSON nesting depth MUST be no more than 64.
- ESRM-H3-MUST-003: Total parsed JSON node count MUST be no more than 100000.
- ESRM-H3-MUST-004: Any object member count MUST be no more than 1024.
- ESRM-H3-MUST-005: Any array length MUST be no more than 4096.
- ESRM-H3-MUST-006: Any string byte length after UTF-8 encoding MUST be no more than 65536.

## H4 - Requirement Inventory

NORMATIVE:
- ESRM-H4-MUST-001: Requirement inventory MUST be generated from `ESRM_PROTOCOL_SECTIONS_22_40.md` and `ESRM_CONFORMANCE_HARNESS_REQUIREMENTS.md`.
- ESRM-H4-MUST-002: Protocol requirements and harness requirements MUST have separate counts.
- ESRM-H4-MUST-003: A requirement inventory MUST record requirement ID, source document, exact section, exact normative sentence, enforcement stage, planned positive vector IDs, planned negative vector IDs, implementation track, and coverage status.
- ESRM-H4-MUST-NOT-001: A generated profile MUST NOT be the authority for its own coverage calculation.
- ESRM-H4-MUST-NOT-002: A harness requirement MUST NOT be counted as protocol semantic coverage.

## H5 - Binary Vector Planning

NORMATIVE:
- ESRM-H5-MUST-001: Until `.bin` files exist, the planning artifact MUST be named `binary-vector-plan.json`.
- ESRM-H5-MUST-002: `binary-vector-plan.json` MUST state that no executable binary vectors are populated.
- ESRM-H5-MUST-003: A future populated binary-vector manifest MUST enumerate actual `.bin` vector files.
- ESRM-H5-MUST-NOT-001: `binary-vector-plan.json` MUST NOT claim to be a populated binary-vector manifest.

## H6 - Deterministic Corpus Generation

NORMATIVE:
- ESRM-H6-MUST-001: The future corpus generator MUST declare generator name, generator version, PRNG, seed format, and case-order rules.
- ESRM-H6-MUST-002: The frozen generator name for this pack MUST be `proofrail-esrm-corpus-planner`.
- ESRM-H6-MUST-003: The frozen generator version for this pack MUST be `0.1-repair2-plan-only`.
- ESRM-H6-MUST-004: The frozen PRNG for future generated vector planning MUST be `HMAC-SHA256-DRBG` with seed encoded as lowercase hexadecimal bytes.
- ESRM-H6-MUST-005: Case ordering MUST be lexicographic by `vector_id`.
- ESRM-H6-MUST-NOT-001: Corpus planning MUST NOT depend on host time, process ID, local username, filesystem absolute paths, network state, or random device state after seed declaration.

## H7 - Validation Reproducibility

NORMATIVE:
- ESRM-H7-MUST-001: Every validation or inventory-generation command referenced by a manifest or report MUST correspond to a committed script.
- ESRM-H7-MUST-002: A clean checkout MUST provide one documented command that reproduces JSON parsing, schema meta-validation, instance validation, registry checks, requirement extraction, coverage calculation, and hash verification.
- ESRM-H7-MUST-003: Validation tooling MUST use repository files and Python standard library only for this artifact phase.
- ESRM-H7-MUST-NOT-001: Validation reports MUST NOT depend on uncommitted local packages.

## H8 - File Manifest and Release Root

NORMATIVE:
- ESRM-H8-MUST-001: The file-hash manifest MUST enumerate every governed file except itself.
- ESRM-H8-MUST-002: The file-hash manifest exclusion MUST be explicit.
- ESRM-H8-MUST-003: `file_hash_manifest_sha256` MUST be recorded separately from `release_root_record_sha256`.
- ESRM-H8-MUST-004: The release-root record MUST record the immutable git commit when known.
- ESRM-H8-MUST-NOT-001: A file-hash manifest MUST NOT claim to contain its own hash.
- ESRM-H8-MUST-NOT-002: The file-manifest hash MUST NOT be mislabeled as the release-root record hash.

## H9 - Dependency Independence

NORMATIVE:
- ESRM-H9-MUST-001: Future Rust and Go tracks MUST use independent parsing implementations.
- ESRM-H9-MUST-002: Future Rust and Go tracks MUST use independent RFC 8785 canonicalization implementations.
- ESRM-H9-MUST-003: Future Rust and Go tracks MUST use independent base64url implementations.
- ESRM-H9-MUST-004: Future Rust and Go tracks MUST use independent Ed25519 verification implementations.
- ESRM-H9-MUST-005: Future Rust and Go tracks MUST use independent JSON Schema validation implementations.
- ESRM-H9-MUST-006: Future Rust and Go tracks MUST use independent SHA-256 or commitment implementations.
- ESRM-H9-MUST-NOT-001: A Rust track MUST NOT call a Go validator for conformance decisions.
- ESRM-H9-MUST-NOT-002: A Go track MUST NOT call a Rust validator for conformance decisions.

## H10 - Implementation Gate

NORMATIVE:
- ESRM-H10-MUST-001: Rust implementation MUST NOT begin until the artifact pack passes independent file-by-file audit.
- ESRM-H10-MUST-002: Go implementation MUST NOT begin until the artifact pack passes independent file-by-file audit.
- ESRM-H10-MUST-003: Vector generation MUST NOT begin until the protocol and harness requirements are independently audited.
- ESRM-H10-MUST-NOT-001: The artifact phase MUST NOT claim conformance.
- ESRM-H10-MUST-NOT-002: The artifact phase MUST NOT implement lifecycle, dispatch, reconciliation, settlement, or recovery engines.

## H11 - Audit Findings

NORMATIVE:
- ESRM-H11-MUST-001: Repair 2 MUST record dispositions for `AUD-001` through `AUD-010`.
- ESRM-H11-MUST-002: `AUD-001` MUST remain a failed-evidence finding against Repair 1.
- ESRM-H11-MUST-003: Repair 2 MUST preserve Repair 1 commit `d405ca4dd5e0a766bbb1e9c1280742c51ebd3bd3` without rewriting it.
