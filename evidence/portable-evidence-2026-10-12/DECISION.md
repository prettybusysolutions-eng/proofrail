# Portable evidence comparison and investment gate

Date: 2026-10-12. Internal assistant-authored experiment, not independent review.

## Decision

The tested checkpoint/export layer provides useful offline integrity verification,
but no additional detection coverage over a conventional signed-digest baseline
in this experiment. Reduced human audit effort, integration cost, customer demand
and acquisition value remain unmeasured. Do not claim they were disproved; do not
claim they were established.

Pause speculative runtime expansion, company formation for this thesis, valuation
claims and paid review procurement based solely on this evidence. Preserve the
pilot and unmerged repair/review work. The next investment should be conditional
on an actual workflow where ProofRail's semantic evidence saves work that an
equivalent conventional implementation cannot cheaply eliminate.

## Completed comparison

Generated a synthetic 100-event ledger (27,625 bytes), exported it with ProofRail,
and signed its checkpoint. For the conventional path, signed the SHA-256 digest
of those exact same bytes using Ed25519. The conventional verifier does not use
ProofRail verification APIs; fixture generation uses ProofRail's ledger format.
Both paths receive an externally supplied trusted public key, and both receive
the same retained latest-ledger digest in the freshness test.

Ran ten cases through each verifier in fresh Python subprocesses, with public
verification material only and no private keys written to disk. Twenty observed
outcomes matched the specified expectations. This is not a separate machine,
independent reviewer, network-sandbox test or installed-distribution test.

| Case | Conventional | ProofRail |
| --- | --- | --- |
| Authentic export | Accept | Accept |
| Altered content | Reject | Reject |
| Deleted tail | Reject | Reject |
| Reordered records | Reject | Reject |
| Duplicated record | Reject | Reject |
| Corrupted signature | Reject | Reject |
| Attacker-signed replacement, original trusted key retained | Reject | Reject |
| Old valid export with no external freshness reference | Accept | Accept |
| Old export with retained latest digest | Reject | Reject |
| Signer signs a false success claim | Accept integrity | Accept integrity |

The final row is not a signature-verification defect. It demonstrates the scope
of the primitive: authentic signed content can still contain false claims. The
false fixture explicitly contains `provider_confirmed=false` and
`claimed_success=true`; neither integrity verifier purports to check that semantic
contradiction. ProofRail's separate lifecycle, quorum and observation paths were
not compared here. Whole-system capability cannot be inferred from this subset.

The freshness reference was supplied by the harness. We did not implement or
test its independent retention/distribution service. Receiving a key or digest
inside an untrusted bundle alone would not establish its trustworthiness.

The serialized manifests were 183 bytes for the conventional path and 765 bytes
for ProofRail. That is one fixture, not total operational cost. Both require an
artifact, a signature/checkpoint, a trusted key and a verification invocation.
Per-case timing is retained for transparency but has only one observation per
case and excludes interpreter startup; it is not a speed benchmark. No human
reviewers, time savings, onboarding costs or commercial outcomes were measured.

## What existing products establish

Sigstore already documents portable bundles and offline verification. Therefore
offline verification alone is not evidence of a new control point. This was not
a Sigstore benchmark and does not establish whole-product equivalence.

NIST describes signatures as supporting integrity and origin authentication.
Our false-claim case illustrates why those properties do not substitute for
independent observation of the underlying event.

Primary sources checked 2026-10-12:

- https://docs.sigstore.dev/cosign/verifying/verify/
- https://docs.sigstore.dev/about/bundle/
- https://csrc.nist.gov/glossary/term/digital_signature

## Concrete remaining experiment: semantic review effort

The following is a proposed decision gate, not a result:

1. Obtain one adopter's redacted execution-review workflow with permission to
   evaluate it. Record current review time and which decisions require provider
   access, policy history, human judgment or follow-up messages.
2. Define the exact decision before choosing tools: for example whether a given
   merge was authorized under the applicable policy and bound to the expected
   head, with sufficient provider evidence. Agree on labels and severe errors.
3. Give both implementations the same evidence, trust roots, observation access,
   freshness references and lifecycle rules. Extend the conventional comparator
   to equivalent semantic checks. Use a named established alternative if it fits.
4. Prepare at least 20 matched cases including stale policies, replay, missing
   evidence, conflicting observers and ambiguous outcomes. Counterbalance case
   order across reviewers and reserve cases not seen while building the tools.
5. Measure correct decisions, severe false acceptances, elapsed review time,
   manual steps, integration effort and maintenance burden. Count setup costs;
   avoid using code-line count or assistant response speed as labor savings.
6. Proposed continuation gate: no severe false acceptance and at least 30% lower
   median review time with comparable accuracy, plus adopter agreement that the
   measured savings warrant a paid pilot. The 30% threshold is a proposed business
   hurdle, not a standard or validated market requirement. Twenty cases are an
   initial signal, not a broad statistical or security guarantee.

An assistant can generate cases and run code here. It cannot supply independent
human review time, an adopter's actual costs or a buyer's willingness to pay.
Without those inputs, continue only bounded technical work answering a specific
unresolved question; do not replace missing market evidence with more claims.

## Reproduction and source identity

```bash
python -m pip install .
python benchmarks/portable_evidence_comparison.py --output results.json
```

Raw case outputs are in `results.json`, including the harness hash. The retained
run used the existing audit virtual environment. The script explicitly imports
runtime source from this checkout in both parent and verifier subprocesses.

Local tested commit: `ee92e37265a5c97e2b543c0e9b81c40627e19b49`.
Remote equivalent: `5e2dcf850bf67b52664538566122c8ef70def326`.
Identical tree: `5cccf546cd3604e1afa99ed7a83612c5deb1852c`.
These evidence files were committed afterward. No runtime implementation was
changed in this experiment. No external messages were sent or funds committed.
