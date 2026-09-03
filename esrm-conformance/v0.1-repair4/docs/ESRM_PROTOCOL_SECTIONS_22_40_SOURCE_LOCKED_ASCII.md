# ProofRail ESRM v0.1 - Canonical Baseline Freeze Corrections, ASCII Semantic Source Lock

Status: transport-safe protocol source for Repair 4. This document preserves the semantics of the operator-provided Sections 22-40 using ASCII-only mathematical notation. It does not claim byte-for-byte equality with the corrupted Repair 3 transport file.

ASCII_SOURCE_SEMANTIC_LOCK=PENDING_INDEPENDENT_AUDIT
NO CLAIM OF CONFORMANCE.

**22. Signature Does Not Confer Authority**
A cryptographically valid signature establishes only:
```text
SignedBy(E, k) = TRUE
```
It MUST NOT by itself establish:
```text
Authorized(E) = TRUE
```
Therefore the following transition is forbidden:
```text
DERIVED
  valid Ed25519 signature
AUTHORIZED
```
The correct transition is:
```text
DERIVED
  signature valid
ATTESTED
  signer identity valid
  key valid
  key not revoked
  authority lineage valid
  signer possesses authorization power
  scope covers transition
  temporal/state predicates hold
AUTHORIZED
```
Formally:
```text
AUTHORIZED(tau) IFF
  SignatureValid(tau)
  AND KeyValid(tau)
  AND IssuerRecognized(tau)
  AND AuthorityDerivationValid(tau)
  AND ScopeCovers(tau)
  AND StateValid(tau)
```
A valid signature from an unauthorized signer MUST produce a valid attestation to an unauthorized claim, not an authorized transition.

**23. Exact Commitment Encoding**
For artifact class x:
```text
B_x = UTF8(RFC8785Canonicalize(x))
```
```text
C_x = SHA256(
  ASCII(D_x) || BYTE(0x00) || B_x
)
```
Requirements:
D_x MUST consist only of bytes in ASCII range 0x21 through 0x7E.
BYTE(0x00) MUST NOT occur inside a registered domain string.
The domain string MUST be protocol-registered.
Domains MUST be version-specific.
Hash output MUST be lowercase hexadecimal.
SHA-256 commitments MUST contain exactly 64 lowercase hexadecimal characters.
Uppercase hexadecimal MUST be rejected rather than normalized.
Leading or trailing whitespace MUST be rejected.
Commitment strings MUST NOT contain a 0x prefix.
Example:
```text
PROOFRAIL:TRANSITION:V1
```
produces:
```text
SHA256(
  ASCII("PROOFRAIL:TRANSITION:V1")
  || BYTE(0x00)
  || canonical_bytes
)
```

**24. Registered Artifact Domains**
ESRM v0.1 freezes the following initial registry:
```text
PROOFRAIL:STATE:V1
PROOFRAIL:RULESET:V1
PROOFRAIL:AUTHORITY:V1
PROOFRAIL:ADMISSION:V1
PROOFRAIL:CONSUMPTION:V1
PROOFRAIL:TRANSITION:V1
PROOFRAIL:DISPATCH-INTENT:V1
PROOFRAIL:DISPATCH-CROSSING:V1
PROOFRAIL:OBSERVATION:V1
PROOFRAIL:RECONCILIATION:V1
PROOFRAIL:SETTLEMENT:V1
PROOFRAIL:RECOVERY:V1
PROOFRAIL:REVOCATION:V1
PROOFRAIL:KEY-STATUS:V1
PROOFRAIL:SIGNATURE:V1
```
No implementation may dynamically construct security domains from artifact_type.
Only registered protocol domains are valid.
Unknown domains MUST fail closed.
The verifier MUST derive the expected domain from the closed protocol registry. An artifact-supplied domain value MUST NOT determine the domain used to calculate a commitment.

