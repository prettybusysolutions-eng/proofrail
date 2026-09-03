# ESRM Protocol Sections 22-40

Status: repository audit artifact for ProofRail ESRM v0.1 canonical conformance. This document preserves the supplied protocol shape and records missing supplied wording as an audit gap. It is not an implementation specification for Rust or Go.

Normative terms: The key words MUST, MUST NOT, SHALL, SHALL NOT, and REQUIRED are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals in NORMATIVE paragraphs.

## Section 22 - Signature Does Not Confer Authority

NORMATIVE:
- ESRM-P22-MUST-001: A signature verification result MUST mean only that a signature was produced by the private key corresponding to the resolved public key over the defined signature input.
- ESRM-P22-MUST-002: A valid signature result MUST produce the state `ATTESTED` and MUST NOT produce the state `AUTHORIZED`.
- ESRM-P22-MUST-003: Authorization MUST be derived from a separate authority input, policy input, or governance decision outside the signature envelope.
- ESRM-P22-MUST-NOT-001: A verifier MUST NOT treat possession of a signing key as authority to perform, approve, dispatch, settle, reconcile, or recover an external effect.
- ESRM-P22-MUST-NOT-002: A signature envelope MUST NOT embed a public key as the source of authority; key identity MUST resolve through a separate key-status or key-registry input.

NON-NORMATIVE:
- The supplied Section 22 title is preserved exactly as `Signature Does Not Confer Authority`. Repair 1 changed this numbering and is rejected by `AUD-001`.

## Section 23 - Raw Artifact Intake

NORMATIVE:
- ESRM-P23-MUST-001: A verifier MUST receive each artifact as an exact finite byte sequence before text decoding or JSON parsing.
- ESRM-P23-MUST-002: A verifier MUST record diagnostic `raw_byte_length` outside the subject artifact.
- ESRM-P23-MUST-003: A verifier MUST record diagnostic `raw_sha256` outside the subject artifact as SHA-256 over the exact raw byte sequence.
- ESRM-P23-MUST-NOT-001: A verifier MUST NOT require, accept, or trust a subject artifact field that claims to contain the artifact's own raw byte hash.
- ESRM-P23-MUST-NOT-002: A verifier MUST NOT normalize Unicode, line endings, or character encodings before raw-byte diagnostics are recorded.

NON-NORMATIVE:
- Diagnostic hashes are observations made by the conformance verifier, not protocol fields inside the artifact being measured.

## Section 24 - JSON Text Intake

NORMATIVE:
- ESRM-P24-MUST-001: JSON artifacts MUST be UTF-8 after raw-byte diagnostics are recorded.
- ESRM-P24-MUST-002: JSON artifacts MUST contain exactly one top-level JSON object.
- ESRM-P24-MUST-003: JSON object member names MUST be unique at every object depth.
- ESRM-P24-MUST-NOT-001: JSON artifacts MUST NOT begin with a UTF-8 BOM.
- ESRM-P24-MUST-NOT-002: JSON artifacts MUST NOT contain leading whitespace before the top-level object.
- ESRM-P24-MUST-NOT-003: JSON artifacts MUST NOT contain trailing whitespace or trailing bytes after the top-level object.
- ESRM-P24-MUST-NOT-004: JSON artifacts MUST NOT use comments, trailing commas, NaN, Infinity, or implementation-specific JSON extensions.

## Section 25 - ESRM Strict Intake and Numeric Profile

NORMATIVE:
- ESRM-P25-MUST-001: A verifier MUST apply strict intake checks before RFC 8785 JSON Canonicalization Scheme.
- ESRM-P25-MUST-002: JSON values MUST satisfy I-JSON constraints before canonicalization.
- ESRM-P25-MUST-003: Numeric values MUST be integers in the inclusive range 0 through 9007199254740991 unless a field schema forbids numbers entirely.
- ESRM-P25-MUST-004: Numeric-profile enforcement MUST apply recursively inside `critical_extensions` and `noncritical_extensions`.
- ESRM-P25-MUST-NOT-001: JSON numbers MUST NOT be negative, fractional, exponential, NaN, or Infinity.
- ESRM-P25-MUST-NOT-002: JSON strings MUST NOT contain unpaired surrogate code points.

