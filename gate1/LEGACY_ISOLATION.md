# Gate 1 Legacy Isolation Rules

Status: NON-NORMATIVE SAFETY BOUNDARY

Repair 4 is authoritative where covered. Older ProofRail documents and schemas remain historical implementation material and must not silently define ESRM v0.1 behavior when they conflict with Repair 4.

## Isolated legacy semantics

### 1. `RECONCILIATION_FAILED` as the reconciliation algebra

Forbidden for Gate 1 ESRM expected results.

Repair 4 requires four mutually exclusive results:

- MATCH
- DIVERGED
- INSUFFICIENT
- UNRESOLVED

A legacy implementation state may remain in historical code, but a Gate 1 conformance vector must never map these four states into one generic failure value.

### 2. `idempotency_required=true` as proof of durable idempotency

Forbidden.

A boolean adapter field cannot establish the target property required by Sections 37–38. Same-effect retransmission requires committed capability evidence proving the relevant durability/deduplication semantics for the exact effect identity and canonical payload scope.

### 3. Generic JSON Schema `date-time`

Insufficient for ESRM timestamp conformance.

Repair 4 requires the narrow `YYYY-MM-DDTHH:MM:SSZ` profile plus calendar validity and rejection of fractional seconds, offsets, alternate casing, and leap-second value 60.

### 4. Coarse `EXECUTING` state as a dispatch substitute

Forbidden as a complete representation of the Repair 4 boundary.

Gate 1 must preserve independently distinguishable intent, consumed authority, crossing-possible state, transport attempt, observation, reconciliation, and settlement semantics. A single coarse state cannot prove which boundary was crossed before a crash.

### 5. Blanket `NEW_AUTHORITY_REQUIRED` for every retry

Incomplete and therefore forbidden as the ESRM recovery function.

Repair 4 allows a narrow `RETRANSMIT_SAME_EFFECT` branch only when verified durable-idempotency evidence exists and the exact effect identity, canonical operation commitment, target, and semantic transition remain unchanged. Otherwise recovery is observation, a new transition/new authority after proven non-occurrence, or UNRESOLVED.

### 6. Executor response as provider truth

Forbidden.

An executor receipt or transport acknowledgement is an execution/transport claim. It cannot become empirical observation merely because it reports success.

### 7. Signature validity as authorization

Forbidden.

A valid signature is attributable attestation only until key status, issuer recognition, authority lineage, scope, state, and protocol predicates validate.

## Enforcement requirement

Any future Gate 1 validator or vector generator must maintain a forbidden-token/semantic check covering these legacy mappings. Discovery of a legacy value in a historical file is not itself a failure; using it as the expected ESRM semantic result is.

## Migration rule

Legacy files are not rewritten merely to make history look consistent. Migration must create new ESRM-derived artifacts with explicit provenance and leave historical files inspectable.