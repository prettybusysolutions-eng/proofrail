# ProofRail ESRM v0.1 Canonical Baseline: Sections 22-48

Status: repository-authoritative artifact baseline for the ESRM raw-byte conformance laboratory. This document is created by Artifact Repair 1 so later coverage is generated from a repository artifact, not from a generated profile checking itself.

RFC 2119/8174 terms are normative only inside `NORMATIVE` subsections. `NON-NORMATIVE` subsections provide explanation only.

NO CLAIM OF CONFORMANCE. Rust and Go implementations have not begun.

## Section 22: Conformance Authority and Scope

### NORMATIVE

- ESRM-22-MUST-001: A conformance artifact pack MUST identify this document as the repository-authoritative ESRM v0.1 baseline for Sections 22 through 48.
- ESRM-22-MUST-002: A conformance artifact pack MUST distinguish NORMATIVE text from NON-NORMATIVE text.
- ESRM-22-MUST-NOT-001: A conformance artifact pack MUST NOT treat examples, rationale, or implementation notes as normative requirements.
- ESRM-22-MUST-NOT-002: A conformance artifact pack MUST NOT claim ESRM conformance before independent audit and before both Rust and Go implementations pass the finalized corpus.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 23: Raw Artifact Parsing

### NORMATIVE

- ESRM-23-MUST-001: An implementation MUST accept each artifact as an exact finite byte sequence before any decoding.
- ESRM-23-MUST-002: An implementation MUST record raw_byte_length before JSON parsing.
- ESRM-23-MUST-003: An implementation MUST record raw_sha256 as SHA-256 over the exact finite byte sequence.
- ESRM-23-MUST-NOT-001: An implementation MUST NOT normalize Unicode before raw_sha256 is recorded.
- ESRM-23-MUST-NOT-002: An implementation MUST NOT translate CRLF, CR, or LF before raw_sha256 is recorded.
- ESRM-23-MUST-NOT-003: An implementation MUST NOT infer a character encoding other than UTF-8.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 24: Lexical UTF-8 and JSON Intake

### NORMATIVE

- ESRM-24-MUST-001: After raw_sha256 is recorded, JSON artifacts MUST decode as valid UTF-8.
- ESRM-24-MUST-002: JSON artifacts MUST contain exactly one top-level JSON object.
- ESRM-24-MUST-003: JSON artifacts MUST reject duplicate object member names at every object depth.
- ESRM-24-MUST-NOT-001: JSON artifacts MUST NOT contain a UTF-8 BOM.
- ESRM-24-MUST-NOT-002: JSON artifacts MUST NOT contain leading whitespace before the top-level object.
- ESRM-24-MUST-NOT-003: JSON artifacts MUST NOT contain trailing bytes or trailing whitespace after the top-level object.
- ESRM-24-MUST-NOT-004: JSON artifacts MUST NOT use comments, trailing commas, NaN, Infinity, or implementation-specific JSON extensions.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 25: I-JSON and Numeric Profile

### NORMATIVE

- ESRM-25-MUST-001: JSON values MUST satisfy I-JSON constraints before JCS canonicalization.
- ESRM-25-MUST-002: Numeric values MUST be integers in the inclusive range 0 through 9007199254740991 unless a schema field explicitly forbids numbers entirely.
- ESRM-25-MUST-003: Numeric-profile enforcement MUST apply recursively inside extension containers.
- ESRM-25-MUST-NOT-001: JSON numbers MUST NOT be negative, fractional, exponential, NaN, or Infinity.
- ESRM-25-MUST-NOT-002: JSON strings MUST NOT contain unpaired surrogate code points.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 26: JCS Canonicalization

### NORMATIVE

- ESRM-26-MUST-001: Canonicalization MUST use RFC 8785 JSON Canonicalization Scheme after strict intake, I-JSON, schema, semantic, and numeric-profile checks.
- ESRM-26-MUST-002: Canonical bytes MUST be UTF-8 encoded RFC 8785 JCS output.
- ESRM-26-MUST-NOT-001: An implementation MUST NOT canonicalize invalid JSON or schema-invalid artifacts.
- ESRM-26-MUST-NOT-002: An implementation MUST NOT substitute local member-ordering, whitespace, or number-rendering behavior for RFC 8785 JCS.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 27: Domain Commitments

### NORMATIVE

