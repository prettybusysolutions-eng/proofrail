# Acceptance bridge: signed intent to bounded evidence

Status: read-only research integration, not an execution adapter.

## Implemented mechanism

1. A trusted caller supplies an exact acceptance contract and enrolled keys.
2. A ProofRail Action Authority Envelope signs the contract's RFC 8785 digest
   through the existing observation_contract.success_predicate_digest field.
3. An SMATP sender signs a handoff containing the task, contract and authority.
4. The bridge verifies the sender, task digest, contract, exact enrolled
   authority, issuer, subject, issuance/expiry, roots, approval and exact effect
   using ProofRail's actual verify_action_authority_envelope implementation.
5. A separate observer signs an observation bound to the full handoff digest,
   authority digest, contract digest, tenant, task, target and observation time.
6. The bridge verifies the observer key, bindings, freshness and content digest.

No ProofRail schema or installed runtime code was modified. An explicit
full_digest helper hashes all fields, including task fields named signature;
ProofRail's hash_record intentionally excludes derived top-level fields and
is therefore inappropriate for hashing arbitrary task objects verbatim.

## Results

- VERIFIED: handoff binding checks passed. Not an execution grant.
- MATCH: the enrolled observer's signed evidence satisfies the expected digest.
- DIVERGED: a valid observation reports a different content digest.
- UNCONFIRMED: observation missing, effect absent or state unknown.
- Exceptions: invalid signatures, unauthorized substitutions, stale evidence,
  expired/future-dated handoffs or invalid contracts are rejected.

These are research verifier outcomes, not new ProofRail settlement states or
an ESRM conformance claim. All results explicitly set execution_authorized=false.
Read-only verification may be repeated; it does not consume single-use authority.

## Trusted inputs and limitations

Trust configuration and the expected contract must come from the operator or
authenticated policy context, never from request-supplied replacements. The
caller pins the full authority digest, issuer and keys, current expected roots
and approval. This module does not fetch current policy or perform revocation
lookups. It does not authenticate a tenant session or act as an identity provider.

Signed observer evidence is a claim from an enrolled observer, not proof that
the observer or provider is honest. An enrolled observer can still lie. External
readback, isolation of observer credentials, consumption-record binding, and
provider-specific verification are not yet connected here. A fresh observation
also does not guarantee state remains unchanged after observation.

The verifier checks a predetermined content hash, not general natural-language
task correctness. It does not execute model output or generated code. Python
dictionary inputs and the caller's clock are trusted to remain stable during a
call. The public-network and concurrency gates of the original prototype remain.

## Tests

26 bridge cases were added to the previous 16-test lab suite (42 total):
valid binding; sender re-signing altered tenant/task/target/predicate/observer/
recipient; changed task bytes; replacement valid authority; predicate altered
by a legitimate sender but not authorized by the issuer; correctly signed
observations transplanted across seven bindings; forged observer using the
correct key label; stale evidence; expired handoff; absent, unknown or missing
evidence; wrong output; changed policy roots; and complete arbitrary task hashing.

Tests use locally generated, distinct sender/issuer/observer keys and call real
ProofRail cryptographic and authority verification functions. They are internally
authored negative controls, not independent security certification.

Run from this directory after installing ProofRail:

```bash
python -m pip install ../.. -r requirements-dev.txt
python -m pytest -q tests/test_acceptance_bridge.py
```

## Remaining execution gate

The separate `execution_binding.py` research extension now implements local
consumption, single dispatch, and destination-recorded provenance; see
EXECUTION_ATTRIBUTION.md. The read-only bridge above retains its original scope.

Remaining: connect the reference behavior to the installed ProofRail consumption
path and a separately authenticated external provider. The research registry is
not shared with production ProofRail. It cannot establish globally single-use
authority across separate registries, administrative rollback, or provider-side
revocation. Preserve ambiguous outcomes and existing non-retry rules.