## Section 26 - Canonicalization

NORMATIVE:
- ESRM-P26-MUST-001: Canonicalization MUST use RFC 8785 JSON Canonicalization Scheme after strict intake, I-JSON, schema, semantic, and numeric-profile checks.
- ESRM-P26-MUST-002: Canonical bytes `B_x` MUST be defined as `UTF8(RFC8785Canonicalize(x))`.
- ESRM-P26-MUST-003: A verifier MUST record diagnostic `canonical_bytes_hex` outside the subject artifact.
- ESRM-P26-MUST-004: A verifier MUST record diagnostic `canonical_sha256` outside the subject artifact as SHA-256 over `B_x`.
- ESRM-P26-MUST-NOT-001: A verifier MUST NOT require, accept, or trust a subject artifact field that claims to contain the artifact's own canonical hash.
- ESRM-P26-MUST-NOT-002: A verifier MUST NOT substitute local member ordering, whitespace, or number rendering for RFC 8785 JCS.

## Section 27 - Registered Domains and Commitments

NORMATIVE:
- ESRM-P27-MUST-001: Every governed artifact MUST declare `artifact_type` using the closed artifact-type registry.
- ESRM-P27-MUST-002: A verifier MUST derive the registered domain from the closed registry using the artifact type.
- ESRM-P27-MUST-003: Artifact-supplied values MUST never determine the registered domain.
- ESRM-P27-MUST-004: Domain commitment `C_x` MUST be defined as `SHA256(ASCII(RegisteredDomain(artifact_type)) || 0x00 || B_x)`.
- ESRM-P27-MUST-005: Domain commitment encoding MUST be exactly 64 lowercase hexadecimal characters.
- ESRM-P27-MUST-NOT-001: Registry values MUST NOT accept aliases, case variants, prefixes, suffixes, or lowercase descriptive substitutes.
- ESRM-P27-MUST-NOT-002: A verifier MUST NOT replace the domain-separated commitment with an ordinary raw-byte or canonical-byte hash.

## Section 28 - Mandatory Governed Artifact Header

NORMATIVE:
- ESRM-P28-MUST-001: Every governed security artifact MUST require `artifact_type`.
- ESRM-P28-MUST-002: Every governed security artifact MUST require `protocol_version`.
- ESRM-P28-MUST-003: Every governed security artifact MUST require `crypto_suite`.
- ESRM-P28-MUST-004: Every governed security artifact MUST require `critical_extensions`.
- ESRM-P28-MUST-005: Every governed security artifact MUST require `noncritical_extensions`.
- ESRM-P28-MUST-006: `critical_extensions` MUST be an array of extension entries.
- ESRM-P28-MUST-007: `noncritical_extensions` MUST be an array of extension entries.
- ESRM-P28-MUST-NOT-001: Governed artifact schemas MUST NOT make mandatory header fields optional.

## Section 29 - Critical and Noncritical Extensions

NORMATIVE:
- ESRM-P29-MUST-001: Each extension entry MUST contain `extension_id` and `value`.
- ESRM-P29-MUST-002: `extension_id` MUST match `^[A-Z][A-Z0-9]*(?::[A-Z][A-Z0-9]*)*:V[0-9]+$`.
- ESRM-P29-MUST-003: An artifact MUST contain no more than 16 critical extension entries.
- ESRM-P29-MUST-004: An artifact MUST contain no more than 64 noncritical extension entries.
- ESRM-P29-MUST-005: Each serialized extension entry MUST be no more than 8192 bytes after JCS canonicalization.
- ESRM-P29-MUST-NOT-001: A verifier MUST NOT ignore an unsupported critical extension.
- ESRM-P29-MUST-NOT-002: Extension values MUST NOT contain values that violate the recursive numeric profile.

## Section 30 - Crypto Suite and Encodings