- ESRM-27-MUST-001: Every governed artifact MUST declare artifact_type using the closed artifact-type registry.
- ESRM-27-MUST-002: Every governed artifact MUST declare domain using the closed domain registry.
- ESRM-27-MUST-003: Every governed artifact MUST include raw_sha256 and canonical_sha256 when the artifact is JSON-governed.
- ESRM-27-MUST-NOT-001: Registry values MUST NOT accept aliases, case variants, prefixes, or suffixes.
- ESRM-27-MUST-NOT-002: A domain commitment MUST NOT be inferred from file path, branch name, repository name, or caller identity.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 28: Closed Artifact Type and Domain Registry

### NORMATIVE

- ESRM-28-MUST-001: The artifact-type registry MUST be closed for ESRM v0.1.
- ESRM-28-MUST-002: The domain registry MUST be closed for ESRM v0.1.
- ESRM-28-MUST-003: The registry MUST define a bijection check between schema-governed artifact types and schema identifiers.
- ESRM-28-MUST-NOT-001: Implementations MUST NOT dynamically add artifact types or domains during conformance execution.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 29: Critical Extensions

### NORMATIVE

- ESRM-29-MUST-001: `critical_extensions` MUST be an array when present.
- ESRM-29-MUST-002: Each critical extension entry MUST contain `extension_id`, `extension_version`, `critical`, and `payload`.
- ESRM-29-MUST-003: `critical` MUST be true for every critical extension entry.
- ESRM-29-MUST-004: `extension_id` MUST match `^esrm\.[a-z0-9]+(?:[._-][a-z0-9]+)*$`.
- ESRM-29-MUST-005: An artifact MUST contain no more than 16 critical extension entries.
- ESRM-29-MUST-006: Each serialized critical extension payload MUST be no larger than 8192 bytes.
- ESRM-29-MUST-NOT-001: Unknown critical extension identifiers MUST NOT be ignored.
- ESRM-29-MUST-NOT-002: Extension containers MUST NOT bypass recursive numeric-profile enforcement.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 30: Raw Artifact Resource Limits

### NORMATIVE

- ESRM-30-MUST-001: A raw artifact MUST be no larger than 1048576 bytes.
- ESRM-30-MUST-002: A parsed JSON artifact MUST have maximum nesting depth no greater than 32.
- ESRM-30-MUST-003: A parsed JSON artifact MUST have no more than 4096 object members total.
- ESRM-30-MUST-004: A parsed JSON artifact MUST have no array longer than 1024 elements.
- ESRM-30-MUST-NOT-001: Implementations MUST NOT continue parsing after a resource limit is exceeded.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 31: Transition Artifact

### NORMATIVE

- ESRM-31-MUST-001: A `proofrail.transition` artifact MUST contain `transition_id`, `artifact_type`, `domain`, `schema_version`, `input_commitments`, `output_commitments`, `operation_label`, `raw_sha256`, and `canonical_sha256`.
- ESRM-31-MUST-002: `input_commitments` and `output_commitments` MUST contain unique commitment strings sorted by bytewise ASCII order.
- ESRM-31-MUST-003: `operation_label` MUST match `^esrm\.[a-z0-9]+(?:[._-][a-z0-9]+)*$`.
- ESRM-31-MUST-NOT-001: A transition artifact MUST NOT contain lifecycle-state fields in ESRM v0.1 canonical raw-byte conformance.
- ESRM-31-MUST-NOT-002: A transition artifact MUST NOT imply mutation of an input artifact.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 32: Signature Envelope

### NORMATIVE

- ESRM-32-MUST-001: A `proofrail.signature` artifact MUST bind exactly one `subject_canonical_sha256`.
- ESRM-32-MUST-002: The crypto suite MUST be `PR-ESRM-JCS-SHA256-ED25519-v1`.
- ESRM-32-MUST-003: Hash commitments MUST use SHA-256 encoded as exactly 64 lowercase hexadecimal characters.
- ESRM-32-MUST-004: Signature mode MUST be pure Ed25519 per RFC 8032.
- ESRM-32-MUST-005: `signature_b64u` MUST decode to exactly 64 bytes using unpadded base64url.
- ESRM-32-MUST-006: `public_key_b64u` MUST decode to exactly 32 bytes using unpadded base64url.
- ESRM-32-MUST-NOT-001: Permissive Base64 decoding MUST NOT be used.
- ESRM-32-MUST-NOT-002: Invalid point encodings and noncanonical signature scalars MUST be rejected.
- ESRM-32-MUST-NOT-003: Signature artifacts MUST NOT contain private keys, bearer tokens, cookies, or secret headers.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 33: Signature Versus Authority

