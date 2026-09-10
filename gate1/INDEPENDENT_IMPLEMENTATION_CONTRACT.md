# Gate 1 Independent Implementation Contract

Status: REVIEW CONTRACT — NO CONFORMANCE CLAIM

The purpose of two verifier tracks is to expose shared misunderstandings and implementation-specific ambiguity. Two programs that share security-critical code are not independent evidence.

## Planned tracks

- Track R: Rust verifier
- Track G: Go verifier

The language choice is not normative. Independence is.

## Inputs both tracks may share

Both tracks may consume identical immutable copies of:

1. the frozen Repair 4 source;
2. audited protocol-domain and reason registries;
3. reviewed Gate 1 rule IDs/source mappings;
4. audited conformance vector input bytes when a later gate authorizes vector generation; and
5. one implementation-independent expected-result manifest.

These shared inputs are evidence, not executable security logic.

## Security-critical components that MUST be independent

The tracks must not share source code, libraries written specifically for the other track, generated parser code from one implementation, or copy-pasted algorithms for:

- raw-byte framing and resource-limit validation;
- UTF-8 and Unicode lexical checks;
- duplicate JSON property detection;
- numeric-token lexical validation;
- timestamp lexical/calendar validation;
- JSON schema/intake enforcement glue;
- RFC8785/JCS canonicalization implementation;
- base64url strict decoding/re-encoding logic;
- domain-separated commitment construction;
- SHA-256 plumbing specific to ESRM commitment formation;
- Ed25519 signature-envelope reconstruction and verification glue;
- key-status and authority-derivation validation;
- reconciliation algebra;
- consumption/replay state transitions;
- dispatch/crossing state machine;
- target-capability validation;
- recovery/idempotency state machine; and
- settlement completeness evaluation.

Using mature general-purpose language ecosystem cryptographic primitives is allowed. Sharing a ProofRail-specific wrapper or verifier implementation is not.

## Development separation

Each track must maintain:

- a separate source tree;
- a separate dependency manifest;
- a separate parser/canonicalizer selection rationale;
- a separate test runner;
- a separate implementation notes file recording ambiguities encountered; and
- a machine-readable result file keyed only by vector/case ID and result vocabulary.

A failure in one track must not be fixed by porting the other track's implementation. The source text and expected-result contract must be revisited first.

## Cross-implementation comparison

For every future vector V:

```text
Expected(V) = Rust(V) = Go(V)
```

is necessary but not sufficient for conformance.

If Rust(V) != Go(V), Gate progression stops until the disagreement is traced to:

- source ambiguity;
- vector construction error;
- expected-result error;
- implementation defect; or
- an unstated dependency/host-language behavior.

The resolution must be documented without rewriting historical result files.

## Negative independence test

The review should be able to remove Track R entirely and still build/run Track G from the frozen source plus shared evidence inputs, and vice versa.

If either track requires executable output from the other, the independence claim fails.

## Claim boundary

Passing the same corpus in two languages does not prove the protocol safe, adopted, production-ready, or formally verified. It demonstrates cross-implementation agreement over the tested ESRM surface only.