**25. Signature Envelope**
The signed object SHALL exclude the signature bytes themselves.
Unsigned envelope:
```json
{
  "artifact_type": "proofrail.signature",
  "protocol_version": "0.1",
  "crypto_suite": "PR-ESRM-JCS-SHA256-ED25519-v1",
  "signed_artifact_type": "proofrail.transition",
  "signed_artifact_domain": "PROOFRAIL:TRANSITION:V1",
  "signed_commitment": "012345...",
  "signer_id": "issuer-001",
  "key_id": "key-001",
  "critical_extensions": [],
  "noncritical_extensions": {}
}
```
Let this envelope be E_tau.
Signature input:
```text
M_tau =
  ASCII("PROOFRAIL:SIGNATURE:V1")
  || BYTE(0x00)
  || UTF8(JCS(E_tau))
```
Then:
```text
signature_tau = Ed25519Sign(secret_key, M_tau)
```
The transmitted artifact equals E_tau plus:
```json
{
  "signature": "..."
}
```
The signature SHALL use RFC 4648 URL-safe Base64 without padding.
The lexical profile SHALL permit only A-Z, a-z, 0-9, hyphen, and underscore.
Padding character = MUST be rejected.
Whitespace MUST be rejected.
Alternate Base64 alphabets MUST be rejected.
The decoded Ed25519 signature MUST contain exactly 64 bytes.
Strict Base64url canonicality MUST be enforced:
```text
decoded_length = 64
decode succeeds strictly
reencode_unpadded_base64url(decoded) = supplied_signature
```
Equivalent decode and reencode equality MUST apply to 32-byte public keys in the future key registry.
The public key resolved through the key registry MUST contain exactly 32 raw Ed25519 public-key bytes and SHALL use unpadded RFC 4648 Base64url when represented textually.
A verifier MUST reconstruct E_tau by removing only the signature member from a transmitted signature object that has already passed its closed schema.
The transmitted signature object MUST contain no additional top-level members.
A verifier MUST NOT reconstruct signed metadata from external context.
The verifier MUST independently confirm:
```text
RegisteredDomain(signed_artifact_type)
  = signed_artifact_domain
```
A valid signature establishes ATTESTED, not AUTHORIZED.

**26. Strict JSON Intake Pipeline**
Security artifacts SHALL enter ProofRail through the following pipeline:
```text
RAW BYTES
RESOURCE-LIMIT VALIDATION
STRICT UTF-8 VALIDATION
JSON TOKENIZATION
DUPLICATE PROPERTY DETECTION
LEXICAL PROFILE VALIDATION
I-JSON VALIDATION
SCHEMA VALIDATION
SEMANTIC FIELD VALIDATION
JCS CANONICALIZATION
DOMAIN-SEPARATED COMMITMENT
SIGNATURE VERIFICATION
KEY-STATUS VALIDATION
AUTHORITY VALIDATION
PROTOCOL VALIDATION
```
Duplicate property names MUST be detected before conversion into a language-native dictionary, map, object, or equivalent structure.
For duplicate-name detection, escaped names SHALL be compared after JSON escape processing.
Duplicate-name example source bytes:
```text
RAW JSON BYTES:
7b 22 6b 65 79 22 3a 31 2c 22 5c 75 30 30 36 62 65 79 22 3a 32 7d
DISPLAY:
{"key":1,"BACKSLASH-u006bey":2}
```
Interpret BACKSLASH as the single byte 0x5c for explanatory display only. The binary corpus must later contain the actual raw bytes.
The top-level JSON value MUST be an object.
A UTF-8 BOM MUST be rejected.
A security artifact MUST contain exactly one top-level JSON value.
Any non-whitespace data after that value MUST be rejected.
The protocol SHALL explicitly define whether leading and trailing JSON whitespace is accepted. For ESRM v0.1 raw security artifacts, leading and trailing whitespace SHALL be rejected so the admitted wire profile has one exact framing rule.
A parser MUST reject comments, trailing commas, NaN, positive or negative Infinity, invalid UTF-8, unpaired surrogate code points, multiple top-level values, and implementation-specific JSON extensions.
A rejected artifact MUST NOT produce canonical bytes, a domain commitment, or a positive signature result.