NORMATIVE:
- ESRM-P30-MUST-001: The ESRM v0.1 crypto suite MUST be `PR-ESRM-JCS-SHA256-ED25519-v1`.
- ESRM-P30-MUST-002: Hashing MUST use SHA-256.
- ESRM-P30-MUST-003: Signature verification MUST use pure Ed25519 per RFC 8032.
- ESRM-P30-MUST-004: Signature encoding MUST be unpadded base64url that decodes to exactly 64 bytes.
- ESRM-P30-MUST-005: Public-key encoding in key registries MUST be unpadded base64url that decodes to exactly 32 raw Ed25519 public-key bytes.
- ESRM-P30-MUST-006: Verifiers MUST reject invalid Ed25519 point encodings and noncanonical signature scalar values.
- ESRM-P30-MUST-NOT-001: Verifiers MUST NOT accept permissive Base64 decoding, padding, whitespace, mixed alphabets, or alternative alphabets for ESRM signature and public-key encodings.

## Section 31 - Canonical Transition Package

NORMATIVE:
- ESRM-P31-MUST-001: A `proofrail.transition` artifact MUST contain `artifact_type` equal to `proofrail.transition`.
- ESRM-P31-MUST-002: A `proofrail.transition` artifact MUST contain `protocol_version`.
- ESRM-P31-MUST-003: A `proofrail.transition` artifact MUST contain `crypto_suite`.
- ESRM-P31-MUST-004: A `proofrail.transition` artifact MUST contain `transition_id`.
- ESRM-P31-MUST-005: A `proofrail.transition` artifact MUST contain `nonce`.
- ESRM-P31-MUST-006: A `proofrail.transition` artifact MUST contain `epoch`.
- ESRM-P31-MUST-007: A `proofrail.transition` artifact MUST contain `pre_state`.
- ESRM-P31-MUST-008: A `proofrail.transition` artifact MUST contain `rules`.
- ESRM-P31-MUST-009: A `proofrail.transition` artifact MUST contain `authority`.
- ESRM-P31-MUST-010: A `proofrail.transition` artifact MUST contain `transition`.
- ESRM-P31-MUST-011: A `proofrail.transition` artifact MUST contain `execution`.
- ESRM-P31-MUST-012: A `proofrail.transition` artifact MUST contain `settlement`.
- ESRM-P31-MUST-013: A `proofrail.transition` artifact MUST contain `critical_extensions`.
- ESRM-P31-MUST-014: A `proofrail.transition` artifact MUST contain `noncritical_extensions`.
- ESRM-P31-MUST-NOT-001: A transition schema MUST NOT substitute `operation_label`, `input_commitments`, or `output_commitments` for the supplied canonical transition package.
- ESRM-P31-MUST-NOT-002: A transition artifact MUST NOT contain self-referential `raw_sha256` or `canonical_sha256` fields.

## Section 32 - Signature Envelope

NORMATIVE:
- ESRM-P32-MUST-001: Unsigned signature envelope `E_tau` MUST contain exactly `artifact_type`, `protocol_version`, `crypto_suite`, `signed_artifact_type`, `signed_artifact_domain`, `signed_commitment`, `signer_id`, `key_id`, `critical_extensions`, and `noncritical_extensions`.
- ESRM-P32-MUST-002: The transmitted `proofrail.signature` object MUST add exactly the `signature` field to `E_tau`.
- ESRM-P32-MUST-003: The signature input MUST be `ASCII("PROOFRAIL:SIGNATURE:V1") || 0x00 || UTF8(JCS(E_tau))`.
- ESRM-P32-MUST-004: `signed_artifact_domain` MUST equal the closed registry domain for `signed_artifact_type`.
- ESRM-P32-MUST-005: `signed_commitment` MUST be the domain-separated commitment of the signed artifact.
- ESRM-P32-MUST-NOT-001: A signature envelope MUST NOT embed the public key.
- ESRM-P32-MUST-NOT-002: A signature envelope MUST NOT omit `signer_id`, `key_id`, `signed_artifact_type`, or `signed_artifact_domain`.

## Section 33 - Key Registry and Key Status

NORMATIVE:
- ESRM-P33-MUST-001: `key_id` MUST resolve through a separate key-registry or key-status input.
- ESRM-P33-MUST-002: The key-registry public key representation MUST be exactly 32 raw Ed25519 bytes encoded as unpadded base64url.
- ESRM-P33-MUST-003: Signature verification MUST fail closed when `key_id` is unknown, revoked, malformed, or incompatible with the declared crypto suite.
- ESRM-P33-MUST-NOT-001: A verifier MUST NOT use a public key supplied inside the signature envelope as the trust root.