### NORMATIVE

- ESRM-33-MUST-001: A signature artifact MUST prove only that the subject commitment was signed by the declared public key.
- ESRM-33-MUST-002: Authority to produce an external effect MUST require a separate authority artifact outside this raw-byte conformance phase.
- ESRM-33-MUST-NOT-001: A valid signature MUST NOT be treated as permission to execute an action.
- ESRM-33-MUST-NOT-002: A signature verifier MUST NOT choose an implicit trust root.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 34: Reconciliation Algebra

### NORMATIVE

- ESRM-34-MUST-001: Reconciliation claims MUST be represented as deterministic relations between input commitments and output commitments.
- ESRM-34-MUST-002: A reconciliation relation MUST preserve all input commitments.
- ESRM-34-MUST-NOT-001: Reconciliation MUST NOT erase, rewrite, or mutate a prior commitment.
- ESRM-34-MUST-NOT-002: Inconclusive reconciliation MUST NOT be reported as success.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 35: Consumption Irreversibility

### NORMATIVE

- ESRM-35-MUST-001: Consumption records MUST be append-only commitment records.
- ESRM-35-MUST-002: A consumed authority commitment MUST remain visible to later verification.
- ESRM-35-MUST-NOT-001: A consumed authority commitment MUST NOT be returned to an unconsumed state.
- ESRM-35-MUST-NOT-002: Replay of a consumed commitment MUST NOT be accepted as fresh authority.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 36: External-Effect Boundary

### NORMATIVE

- ESRM-36-MUST-001: External-effect claims MUST identify the exact boundary where local verification ends and external provider state begins.
- ESRM-36-MUST-002: Ambiguous external-effect outcomes MUST be recorded as ambiguous.
- ESRM-36-MUST-NOT-001: An implementation MUST NOT convert an ambiguous external outcome into success without independent observation.
- ESRM-36-MUST-NOT-002: Raw-byte conformance MUST NOT claim production exactly-once external execution.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 37: Conformance Interface

### NORMATIVE

- ESRM-37-MUST-001: A conformance implementation MUST expose independent parse, schema, semantic, canonicalization, signature, and commitment checks.
- ESRM-37-MUST-002: A conformance result MUST include rejection_stage and reason_code for every negative vector.
- ESRM-37-MUST-NOT-001: A conformance implementation MUST NOT hide parser failures behind a generic failure code.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 38: Rejection Precedence

### NORMATIVE

- ESRM-38-MUST-001: Rejection precedence MUST be deterministic.
- ESRM-38-MUST-002: Rejection precedence MUST be raw_byte_intake, resource_limit, utf8_decode, json_parse, duplicate_member, schema_validation, registry_lookup, semantic_validation, canonicalization, commitment_validation, signature_validation, claim_boundary.
- ESRM-38-MUST-NOT-001: Implementations MUST NOT report a later-stage rejection when an earlier-stage rejection applies.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 39: Corpus Requirements

### NORMATIVE

- ESRM-39-MUST-001: The corpus manifest MUST enumerate every vector file by relative path, raw byte length, and SHA-256.
- ESRM-39-MUST-002: Every vector MUST list the normative requirement IDs it covers.
- ESRM-39-MUST-003: Every negative vector MUST list expected rejection_stage and reason_code.
- ESRM-39-MUST-NOT-001: Vector files MUST NOT depend on absolute host paths, local usernames, environment variables, or wall-clock time.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 40: Deterministic Corpus Generation

### NORMATIVE

- ESRM-40-MUST-001: Generated corpus families MUST declare generator_id, generator_version, PRNG algorithm, seed, case ordering, and reproduction command.
- ESRM-40-MUST-002: The PRNG algorithm for generated ESRM v0.1 vectors MUST be ChaCha20 with a 256-bit seed encoded as 64 lowercase hex characters.
- ESRM-40-MUST-003: Case ordering MUST be lexicographic by vector_id after generation.
- ESRM-40-MUST-NOT-001: Corpus generation MUST NOT read host time, network state, process ID, or random device state after the declared seed is set.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 41: File-Manifest Anchoring

