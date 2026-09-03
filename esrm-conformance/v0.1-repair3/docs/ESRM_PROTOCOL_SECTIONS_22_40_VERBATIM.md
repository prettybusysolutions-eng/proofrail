# ProofRail ESRM v0.1 — Canonical Baseline Freeze Corrections

**22. Signature Does Not Confer Authority**
A cryptographically valid signature establishes only:
[
SignedBy(E,k)=TRUE
]
It MUST NOT by itself establish:
[
Authorized(E)=TRUE
]
Therefore the following transition is forbidden:
```
DERIVED
   │
   │ valid Ed25519 signature
   ▼
AUTHORIZED
```
The correct transition is:
```
DERIVED
   │
   │ signature valid
   ▼
ATTESTED
   │
   │ signer identity valid
   │ key valid
   │ key not revoked
   │ authority lineage valid
   │ signer possesses authorization power
   │ scope covers transition
   │ temporal/state predicates hold
   ▼
AUTHORIZED
```
Formally:
[
AUTHORIZED(	au)
\iff
SignatureValid(	au)
\land
KeyValid(	au)
\land
IssuerRecognized(	au)
\land
AuthorityDerivationValid(	au)
\land
ScopeCovers(	au)
\land
StateValid(	au)
]
A valid signature from an unauthorized signer MUST produce a valid attestation to an unauthorized claim, not an authorized transition.


⸻


**23. Exact Commitment Encoding**
For artifact class (x):
[
C_x=
SHA256(
ASCII(D_x)
\parallel
0x00
\parallel
B_x
)
]
where:
[
B_x=UTF8(JCS(x))
]
Requirements:
(D_x) MUST consist only of bytes in ASCII range `0x21` through `0x7E`.
`0x00` MUST NOT occur inside a registered domain string.
The domain string MUST be protocol-registered.
Domains MUST be version-specific.
Hash output MUST be lowercase hexadecimal.
SHA-256 commitments MUST contain exactly 64 lowercase hexadecimal characters.
Uppercase hexadecimal MUST be rejected rather than normalized.
Leading or trailing whitespace MUST be rejected.
Commitment strings MUST NOT contain a `0x` prefix.
Example:
```
PROOFRAIL:TRANSITION:V1
```
produces:
```
SHA256(
  ASCII("PROOFRAIL:TRANSITION:V1")
  || 0x00
  || canonical_bytes
)
```


⸻


**24. Registered Artifact Domains**
ESRM v0.1 freezes the following initial registry:
```
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
No implementation may dynamically construct security domains from `artifact_type`.
Only registered protocol domains are valid.
Unknown domains MUST fail closed.
The verifier MUST derive the expected domain from the closed protocol registry. An artifact-supplied domain value MUST NOT determine the domain used to calculate a commitment.


⸻


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
Let this envelope be (E_	au).
Signature input:
[
M_	au=
ASCII(	ext{“PROOFRAIL:SIGNATURE:V1”})
\parallel
0x00
\parallel
UTF8(JCS(E_	au))
]
Then:
[
\sigma_	au=Ed25519Sign(sk,M_	au)
]
The transmitted artifact equals (E_	au) plus:
```json
{
  "signature": "..."
}
```
The signature SHALL use RFC 4648 URL-safe Base64 without padding.
The lexical profile SHALL permit only:
```
A-Z
a-z
0-9
-
_
```
`=` padding MUST be rejected.
Whitespace MUST be rejected.
Alternate Base64 alphabets MUST be rejected.
The decoded Ed25519 signature MUST contain exactly 64 bytes.
The public key resolved through the key registry MUST contain exactly 32 raw Ed25519 public-key bytes and SHALL use unpadded RFC 4648 Base64url when represented textually.
A verifier MUST reconstruct (E_	au) by removing only the `signature` member from a transmitted signature object that has already passed its closed schema.
The transmitted signature object MUST contain no additional top-level members.
A verifier MUST NOT reconstruct signed metadata from external context.
The verifier MUST independently confirm:
**[****RegisteredDomain(signed_artifact_type)**
signed_artifact_domain
]
A valid signature establishes `ATTESTED`, not `AUTHORIZED`.


⸻


**26. Strict JSON Intake Pipeline**
Security artifacts SHALL enter ProofRail through the following pipeline:
```
RAW BYTES
   ↓