## Section 34 - Signature Versus Authority

NORMATIVE:
- ESRM-P34-MUST-001: A valid signature over a valid envelope MUST produce `ATTESTED` only.
- ESRM-P34-MUST-002: Authority evaluation MUST consume separate authority material and MUST be distinguishable from signature verification.
- ESRM-P34-MUST-NOT-001: A verifier MUST NOT conflate `ATTESTED` with authorization to execute external effects.

## Section 35 - Reconciliation Algebra

NORMATIVE:
- ESRM-P35-MUST-001: Reconciliation inputs and outputs MUST be content-addressed by domain-separated commitments.
- ESRM-P35-MUST-002: Reconciliation rules MUST be append-only over prior commitments.
- ESRM-P35-MUST-NOT-001: Reconciliation MUST NOT mutate or replace prior committed artifacts.

## Section 36 - Consumption Irreversibility

NORMATIVE:
- ESRM-P36-MUST-001: Consumption of authority or settlement capacity MUST be represented as an irreversible transition over committed inputs.
- ESRM-P36-MUST-NOT-001: A consumed authority unit MUST NOT be reused by another transition.

## Section 37 - External-Effect Boundary

NORMATIVE:
- ESRM-P37-MUST-001: External effects MUST be outside raw canonicalization conformance unless represented as committed observations.
- ESRM-P37-MUST-002: A conformance lab MUST distinguish artifact verification from dispatch or execution.
- ESRM-P37-MUST-NOT-001: Passing artifact verification MUST NOT imply that an external effect occurred or was authorized.

## Section 38 - Conformance Interface

NORMATIVE:
- ESRM-P38-MUST-001: A conformance result MUST include `raw_byte_length`, `raw_sha256`, `canonical_bytes_hex`, `canonical_sha256`, and `domain_commitment` as verifier observations when applicable.
- ESRM-P38-MUST-002: A conformance result MUST identify the rejection stage and reason code for rejected artifacts.
- ESRM-P38-MUST-NOT-001: A conformance result MUST NOT be embedded in the subject artifact whose bytes it measures.

## Section 39 - Binary Vector Corpus

NORMATIVE:
- ESRM-P39-MUST-001: A populated binary-vector manifest MUST enumerate actual `.bin` files.
- ESRM-P39-MUST-002: Each binary vector entry MUST contain `vector_id`.
- ESRM-P39-MUST-003: Each binary vector entry MUST contain `relative_path`.
- ESRM-P39-MUST-004: Each binary vector entry MUST contain `raw_byte_length`.
- ESRM-P39-MUST-005: Each binary vector entry MUST contain `raw_sha256`.
- ESRM-P39-MUST-006: Each binary vector entry MUST contain `expected_status`.
- ESRM-P39-MUST-007: Accepted vectors MUST contain `expected_canonical_bytes_hex`, `expected_canonical_sha256`, `expected_domain_commitment`, and `expected_signature_result`.
- ESRM-P39-MUST-008: Rejected vectors MUST contain `expected_rejection_stage` and `expected_reason_code`.
- ESRM-P39-MUST-NOT-001: A requirement-planning inventory MUST NOT be called a populated binary-vector manifest.

## Section 40 - Rejection Precedence

NORMATIVE:
- ESRM-P40-MUST-001: Rejection precedence MUST be deterministic.
- ESRM-P40-MUST-002: Rejection stages MUST be selected from the closed rejection-stage registry.
- ESRM-P40-MUST-003: Reason codes MUST be selected from the closed reason-code registry.
- ESRM-P40-MUST-004: Earlier rejection stages MUST take precedence over later stages when multiple failures are present.
- ESRM-P40-MUST-NOT-001: A verifier MUST NOT report implementation-specific or nondeterministic rejection reasons for ESRM-governed vectors.

## Missing Supplied Text Boundary

NORMATIVE:
- ESRM-P00-MUST-001: Any supplied Section 22-40 sentence not present in this repository document MUST remain an unresolved audit gap until inserted verbatim or adjudicated by an independent protocol owner.
- ESRM-P00-MUST-NOT-001: Implementations MUST NOT begin from this document until independent audit confirms that the supplied Sections 22-40 semantics are preserved.