### NORMATIVE

- ESRM-41-MUST-001: The file-hash manifest MUST enumerate every governed file except itself.
- ESRM-41-MUST-002: The file-hash manifest exclusion MUST be explicit.
- ESRM-41-MUST-003: The file-hash manifest SHA-256 MUST be recorded in a separate release-root record or immutable git commit.
- ESRM-41-MUST-NOT-001: A file-hash manifest MUST NOT claim to contain its own hash unless a separate self-reference construction is specified.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 42: JSON Schema Dialect

### NORMATIVE

- ESRM-42-MUST-001: JSON Schemas MUST use Draft 2020-12.
- ESRM-42-MUST-002: JSON Schemas MUST contain explicit `$schema` and stable `$id` fields.
- ESRM-42-MUST-003: JSON Schemas MUST set `additionalProperties` to false for governed artifacts.
- ESRM-42-MUST-NOT-001: JSON Schema `format` assertions MUST NOT be normative for ESRM v0.1 conformance.
- ESRM-42-MUST-NOT-002: Implementations MUST NOT rely on validator-specific `format` behavior for pass/fail decisions.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 43: Rust and Go Dependency Independence

### NORMATIVE

- ESRM-43-MUST-001: Rust and Go tracks MUST use separate parsing implementations.
- ESRM-43-MUST-002: Rust and Go tracks MUST use separate JCS canonicalization implementations.
- ESRM-43-MUST-003: Rust and Go tracks MUST use separate base64url implementations.
- ESRM-43-MUST-004: Rust and Go tracks MUST use separate Ed25519 verification implementations.
- ESRM-43-MUST-005: Rust and Go tracks MUST use separate JSON Schema validation implementations.
- ESRM-43-MUST-006: Rust and Go tracks MUST use separate SHA-256 or commitment implementations.
- ESRM-43-MUST-NOT-001: A Rust track MUST NOT call a Go validator.
- ESRM-43-MUST-NOT-002: A Go track MUST NOT call a Rust validator.
- ESRM-43-MUST-NOT-003: Either track MUST NOT shell out to the other track for conformance decisions.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 44: Validation Result Semantics

### NORMATIVE

- ESRM-44-MUST-001: Validation output MUST distinguish parse validation, schema validation, semantic validation, canonicalization validation, signature validation, commitment validation, and end-to-end conformance.
- ESRM-44-MUST-002: Validation output MUST report uncovered requirements.
- ESRM-44-MUST-003: Validation output MUST report unresolved ambiguities.
- ESRM-44-MUST-NOT-001: Validation output MUST NOT claim conformance from artifact parse success alone.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 45: Release Gates

### NORMATIVE

- ESRM-45-MUST-001: Implementation work MUST NOT begin until this artifact pack has been independently audited.
- ESRM-45-MUST-002: A release candidate MUST include normative source, registries, schemas, coverage inventory, dependency report, risk register, validation results, file-hash manifest, and release-root record.
- ESRM-45-MUST-NOT-001: A release candidate MUST NOT merge without explicit operator direction.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 46: Deviation Reporting

### NORMATIVE

- ESRM-46-MUST-001: The artifact pack MUST record deviations from supplied ESRM language.
- ESRM-46-MUST-002: Missing source language MUST be reported as an unresolved evidence gap.
- ESRM-46-MUST-NOT-001: An implementation MUST NOT silently resolve a contradiction by local choice.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 47: Ambiguity Handling

### NORMATIVE

- ESRM-47-MUST-001: Every unresolved ambiguity MUST have a stable ambiguity ID.
- ESRM-47-MUST-002: Every ambiguity record MUST list affected vector families.
- ESRM-47-MUST-003: Affected vector families MUST be stopped when implementation would require inventing protocol semantics.
- ESRM-47-MUST-NOT-001: A stopped vector family MUST NOT be counted as passed conformance.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.

## Section 48: Claim Boundary

### NORMATIVE

- ESRM-48-MUST-001: This phase MUST state `NO CLAIM OF CONFORMANCE` in its validation summary.
- ESRM-48-MUST-002: This phase MUST state that Rust and Go implementations have not begun.
- ESRM-48-MUST-NOT-001: This phase MUST NOT claim lifecycle, dispatch, reconciliation, settlement, or recovery engine behavior.

### NON-NORMATIVE

This section explains the requirement boundary and supplies no additional normative force.
