# ESRM Repair 4 Source-to-Architecture Traceability

Status: NON-NORMATIVE TRACEABILITY INDEX

Purpose: map the architecture invariants and implementation boundaries back to the frozen Repair 4 source. This file does not create protocol requirements. It makes derivation auditable.

Canonical source used by this index:

`esrm-conformance/v0.1-repair4/docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md`

## Traceability Matrix

| Repair 4 section | Frozen concern | Architecture mapping | Implementation consequence |
| --- | --- | --- | --- |
| 22 — Signature Does Not Confer Authority | signature attribution is not authorization | `K-AUTH-002`; Fundamental Separation | verifier must validate key/status/lineage/scope/state after signature verification; no `signature_valid -> authorized` shortcut |
| 23 — Exact Commitment Encoding | domain-separated RFC8785/SHA-256 commitment construction and exact lowercase encoding | `K-DATA-003` | independent implementations must compute identical bytes/commitments and reject alternate lexical encodings |
| 24 — Registered Artifact Domains | closed, version-specific security domains; artifact cannot select verification domain | `K-DATA-002` | verifier derives expected domain from closed registry; unknown or mismatched domains fail closed |
| 25 — Signature Envelope | exact signature envelope semantics; Base64url canonicality; signature establishes ATTESTED only | `K-AUTH-002`, `K-DATA-001`, `K-DATA-003` | reconstruct envelope only after closed-schema validation; strict length/alphabet/re-encode checks; no external metadata reconstruction |
| 26 — Strict JSON Intake Pipeline | raw-byte and lexical validation before host-language object semantics | `K-DATA-001` | duplicate keys, invalid UTF-8, BOM, comments, trailing commas, multiple roots, alternate numeric/JSON extensions rejected before canonicalization/signature result |
| 27 — Unicode Profile | no Unicode normalization/case folding; exact canonical ordering semantics | `K-DATA-003` | independent parsers must preserve cryptographic distinction of differently encoded strings and use RFC8785 ordering |
| 28 — Numeric Profile | security-critical JSON numbers are restricted nonnegative integer tokens within safe range | `K-DATA-003` | lexical validation must run before host numeric conversion; signed/large/decimal quantities use registered string grammars |
| 29 — Timestamp Profile | narrow UTC timestamp grammar and explicit separation of logical order from wall clock | `K-DATA-003`, control-plane versioning | generic `date-time` validation is insufficient; logical epoch/counter drives deterministic ordering where required |
| 30 — Mandatory Artifact Header | mandatory artifact type/version/crypto/extension header; no uncommitted security semantics | `K-DATA-005`, `K-DATA-002` | new ESRM schemas must include frozen header and empty extensions until registry semantics change; legacy envelope is not silently upgraded |
| 31 — Precise Reconciliation Result Algebra | exact four-way `MATCH/DIVERGED/INSUFFICIENT/UNRESOLVED`; later evidence is append-only | `K-OBS-003`, `K-OBS-004`, `K-OBS-005` | runtime/UI error states must remain separate; timeout cannot be mapped to divergence; later evidence creates new epoch/artifact |
| 32 — Closed-World Absence Rule | absence requires authoritative closed-world coverage | `K-OBS-002` | negative provider query does not prove non-occurrence unless observation profile commits authoritative coverage for domain/interval |
| 33 — Consumption Irreversibility | consumed authority never becomes reusable; non-occurrence can justify new authority only | `K-AUTH-003`, `K-AUTH-004` | replay registry is monotonic; provider rejection/crash/recovery cannot roll consumption backward |
| 34 — Crash-Safe Dispatch Boundary | consumption is not external effect; durable crossing semantics; uncertainty preserved | `K-EFFECT-001`, `K-EFFECT-002`, `K-REC-001` | consumption + crossing durability precede release; crash after crossing without evidence produces UNKNOWN and forbids silent authority restoration |
| 35 — Dispatch Intent Artifact | immutable prepared-attempt artifact with transition/consumption/executor/target/effect bindings | execution-plane component model | dispatch manager must emit distinct intent artifact; intent cannot establish transmission/effect/settlement |
| 36 — Boundary-Crossing Artifact | crossing proves only capability to cross protected boundary | `K-EFFECT-002`, `K-REC-001` | crossing and transport/effect are separately recorded; post-crash ambiguity is legitimate protocol state |
| 37 — External Target Capability Evidence | adapter recovery class requires committed evidence; defined capability classes | `K-EFFECT-005` | adapter metadata cannot self-authorize retry; capability evidence is version/scope-bound and frozen for the transition |
| 38 — Recovery Function | occurred/non-occurrence/idempotency evidence determine legal recovery | `K-REC-002`, `K-REC-003`, `K-REC-004` | recovery is explicit; same-effect retransmission permitted only under verified durable idempotency; otherwise new transition/authority or unresolved |
| 39 — Transport Attempt Versus Semantic Transition | transport attempts and semantic effects are distinct; retries may be new potential effects | `K-EFFECT-004`, `K-REC-003` | stable effect identity is mandatory for retry reasoning; executor acknowledgement is not semantic-effect proof |
| 40 — Canonical Baseline Safety Claim | no universal exactly-once claim; unknown effect stays unknown; epistemic roles remain distinct | Fundamental Separation, `K-EFFECT-003`, `K-REC-001`, Architectural Acceptance Test | top-level product/architecture claim must remain narrower than exactly-once; settlement requires distinguishable evidence chain |