**27. Unicode Profile**
The canonicalization layer SHALL NOT perform NFC, NFD, NFKC, NFKD, case folding, locale folding, transliteration, or homoglyph replacement.
JCS preserves Unicode string data as supplied rather than normalizing equivalent sequences.
U+00E9 and the sequence U+0065 followed by U+0301 remain cryptographically distinct.
Security identifiers SHOULD use a field-specific restricted grammar.
For protocol-defined identifiers, the preferred baseline is printable ASCII unless the field explicitly requires broader Unicode.
Canonical property ordering SHALL follow RFC 8785 UTF-16 code-unit ordering, not UTF-8 byte ordering, Unicode code-point ordering, locale rules, or host-language defaults.
Invalid Unicode data, including lone surrogate values, MUST fail closed.

**28. ProofRail Numeric Profile**
ESRM SHALL use a stricter numeric subset than ordinary JCS.
Security-critical JSON numeric tokens MUST represent nonnegative integers only, fall within 0 <= n <= 2^53 - 1, contain decimal digits only, contain no leading plus sign, contain no decimal point, contain no exponent, contain no leading zero except the literal 0, reject lexical negative zero, and reject all negative numeric tokens.
Valid examples: 0, 1, 42, 9007199254740991.
Invalid examples: -0, -1, 01, 1.0, 1e3, 1E3, +1, 9007199254740992.
These restrictions MUST be enforced against the original numeric token before conversion into a host-language numeric type.
Quantities requiring signed values, larger integers, decimal precision, money, timestamps, hashes, cryptographic quantities, or arbitrary precision SHALL use strings with explicitly registered grammars.
The numeric profile MUST apply recursively inside critical and noncritical extension values.

**29. Timestamp Profile**
RFC 3339 permits multiple textual representations of the same instant. ProofRail SHALL use a narrower signed-artifact profile.
ESRM v0.1 timestamp grammar:
```text
YYYY-MM-DDTHH:MM:SSZ
```
Requirements: uppercase T; uppercase Z; UTC only; no numeric offset; exactly four digits for year; exactly two digits for month, day, hour, minute, and second; no fractional seconds; no whitespace; leap-second value 60 MUST be rejected by ESRM v0.1; calendar validity MUST be checked; invalid dates and times MUST be rejected rather than normalized.
Example:
```text
2026-09-02T21:49:00Z
```
Protocol ordering MUST use logical_epoch or another explicitly defined logical sequence value where deterministic order matters.
Wall-clock timestamps MUST NOT implicitly establish transaction ordering.
ProofRail SHALL distinguish logical_epoch, issued_at, observed_at, received_at, expires_at, and evidence_deadline.
Wall-clock values establish temporal validity only under an explicitly committed clock policy.

**30. Mandatory Artifact Header**
Every security-relevant signed ESRM artifact SHALL require:
```json
{
  "artifact_type": "...",
  "protocol_version": "0.1",
  "crypto_suite": "PR-ESRM-JCS-SHA256-ED25519-v1",
  "critical_extensions": [],
  "noncritical_extensions": {}
}
```
This requirement applies to state assertions, rule sets represented as signed artifacts, authorities, admissions, consumptions, transition packages, dispatch intents, boundary-crossing artifacts, observations, reconciliations, settlements, recoveries, revocations, key-status statements, and signature artifacts.
critical_extensions is an ordered JSON array unless a future protocol version explicitly defines different semantics.
noncritical_extensions is a JSON object.
Until an extension registry and extension semantics are separately frozen, ESRM v0.1 allows only empty extensions:
```text
EXTENSIONS_PRESENT_BUT_NONE_REGISTERED_V0_1
critical_extensions = []
noncritical_extensions = {}
```
An implementation MUST NOT reorder arrays unless the protocol schema explicitly declares an array to be represented canonically as a sorted set before artifact construction.
Unknown critical extensions MUST cause deterministic rejection.
Unknown noncritical metadata MAY be retained only when its lack of security effect is explicitly defined by the protocol.
All critical and noncritical extension material appearing inside the governed artifact is included in its canonical bytes and domain-separated commitment.
Security-relevant meaning MUST NEVER be introduced through an uncommitted extension.

