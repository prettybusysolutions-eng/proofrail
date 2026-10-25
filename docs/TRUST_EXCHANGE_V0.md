# ProofRail Trust Exchange — Cross-Domain Witness Profile v0

**Status:** experimental implementation and specification draft. Not a published
interoperability standard, SCITT implementation, regulated trust service,
operationally independent witness network, or production authorization gate.

## The actual integration problem

An AWS-hosted AI agent may request an action in GitHub, Microsoft Entra,
another cloud, an enterprise ERP or a physical facilities system. Each system
can apply its own local policy. An enterprise buyer still needs a portable,
independently verifiable answer to **what exact authority was used, which
effect was claimed, what outcome evidence was observed, and whether the
underlying evidence history was silently replaced**.

Build on incumbent identity and policy systems, not around them. The proposed
neutral role is a *verification profile*: independent operators can attest to
the same immutable action commitment, with portable offline verification.

AWS AgentCore's policy gateway and Microsoft Entra Agent ID are
complementary local authority mechanisms. The IETF's SCITT architecture,
[RFC 9943](https://www.rfc-editor.org/rfc/rfc9943), already defines
transparency statements, verifiable-data-structure inclusion receipts, and
cross-service auditability. We should **integrate with SCITT**, not rebrand
its core properties or claim we invented signed transparency.

## v0 narrow trust primitive

`proofrail.trust_exchange` defines a canonical JSON witness statement
binding:

- `authority_digest`: the previously verified exact action authority;
- `effect_digest`: the exact target and parameters, already checked by
  the enforcement layer;
- `outcome_digest`: independently observed outcome *evidence commitment*;
- `checkpoint_digest`: the ProofRail signed Merkle checkpoint committing
  the local evidence ledger;
- `previous_checkpoint_digest` and `sequence`: an expected history link
  and monotonic sequence **supplied by an external verifier**;
- `execution_domain`: the independently pinned provider/tenant namespace.

The statement includes no credential, private key, personal record or
unhashed customer payload. Digest-only content minimizes disclosure but
does **not** stop dictionary attacks against guessable underlying data.

Each separately administered witness signs the **same statement digest**,
using ProofRail's RFC 8785 canonicalization and Ed25519 `sign_record`.
The portable receipt embeds a signer ID and operator ID. A verifier receives
the key roster from a **separate trusted channel**; the bundle cannot
introduce its own trusted keys or redefine which operators are independent.

`verify_witness_exchange` recomputes the supplied signed checkpoint against
the supplied ledger, compares the checkpoint hash, checks every externally
pinned expected statement field (including previous root and sequence),
verifies witness signatures and key IDs, and requires at least two
**distinct administrative operator IDs**. Multiple keys from one operator
cannot satisfy this independence condition.

**These operator IDs are assertions in the external trust roster.** The code
cannot prove true legal or infrastructure independence. Verification of
provider-side truth, external checkpoint custody, provider policy, witness
operational controls and resistance to colluding operators requires
separately witnessed evidence.

## Where this fits

```text
Any agent/model/framework
   -> local policy authority (AWS/Entra/other)
   -> ProofRail exact-effect authority and provider enforcement
   -> independently checked outcome + ProofRail signed checkpoint
   -> 2+ independent witness services sign the same commitment
   -> portable verification with externally pinned roster and prior root
   -> optional SCITT transparency receipt or another external retention system
```

**No part of v0 calls a remote witness service, persists a shared history,
anchors to SCITT, creates live provider authorization, establishes a neutral
governing consortium, verifies a provider effect, or enforces a merge.** It
establishes only the cryptographically checkable agreement primitive that such
systems would need.

## Offline verification from the installed package

The portable profile has strict machine-readable contracts:
`schemas/cross_domain_witness_statement.schema.json` and
`schemas/cross_domain_witness_receipt.schema.json`. The verifier is shipped
as the `proofrail-exchange` entry point in the ProofRail wheel.

```sh
proofrail-exchange \
  --statement /received-bundle/witness-statement.json \
  --receipts /received-bundle/witness-receipts.json \
  --ledger /received-bundle/ledger.jsonl \
  --checkpoint /received-bundle/signed-checkpoint.json \
  --checkpoint-public-key /trusted-operator/checkpoint-public-key.txt \
  --trusted-witnesses /trusted-operator/pinned-witness-keys.json \
  --expected /trusted-operator/pinned-expectations.json
```

The JSON roster maps signer IDs to `operator_id`, `key_id`, and `public_key`
(URL-safe base64-encoded Ed25519 public keys); the external expectations file
contains every statement field **except `kind`**, including
`previous_checkpoint_digest` and `sequence`. Signature and exact-context
checks fail closed. Exit code `0` indicates the narrow cryptographic
verification passed, `4` indicates a refused bundle, and `2` indicates
invalid inputs. **The verifier never downloads a trusted key from the
bundle**. A user who copies the keys/expected state from that same bundle has
not established an external trust root.

This CLI performs no live provider calls, network requests, agent approvals,
merges, witness signing or registry writes.

## Concrete adoption test

A meaningful next demonstration would require:

1. A GitHub merge adapter and a non-GitHub execution adapter to produce
   evidence commitments in the same interoperable format.
2. At least two operator-run witness processes with separate credentials,
   separate administration, independent provider reads and separate
   checkpoint retention; not two test keys controlled by ProofRail.
3. A third-party verifier to obtain operator keys and the previous checkpoint
   from independent channels, verify both bundles without ProofRail cloud
   access, and detect swapped outcomes, conflicting signers, changed heads,
   rollback and truncated ledgers.
4. SCITT integration with verifiable inclusion and consistency evidence, not
   merely emitting SCITT-shaped JSON.
5. Two independently written client implementations to reproduce the tests
   with the same vectors and error semantics.

Without steps 2–5 this is an internal cryptographic experiment, not
an independent trust network.

## Economic model and defensibility

Keep the **receipt format and verifier open and free**. Organizations should
own their keys and policy; they can replace a ProofRail-operated verifier.
Offer paid certified production-grade enforcement adapters, policy
distribution, operations, retained witness service, key management,
dispute/incident workflows, compliance exports and supported SLAs.

The possible moat is not an uncopyable algorithm. It is audited
interoperability, trusted operators, integrations, developer adoption and
high-fidelity evidence accumulated across otherwise competing platforms.
No large cloud provider is technically prevented from implementing this
profile, forking an open implementation or joining a competing standard.
Neutral consortium governance and genuinely distributed trust are goals
that prevent unilateral control over **evidence**, not an exclusive monopoly
over the protocol. Commercial adoption must be earned.

## Threat-model omissions

The current prototype does not solve collusion among independent signers,
operator spoofing in a dishonest external roster, stale or compromised
checkpoint keys, provider lying to every observer, compromised signing
endpoints, fork accountability across multiple bundles, timestamp proofs,
privacy inference from hashes, revocation propagation, issuer compromise,
multi-tenant service isolation, or a network-level atomic consume-and-execute
protocol. An attestation records what a signer asserted, not objective truth.

The next proof should go after those unimplemented properties, not
declare them resolved.
