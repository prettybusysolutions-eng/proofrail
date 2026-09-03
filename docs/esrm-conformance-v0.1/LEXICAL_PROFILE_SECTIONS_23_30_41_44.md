# ProofRail ESRM v0.1 Raw-Byte Lexical Profile

Status: normative draft for conformance-lab construction only. This document does not claim ESRM conformance and does not implement any lifecycle kernel, dispatch engine, reconciliation engine, settlement engine, or recovery engine.

Scope: Sections 23-30 and 41-44 as referenced by the ESRM conformance mission. The repository does not currently contain the authoritative ESRM section text. Requirements below are therefore a closed lexical profile for test-lab artifacts, while ambiguities caused by missing authoritative section prose are recorded in `manifests/esrm-risk-register.v0.1.json` and affected vector families are stopped.

## Normative Requirements

- ESRM-LP-23-MUST-001: A conformance implementation MUST treat input artifacts as raw bytes before interpreting them as text.
- ESRM-LP-23-MUST-002: A conformance implementation MUST reject input that requires implicit character-set detection.
- ESRM-LP-23-MUST-NOT-001: A conformance implementation MUST NOT normalize Unicode before recording the raw input digest.
- ESRM-LP-23-MUST-NOT-002: A conformance implementation MUST NOT translate CRLF, CR, or LF before recording the raw input digest.
- ESRM-LP-24-MUST-001: Every artifact under test MUST have a SHA-256 digest over exact raw bytes.
- ESRM-LP-24-MUST-002: Digest fields MUST be lowercase hex and exactly 64 characters.
- ESRM-LP-24-MUST-NOT-001: A digest MUST NOT be computed over decoded text when raw bytes are available.
- ESRM-LP-24-MUST-NOT-002: A digest MUST NOT be accepted if missing, malformed, uppercase, truncated, or overlong.
- ESRM-LP-25-MUST-001: JSON artifact envelopes MUST declare `artifact_type` using the closed artifact-type registry.
- ESRM-LP-25-MUST-002: JSON artifact envelopes MUST declare `domain` using the closed domain registry.
- ESRM-LP-25-MUST-003: JSON artifact envelopes MUST declare `schema_version` as `esrm.v0.1`.
- ESRM-LP-25-MUST-NOT-001: JSON artifact envelopes MUST NOT contain unregistered artifact types or domains.
- ESRM-LP-25-MUST-NOT-002: JSON artifact envelopes MUST NOT accept aliases, case variants, or prefixed forms for registry values.
- ESRM-LP-26-MUST-001: `proofrail.transition` artifacts MUST include `transition_id`, `from_state`, `to_state`, `input_artifact_digests`, `output_artifact_digests`, `rejection_stage`, and `reason_code`.
- ESRM-LP-26-MUST-002: `input_artifact_digests` and `output_artifact_digests` MUST be arrays of unique SHA-256 digest strings.
- ESRM-LP-26-MUST-003: Digest arrays MUST be lexicographically sorted by bytewise ASCII order.
- ESRM-LP-26-MUST-NOT-001: A transition MUST NOT imply mutation of any prior artifact.
- ESRM-LP-26-MUST-NOT-002: A transition MUST NOT use a reason code outside the closed reason-code registry.
- ESRM-LP-27-MUST-001: `proofrail.signature` artifacts MUST bind exactly one `subject_digest`.
- ESRM-LP-27-MUST-002: `signature_algorithm` MUST be selected from the closed registry.
- ESRM-LP-27-MUST-003: `public_key_fingerprint` MUST be a lowercase 64-character SHA-256 hex string.
- ESRM-LP-27-MUST-NOT-001: Signature artifacts MUST NOT embed private keys, bearer tokens, cookies, or secret headers.
- ESRM-LP-27-MUST-NOT-002: Signature artifacts MUST NOT verify against an implementation-selected trust root unless that trust root is represented as an explicit input artifact digest.
- ESRM-LP-28-MUST-001: Binary payload fields represented as Base64 MUST use the single Base64 alphabet selected by the registry.
- ESRM-LP-28-MUST-002: Base64 strings MUST be padded if the selected alphabet requires padding.
- ESRM-LP-28-MUST-NOT-001: Base64 parsers MUST NOT accept whitespace inside encoded values.
- ESRM-LP-28-MUST-NOT-002: Base64 parsers MUST NOT accept mixed standard/base64url alphabets in the same field.
- ESRM-LP-29-MUST-001: JSON objects MUST reject duplicate member names.
- ESRM-LP-29-MUST-002: JSON strings MUST be valid UTF-8 after raw-byte digest capture.
- ESRM-LP-29-MUST-NOT-001: Parsers MUST NOT accept comments, trailing commas, NaN, Infinity, or implementation-specific JSON extensions.
- ESRM-LP-29-MUST-NOT-002: Parsers MUST NOT silently coerce strings, numbers, booleans, arrays, or objects across expected types.
- ESRM-LP-30-MUST-001: A conformance vector MUST declare whether it tests raw-byte identity, JSON parse validity, schema validity, canonicalization, signature verification, or commitment binding.
- ESRM-LP-30-MUST-002: A vector family depending on unresolved canonicalization rules MUST be marked `stopped_by_ambiguity`.
- ESRM-LP-30-MUST-NOT-001: Implementations MUST NOT substitute local canonicalization behavior for unresolved ESRM canonicalization text.
- ESRM-LP-41-MUST-001: Every negative vector MUST name an expected `rejection_stage` from the closed registry.
- ESRM-LP-41-MUST-002: Every negative vector MUST name an expected `reason_code` from the closed registry.
- ESRM-LP-41-MUST-NOT-001: Rejection reports MUST NOT expose credentials, secret headers, or raw private key material.
- ESRM-LP-42-MUST-001: Every binary vector MUST be described by the binary-vector manifest schema.
- ESRM-LP-42-MUST-002: Every vector MUST declare raw byte length and SHA-256 digest.
- ESRM-LP-42-MUST-NOT-001: A vector MUST NOT depend on host filesystem paths, local usernames, environment variables, or wall-clock time.
- ESRM-LP-43-MUST-001: Rust and Go tracks MUST use independent parsers, canonicalizers, Base64 codecs, signature libraries, schema validators, and commitment/digest implementations.
- ESRM-LP-43-MUST-002: Shared test vectors MAY be consumed by both tracks, but no parsing or validation implementation may be shared.
- ESRM-LP-43-MUST-NOT-001: A Rust track MUST NOT call a Go validator, and a Go track MUST NOT call a Rust validator.
- ESRM-LP-44-MUST-001: The lab MUST distinguish parse validation, schema validation, signature validation, commitment validation, and end-to-end conformance.
- ESRM-LP-44-MUST-002: The lab MUST report uncovered requirements and unresolved ambiguities.
- ESRM-LP-44-MUST-NOT-001: The lab MUST NOT claim ESRM conformance before independent audit and before both Rust and Go implementations pass the finalized vector corpus.