**31. Precise Reconciliation Result Algebra**
The reconciliation result set SHALL be MATCH, DIVERGED, INSUFFICIENT, and UNRESOLVED with mutually exclusive meanings.
```text
MATCH:
  empirical_world(tau) SATISFIES settlement_predicate(tau)
```
```text
DIVERGED:
  empirical_world(tau) DOES_NOT_SATISFY settlement_predicate(tau)
```
INSUFFICIENT means the current evidence set cannot establish MATCH or DIVERGED because one or more admissibility requirements are missing or invalid, while the committed reconciliation window remains open.
```text
INSUFFICIENT:
  WindowOpen
  AND NOT MatchEstablished
  AND NOT DivergenceEstablished
```
UNRESOLVED means the committed reconciliation epoch has closed and neither MATCH nor DIVERGED was established.
```text
UNRESOLVED:
  WindowClosed
  AND NOT MatchEstablished
  AND NOT DivergenceEstablished
```
These states MUST NOT be collapsed.
```text
Timeout DOES_NOT_IMPLY DIVERGED
```
Instead, timeout plus insufficient evidence implies UNRESOLVED unless the committed settlement predicate explicitly defines absence of an event by a deadline as the relevant empirical outcome and the closed-world requirements of Section 32 are satisfied.
A later observation MUST NOT mutate an existing reconciliation.
It SHALL create a new reconciliation artifact and, when applicable, a new reconciliation epoch.
A reconciliation conclusion belongs to the ADJUDICATED domain. It is not itself empirical evidence.

**32. Closed-World Absence Rule**
Absence of observed evidence MUST NOT establish evidence of absence.
For a predicate such as no payment occurred before deadline D, ProofRail may conclude absence only when the committed observer policy establishes that the evidence source possesses authoritative closed-world coverage over the relevant domain and interval.
```text
DeadlinePassed DOES_NOT_IMPLY EventAbsent
```
Instead:
```text
DeadlinePassed
  AND AuthoritativeCoverage(Domain, Interval)
  AND ClosedWorldEvidence
  AND NoEventObserved
  IMPLIES EventAbsent
```
Without closed-world evidence, the result MUST be UNRESOLVED, rather than DIVERGED or MATCH.
Evidence used to establish closed-world coverage MUST itself be retained and cryptographically committed.

**33. Consumption Irreversibility**
Consumption is an append-only fact.
```text
Consumed(authority_tau) = TRUE
```
Once true, no subsequent artifact may change it to FALSE. This includes proof that the target rejected the operation, the effect boundary was never crossed, no external effect occurred, observation failed, reconciliation failed, the process crashed, or the network timed out.
The original authority is spent.
ProofRail distinguishes RESERVATION_CANCELLED from AUTHORITY_CONSUMED.
A reservation may be cancelled only before consumption.
After consumption, any legitimate later attempt requires a newly derived authority artifact.
A new authority MAY cite cryptographic proof of non-effect as justification for regrant, but it remains a distinct authority.
```text
NonOccurrence(transition_1)
  DOES_NOT_IMPLY Reusable(authority_1)
```
Potentially:
```text
NonOccurrence(transition_1)
  AND RegrantPolicySatisfied
  IMPLIES Issue(authority_2)
```
with:
```text
authority_2 != authority_1
```
Reusing a consumed authority, consumed transition identifier, or consumed nonce MUST cause deterministic rejection.