## Artifact/Role Derivation

Repair 4 Section 24 freezes initial security domains for:

```text
STATE
RULESET
AUTHORITY
ADMISSION
CONSUMPTION
TRANSITION
DISPATCH-INTENT
DISPATCH-CROSSING
OBSERVATION
RECONCILIATION
SETTLEMENT
RECOVERY
REVOCATION
KEY-STATUS
SIGNATURE
```

Section 40 additionally requires settlement to preserve independently distinguishable committed roles for:

```text
State
Derivation
Authority
Admission
Consumption
Dispatch
Observation
Reconciliation
Settlement
```

Architectural consequence: a future artifact registry must not assume that every semantic role necessarily maps one-to-one to one wire artifact/domain. Where Repair 4 has not frozen that mapping, the implementation must preserve the distinction without inventing a normative schema.

## Legacy Conflict Cross-References

| Conflict | Repair 4 source |
| --- | --- |
| `C-001` reconciliation collapsed into `RECONCILIATION_FAILED` | §31, §40 |
| `C-002` generic idempotency requirement | §37–§39 |
| `C-003` all retry forced to new authority | §33, §38–§39 |
| `C-004` ambiguous outcome encoded as runtime failure | §31, §34, §36, §40 |
| `C-005` legacy envelope header differs from ESRM mandatory header | §24–§25, §30 |
| `C-006` generic date-time profile | §29 |
| `C-007` coarse legacy dispatch state | §34–§36 |
| `C-008` GitHub-specific reconciliation semantics in universal state machine | §31–§32, §40 |
| `C-009` public claims remain narrower than architecture | §40 safety claim and current evidence boundaries |
| `C-010` architecture must not become protocol by documentation | Repair 4 source-lock status + §40 no-claim boundary |

## Test-Family Derivation

The conformance program should derive these test families directly from source:

```text
§22      authority-confusion tests
§23–25   commitment/domain/signature canonicality tests
§26–30   raw parser/Unicode/numeric/timestamp/header tests
§31–32   reconciliation/closed-world evidence tests
§33      irreversible consumption/replay tests
§34–36   crash/crossing ambiguity tests
§37      target-capability evidence tests
§38–39   recovery/idempotency/transport-attempt tests
§40      global safety-property tests
```

## Implementation Independence Rule

The Rust and Go conformance tracks should share:
- frozen source documents;
- machine-readable test vectors after audit;
- expected result manifests.

They should not share:
- parser code;
- canonicalizer code;
- Base64url implementation;
- signature-validation implementation;
- commitment implementation;
- state-machine/recovery implementation.

This preserves the dependency-independence requirement already recorded in Repair 4.

## Change Control

If a future architecture invariant cannot be mapped to a Repair 4 section, classify it as one of:

```text
IMPLEMENTATION REQUIREMENT
DEPLOYMENT PROFILE REQUIREMENT
COMMERCIAL PRODUCT REQUIREMENT
PROPOSED FUTURE ESRM EXTENSION
```

Do not present it as current ESRM semantics until it passes the separate normative freeze/conformance process.

Traceability is therefore bidirectional:

```text
protocol rule -> architecture consequence
architecture invariant -> protocol source or explicit non-protocol classification
```

That is the mechanism that prevents architecture drift.