RESOURCE-LIMIT VALIDATION
   ↓
STRICT UTF-8 VALIDATION
   ↓
JSON TOKENIZATION
   ↓
DUPLICATE PROPERTY DETECTION
   ↓
LEXICAL PROFILE VALIDATION
   ↓
I-JSON VALIDATION
   ↓
SCHEMA VALIDATION
   ↓
SEMANTIC FIELD VALIDATION
   ↓
JCS CANONICALIZATION
   ↓
DOMAIN-SEPARATED COMMITMENT
   ↓
SIGNATURE VERIFICATION
   ↓
KEY-STATUS VALIDATION
   ↓
AUTHORITY VALIDATION
   ↓
PROTOCOL VALIDATION
```
Duplicate property names MUST be detected before conversion into a language-native dictionary, map, object, or equivalent structure.
For duplicate-name detection, escaped names SHALL be compared after JSON escape processing.
Therefore:
```json
{
  "key": 1,
  "key": 2
}
```
is invalid because both names decode to the same Unicode sequence.
The top-level JSON value MUST be an object.
A UTF-8 BOM MUST be rejected.
A security artifact MUST contain exactly one top-level JSON value.
Any non-whitespace data after that value MUST be rejected.
The protocol SHALL explicitly define whether leading and trailing JSON whitespace is accepted. For ESRM v0.1 raw security artifacts, leading and trailing whitespace SHALL be rejected so the admitted wire profile has one exact framing rule.
A parser MUST reject:
comments;
trailing commas;
NaN;
positive or negative Infinity;
invalid UTF-8;
unpaired surrogate code points;
multiple top-level values;
implementation-specific JSON extensions.
A rejected artifact MUST NOT produce canonical bytes, a domain commitment, or a positive signature result.


⸻


**27. Unicode Profile**
The canonicalization layer SHALL NOT perform:
```
NFC
NFD
NFKC
NFKD
case folding
locale folding
transliteration
homoglyph replacement
```
JCS preserves Unicode string data as supplied rather than normalizing equivalent sequences.
Therefore:
```
U+00E9
```
and:
```
U+0065 U+0301
```
remain cryptographically distinct.
Security identifiers SHOULD use a field-specific restricted grammar.
For protocol-defined identifiers, the preferred baseline is printable ASCII unless the field explicitly requires broader Unicode.
Canonical property ordering SHALL follow RFC 8785 UTF-16 code-unit ordering, not:
UTF-8 byte ordering;
Unicode code-point ordering;
locale rules;
host-language defaults.
Invalid Unicode data, including lone surrogate values, MUST fail closed.


⸻


**28. ProofRail Numeric Profile**
ESRM SHALL use a stricter numeric subset than ordinary JCS.
Security-critical JSON numeric tokens MUST:
represent nonnegative integers only;
fall within:
[
0\le n\le2^{53}-1
]
contain decimal digits only;
contain no leading `+`;
contain no decimal point;
contain no exponent;
contain no leading zero except the literal `0`;
reject lexical negative zero;
reject all negative numeric tokens.
Valid:
```
0
1
42
9007199254740991
```
Invalid:
```
-0
-1
01
1.0
1e3
1E3
+1
9007199254740992
```
These restrictions MUST be enforced against the original numeric token before conversion into a host-language numeric type.
Quantities requiring signed values, larger integers, decimal precision, money, timestamps, hashes, cryptographic quantities, or arbitrary precision SHALL use strings with explicitly registered grammars.
The numeric profile MUST apply recursively inside critical and noncritical extension values.


⸻


**29. Timestamp Profile**
RFC 3339 permits multiple textual representations of the same instant. ProofRail SHALL use a narrower signed-artifact profile.
ESRM v0.1 timestamp grammar:
```
YYYY-MM-DDTHH:MM:SSZ
```
Requirements:
uppercase `T`;
uppercase `Z`;
UTC only;
no numeric offset;
exactly four digits for year;
exactly two digits for month, day, hour, minute, and second;
no fractional seconds;
no whitespace;
leap-second value `60` MUST be rejected by ESRM v0.1;
calendar validity MUST be checked;
invalid dates and times MUST be rejected rather than normalized.
Example:
```
2026-09-02T21:49:00Z
```Protocol ordering MUST use `logical_epoch` or another explicitly defined logical sequence value where deterministic order matters.
Wall-clock timestamps MUST NOT implicitly establish transaction ordering.
ProofRail SHALL distinguish:
```
logical_epoch
issued_at
observed_at
received_at
expires_at
evidence_deadline
```
Wall-clock values establish temporal validity only under an explicitly committed clock policy.


⸻


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
This requirement applies to:
state assertions;
rule sets represented as signed artifacts;
authorities;
admissions;
consumptions;
transition packages;
dispatch intents;
boundary-crossing artifacts;
observations;
reconciliations;
settlements;
recoveries;
revocations;
key-status statements;
signature artifacts.
`critical_extensions` is an ordered JSON array unless a future protocol version explicitly defines different semantics.
`noncritical_extensions` is a JSON object.
An implementation MUST NOT reorder arrays unless the protocol schema explicitly declares an array to be represented canonically as a sorted set before artifact construction.
Unknown critical extensions MUST cause deterministic rejection.
Unknown noncritical metadata MAY be retained only when its lack of security effect is explicitly defined by the protocol.
All critical and noncritical extension material appearing inside the governed artifact is included in its canonical bytes and domain-separated commitment.
Security-relevant meaning MUST NEVER be introduced through an uncommitted extension.


⸻


**31. Precise Reconciliation Result Algebra**
The reconciliation result set SHALL be:
[
\mathcal R=
{
MATCH,
DIVERGED,
INSUFFICIENT,
UNRESOLVED
}
]
with mutually exclusive meanings.
**MATCH**
Admissible evidence positively establishes:
[
\hat W_	au\models P_	au
]
where (P_	au) is the committed settlement predicate.
**DIVERGED**
Admissible evidence positively establishes:
[
\hat W_	au
ot\models P_	au
]
**INSUFFICIENT**
The current evidence set cannot establish `MATCH` or `DIVERGED` because one or more admissibility requirements are missing or invalid, while the committed reconciliation window remains open.
Examples:
insufficient observer set;
insufficient finality;
stale evidence;
untrusted source;
missing metadata;
incomplete evidence set.
Formally:
[
WindowOpen
\land

eg MatchEstablished
\land

eg DivergenceEstablished
\Rightarrow
INSUFFICIENT
]
**UNRESOLVED**
The committed reconciliation epoch has closed and neither `MATCH` nor `DIVERGED` was established.
[
WindowClosed
\land

eg MatchEstablished
\land

eg DivergenceEstablished
\Rightarrow
UNRESOLVED
]
These states MUST NOT be collapsed.
Expiration of an observation deadline MUST NOT itself establish divergence:
[
timeout
ot\Rightarrow DIVERGED
]
Instead:
[
timeout
\land

eg sufficientEvidence
\Rightarrow
UNRESOLVED
]
unless the committed settlement predicate explicitly defines absence of an event by a deadline as the relevant empirical outcome and the closed-world requirements of Section 32 are satisfied.
A later observation MUST NOT mutate an existing reconciliation.
It SHALL create a new reconciliation artifact and, when applicable, a new reconciliation epoch.
A reconciliation conclusion belongs to the `ADJUDICATED` domain. It is not itself empirical evidence.


⸻


**32. Closed-World Absence Rule**
Absence of observed evidence MUST NOT establish evidence of absence.
For a predicate such as:
```
No payment occurred before deadline D.
```
ProofRail may conclude absence only when the committed observer policy establishes that the evidence source possesses authoritative closed-world coverage over the relevant domain and interval.
Therefore:
[
DeadlinePassed

ot\Rightarrow
EventAbsent
]
Instead:
[
DeadlinePassed
\land
AuthoritativeCoverage(Domain,Interval)
\land
ClosedWorldEvidence
\land
NoEventObserved
\Rightarrow
EventAbsent
]Without closed-world evidence, the result MUST be `UNRESOLVED`, rather than `DIVERGED` or `MATCH`.
Evidence used to establish closed-world coverage MUST itself be retained and cryptographically committed.


⸻


**33. Consumption Irreversibility**
Consumption is an append-only fact.
Once:
[
Consumed(A_	au)=TRUE
]
no subsequent artifact may change it to `FALSE`.
This includes proof that:
the target rejected the operation;
the effect boundary was never crossed;
no external effect occurred;
observation failed;
reconciliation failed;
the process crashed;
the network timed out.
The original authority is spent.
ProofRail distinguishes:
```
RESERVATION_CANCELLED
```
from:
```
AUTHORITY_CONSUMED
```
A reservation may be cancelled only before consumption.
After consumption, any legitimate later attempt requires a newly derived authority artifact.
A new authority MAY cite cryptographic proof of non-effect as justification for regrant, but it remains a distinct authority.
Thus:
[
NonOccurrence(T_1)

ot\Rightarrow
Reusable(A_1)
]
but potentially:
[
NonOccurrence(T_1)
\land
RegrantPolicySatisfied
\Rightarrow
Issue(A_2)
]
with:
[
A_2
eq A_1
]
Reusing a consumed authority, consumed transition identifier, or consumed nonce MUST cause deterministic rejection.


⸻


**34. Crash-Safe Dispatch Boundary**
ProofRail SHALL NOT claim universal atomic equivalence between authority consumption and external effect:
[
Consumed(A_	au)

ot\Leftrightarrow
ExternalEffect(T_	au)
]
The dispatch lifecycle SHALL contain:
```
UNDISPATCHED
DISPATCH_INTENT_RECORDED
AUTHORITY_CONSUMED
CROSSING_POSSIBLE
DISPATCH_ACKNOWLEDGED
EFFECT_CONFIRMED
EFFECT_REJECTED
EFFECT_UNRESOLVED
```
Before releasing the first externally visible instruction or byte capable of creating the protected effect, ProofRail MUST durably record:
```
AUTHORITY_CONSUMED
```
followed by:
```
CROSSING_POSSIBLE
```
Only after both durable records exist may dispatch begin.
A crash between those durable commits and transmission may burn authority without producing an effect.
That is an accepted availability loss.
It MUST NOT be repaired by silently restoring authority.
Safety dominates automatic completion.
Once `CROSSING_POSSIBLE` exists and conclusive external evidence does not exist:
[
EffectStatus=UNKNOWN
]
Unknown effect status MUST NOT be converted into success, failure, or reusable authority.


⸻


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
The dispatch intent establishes:
```
authorized attempt prepared
```
It does not establish:
```
transmitted
acknowledged
executed
observed
settled
```
The dispatch intent MUST be immutable and domain-committed under:
```
PROOFRAIL:DISPATCH-INTENT:V1
```


⸻


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
The artifact establishes only:
```
ProofRail became capable of crossing the protected effect boundary.
```
It deliberately does not prove that transport occurred.
Consequently, after restart:
[
CrossingRecorded
\land

eg ExternalEvidence
\Rightarrow
EffectStatus=UNKNOWN
]
If ProofRail crashes after recording the artifact but before transmission, the effect may not have occurred.
If ProofRail crashes after transmission but before receiving a response, the effect may have occurred.These cases are deliberately indistinguishable without additional target evidence.
This ambiguity is a legitimate epistemic state.


⸻


**37. External Target Capability Evidence**
A target adapter MUST NOT acquire a recovery class merely by self-declaration.
The target capability class SHALL itself be supported by a committed capability-evidence artifact.
Valid classes:
```
ATOMIC_PARTICIPANT
DURABLE_IDEMPOTENCY
CONDITIONAL_MUTATION
QUERYABLE_EFFECT
OBSERVABLE_ONLY
OPAQUE_TARGET
```
Capability evidence SHOULD establish:
target identity;
adapter identity;
protocol or API version;
tested capability;
effect-identity scope;
durability scope;
deduplication scope;
payload-binding behavior;
observation authority;
validity period;
evidence source;
verification result.
The recovery engine MUST rely on the committed target-capability evidence that existed for the transition, not whatever capability the adapter claims after a crash.
For `DURABLE_IDEMPOTENCY`, the evidence MUST establish:
[
SameEffectIdentity
+
SameCanonicalPayload
\Rightarrow
AtMostOneSemanticEffect
]
For `QUERYABLE_EFFECT`, the evidence MUST define whether a negative query result proves non-occurrence or merely lack of current knowledge.
For `OBSERVABLE_ONLY` and `OPAQUE_TARGET`, ambiguous dispatch MUST forbid automatic retry.


⸻


**38. Recovery Function**
Let:
(D) = valid durable crossing artifact;
(K) = valid evidence of durable idempotency for the exact effect identity;
(Q) = admissible authoritative effect-status evidence;
(F) = admissible final non-occurrence evidence.
Then:
[
Recover(D,K,Q,F)=
egin{cases}
OBSERVE_AS_MATCH,
&
Q=Occurred
\[4pt]
RECOVER_WITH_NEW_TRANSITION,
&
F=DidNotOccur
\[4pt]
RETRANSMIT_SAME_EFFECT,
&
K
\land
Q
eq Occurred
\[4pt]
UNRESOLVED,
&
otherwise
\end{cases}
]
`RETRANSMIT_SAME_EFFECT` is permissible only when durable idempotency evidence establishes:
[
SameEffectIdentity
+
SameCanonicalPayload
\Rightarrow
AtMostOneSemanticEffect
]
The retransmission MUST use:
the same effect identity;
the same canonical operation commitment;
the same target;
the same semantic transition.
Changing any security-relevant component converts the action into a new transition requiring new authority.
For `OBSERVABLE_ONLY` and `OPAQUE_TARGET`:
[
AmbiguousDispatch
\Rightarrow
AutomaticRetry=FORBIDDEN
]
Proof of non-occurrence does not restore the original consumed authority.
`RECOVER_WITH_NEW_TRANSITION` requires a new transition and newly derived authority.


⸻


**39. Transport Attempt Versus Semantic Transition**
ProofRail SHALL distinguish:
```
TransportAttempt
```
from:
```
SemanticEffect
```
Multiple transport attempts MAY belong to one transition only when target semantics provide verified durable deduplication.
Thus:
[
attempt_1
eq attempt_2
]
while:
**[**
**
**
**effectIdentity(attempt_1)**
effectIdentity(attempt_2)
]
may remain valid.
Without proven durable idempotency:
[
NewAttempt
\Rightarrow
PotentialNewEffect
]
and automatic retry MUST be rejected.
A transport acknowledgement is not proof of semantic effect.
An executor response is not an independent observation merely because it describes an outcome.
Transport-attempt records MUST remain independently distinguishable from transition, observation, reconciliation, and settlement artifacts.


⸻


**40. Canonical Baseline Safety Claim**
ESRM v0.1 MUST NOT claim universal exactly-once execution.
It MAY claim the following property only when the implementation satisfies the specification:
[
oxed{
egin{aligned}
&	ext{ProofRail never converts uncertain external effect status}&	ext{into false success, false failure, or restored execution authority.}
\end{aligned}
}
]
More formally:
[
UnknownEffect(	au)
\Rightarrow

eg Settled(	au)
\land

eg FailedByInference(	au)
\land
Consumed(A_	au)
]
and:
[
Retry(	au)
\Rightarrow
VerifiedDurableIdempotency
\lor
NewTransitionWithNewAuthority
]
The byte-level protocol boundary is:
[
RawBytes
ightarrow
StrictParse
ightarrow
Schema
ightarrow
CanonicalBytes
ightarrow
DomainCommitment
ightarrow
SignatureAttestation
ightarrow
AuthorityValidation
]
The external-execution boundary is:[
Intent
ightarrow
Consume
ightarrow
CrossingPossible
ightarrow
Dispatch
ightarrow
Observe
ightarrow
Adjudicate
ightarrow
Settle
]
The protocol MUST preserve:
[
	ext{cryptographic validity}

eq
	ext{authority validity}

eq
	ext{empirical validity}
]
and:
[
	ext{SPECULATIVE}

eq
	ext{EMPIRICAL}

eq
	ext{ADJUDICATED}
]
The final foundational invariant is:
[
SETTLED(	au)
]
requires independently distinguishable committed artifacts for:
```
State
→ Derivation
→ Authority
→ Admission
→ Consumption
→ Dispatch
→ Observation
→ Reconciliation
→ Settlement
```
No artifact may impersonate another epistemic role.
NO CLAIM OF CONFORMANCE.