**34. Crash-Safe Dispatch Boundary**
ProofRail SHALL NOT claim universal atomic equivalence between authority consumption and external effect:
```text
Consumed(authority_tau)
  IS_NOT_EQUIVALENT_TO ExternalEffect(transition_tau)
```
The dispatch lifecycle SHALL contain UNDISPATCHED, DISPATCH_INTENT_RECORDED, AUTHORITY_CONSUMED, CROSSING_POSSIBLE, DISPATCH_ACKNOWLEDGED, EFFECT_CONFIRMED, EFFECT_REJECTED, and EFFECT_UNRESOLVED.
Before releasing the first externally visible instruction or byte capable of creating the protected effect, ProofRail MUST durably record AUTHORITY_CONSUMED followed by CROSSING_POSSIBLE.
Only after both durable records exist may dispatch begin.
A crash between those durable commits and transmission may burn authority without producing an effect. That is an accepted availability loss.
It MUST NOT be repaired by silently restoring authority.
Safety dominates automatic completion.
Once CROSSING_POSSIBLE exists and conclusive external evidence does not exist:
```text
EffectStatus = UNKNOWN
```
Unknown effect status MUST NOT be converted into success, failure, or reusable authority.

**35. Dispatch Intent Artifact**
A dispatch-intent artifact SHALL contain:
```json
{
  "artifact_type": "proofrail.dispatch_intent",
  "protocol_version": "0.1",
  "crypto_suite": "PR-ESRM-JCS-SHA256-ED25519-v1",
  "transition_id": "...",
  "transition_commitment": "...",
  "authority_consumption_commitment": "...",
  "executor_identity_commitment": "...",
  "target_commitment": "...",
  "operation_commitment": "...",
  "effect_identity": "...",
  "dispatch_sequence": 0,
  "logical_epoch": 0,
  "critical_extensions": [],
  "noncritical_extensions": {}
}
```
The dispatch intent establishes authorized attempt prepared.
It does not establish transmitted, acknowledged, executed, observed, or settled.
The dispatch intent MUST be immutable and domain-committed under PROOFRAIL:DISPATCH-INTENT:V1.

**36. Boundary-Crossing Artifact**
Immediately before dispatch, ProofRail SHALL durably append:
```json
{
  "artifact_type": "proofrail.dispatch_crossing",
  "protocol_version": "0.1",
  "crypto_suite": "PR-ESRM-JCS-SHA256-ED25519-v1",
  "transition_commitment": "...",
  "dispatch_intent_commitment": "...",
  "authority_consumption_commitment": "...",
  "attempt_id": "...",
  "effect_identity": "...",
  "target_commitment": "...",
  "logical_epoch": 0,
  "critical_extensions": [],
  "noncritical_extensions": {}
}
```
The artifact establishes only that ProofRail became capable of crossing the protected effect boundary.
It deliberately does not prove that transport occurred.
Consequently, after restart:
```text
CrossingRecorded
  AND NOT ExternalEvidence
  IMPLIES EffectStatus = UNKNOWN
```
If ProofRail crashes after recording the artifact but before transmission, the effect may not have occurred.
If ProofRail crashes after transmission but before receiving a response, the effect may have occurred.
These cases are deliberately indistinguishable without additional target evidence.
This ambiguity is a legitimate epistemic state.

**37. External Target Capability Evidence**
A target adapter MUST NOT acquire a recovery class merely by self-declaration.
The target capability class SHALL itself be supported by a committed capability-evidence artifact.
Valid classes are ATOMIC_PARTICIPANT, DURABLE_IDEMPOTENCY, CONDITIONAL_MUTATION, QUERYABLE_EFFECT, OBSERVABLE_ONLY, and OPAQUE_TARGET.
Capability evidence SHOULD establish target identity, adapter identity, protocol or API version, tested capability, effect-identity scope, durability scope, deduplication scope, payload-binding behavior, observation authority, validity period, evidence source, and verification result.
The recovery engine MUST rely on the committed target-capability evidence that existed for the transition, not whatever capability the adapter claims after a crash.
For DURABLE_IDEMPOTENCY, the evidence MUST establish:
```text
SameEffectIdentity
  AND SameCanonicalPayload
  IMPLIES AtMostOneSemanticEffect
```
For QUERYABLE_EFFECT, the evidence MUST define whether a negative query result proves non-occurrence or merely lack of current knowledge.
For OBSERVABLE_ONLY and OPAQUE_TARGET, ambiguous dispatch MUST forbid automatic retry.

**38. Recovery Function**
Let D be a valid durable crossing artifact, K be valid evidence of durable idempotency for the exact effect identity, Q be admissible authoritative effect-status evidence, and F be admissible final non-occurrence evidence.
```text
Recover(D, K, Q, F):
  IF Q = Occurred:
    OBSERVE_AS_MATCH
  ELSE IF F = DidNotOccur:
    RECOVER_WITH_NEW_TRANSITION
  ELSE IF K AND Q != Occurred:
    RETRANSMIT_SAME_EFFECT
  ELSE:
    UNRESOLVED
```
RETRANSMIT_SAME_EFFECT is permissible only when durable idempotency evidence establishes:
```text
SameEffectIdentity
  AND SameCanonicalPayload
  IMPLIES AtMostOneSemanticEffect
```
The retransmission MUST use the same effect identity, same canonical operation commitment, same target, and same semantic transition.
Changing any security-relevant component converts the action into a new transition requiring new authority.
For OBSERVABLE_ONLY and OPAQUE_TARGET:
```text
AmbiguousDispatch IMPLIES AutomaticRetry = FORBIDDEN
```
Proof of non-occurrence does not restore the original consumed authority.
RECOVER_WITH_NEW_TRANSITION requires a new transition and newly derived authority.

**39. Transport Attempt Versus Semantic Transition**
ProofRail SHALL distinguish TransportAttempt from SemanticEffect.
Multiple transport attempts MAY belong to one transition only when target semantics provide verified durable deduplication.
Thus:
```text
attempt_1 != attempt_2
```
while:
```text
effectIdentity(attempt_1)
  = effectIdentity(attempt_2)
```
may remain valid.
Without proven durable idempotency:
```text
NewAttempt IMPLIES PotentialNewEffect
```
and automatic retry MUST be rejected.
A transport acknowledgement is not proof of semantic effect.
An executor response is not an independent observation merely because it describes an outcome.
Transport-attempt records MUST remain independently distinguishable from transition, observation, reconciliation, and settlement artifacts.

**40. Canonical Baseline Safety Claim**
ESRM v0.1 MUST NOT claim universal exactly-once execution.
It MAY claim the following property only when the implementation satisfies the specification:
```text
ProofRail never converts uncertain external effect status
into false success, false failure, or restored execution authority.
```
More formally:
```text
UnknownEffect(tau) IMPLIES
  NOT Settled(tau)
  AND NOT FailedByInference(tau)
  AND Consumed(authority_tau)
```
and:
```text
Retry(tau) IMPLIES
  VerifiedDurableIdempotency
  OR NewTransitionWithNewAuthority
```
The byte-level protocol boundary is RawBytes to StrictParse to Schema to CanonicalBytes to DomainCommitment to SignatureAttestation to AuthorityValidation.
The external-execution boundary is Intent to Consume to CrossingPossible to Dispatch to Observe to Adjudicate to Settle.
The protocol MUST preserve cryptographic validity not equal to authority validity not equal to empirical validity.
The protocol MUST preserve SPECULATIVE not equal to EMPIRICAL not equal to ADJUDICATED.
The final foundational invariant is that SETTLED(tau) requires independently distinguishable committed artifacts for State, Derivation, Authority, Admission, Consumption, Dispatch, Observation, Reconciliation, and Settlement.
No artifact may impersonate another epistemic role.
NO CLAIM OF CONFORMANCE.
