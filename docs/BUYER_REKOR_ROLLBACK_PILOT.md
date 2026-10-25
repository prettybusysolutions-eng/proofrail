# Buyer high-water and Rekor v2 request dry run (experimental)

**Status:** implementation and unit fixtures only. This draft is stacked on
the SCITT COSE prototype (PR #63). It DOES NOT submit anything to Rekor,
verify a Rekor inclusion proof, merge a GitHub PR, provide a production
authority check, or prove an independent transparency witness.

## Why this is narrower than a new witness network

Use Sigstore Rekor v2 for independent publication when authorized. Rekor v2
has a documented POST /api/v2/log/entries interface taking
hashedRekordRequestV002, including a base64 SHA-256 artifact digest, detached
signature and a DER SubjectPublicKeyInfo public key. Rekor v2 hashedrekord
requires a **prehash-compatible** signing algorithm; its server rejects pure
Ed25519 PKIX_ED25519. The outer artifact signature in this dry run is ECDSA
P-256 with SHA-256 (PKIX_ECDSA_P256_SHA_256). The original inner SCITT
COSE signature remains Ed25519 (-19). It has **no
latest-by-stream search index**; monitors read tiles/checkpoints instead.
Do not submit to rekor.sigstore.dev's removed v1 API or hardcode the current
tile shard. Resolve actual writable shard from Sigstore's authenticated
current signing configuration at execution time.

The standard SCITT COSE checkpoint statement still exists independently;
Rekor hashedrekord would log SHA-256 of those **exact COSE bytes** (which the
holder also signs with a second detached Ed25519 signature). It does not
transform that COSE message into an RFC 9942 SCITT receipt. SCITT remains the
desired future registration profile if/when a suitable service is available.

Official reference: https://github.com/sigstore/rekor-tiles/blob/main/CLIENTS.md

## 1. Buyer-owned high-water mark

proofrail/buyer_highwater.py implements BuyerHighWaterStore:

- Its stable stream ID is SHA-256 over canonical JSON of buyer-pinned
  (issuer, subject, execution domain), not a value accepted from a bundle.
- It validates ProofRail's issuer COSE signature, the independently pinned
  expected claim, the separately trusted checkpoint signer and full ledger
  commitment before **any** SQLite head mutation.
- It accepts only genesis (sequence 1 / GENESIS) for a new stream.
- A next checkpoint MUST have sequence = current sequence + 1 and
  previous_checkpoint_digest = current accepted checkpoint digest.
- An identical duplicate is idempotent; an older checkpoint, same-sequence
  competing digest, gap, or broken predecessor is refused.
- SQLite BEGIN IMMEDIATE serializes concurrent read/check/write; FULL
  synchronous and DELETE journal improve local durability.

This is a **buyer-local signed-state observer** and intentionally returns
externally_anchored=false, rekor_inclusion_verified=false,
merge_authorized=false. It does not grant authority, enforce policy, or prove
a real provider-side effect. It does not certify that a checkpoint was
registered in any transparency log.

**Custody condition:** buyer must keep this SQLite DB on buyer-only storage,
away from issuer/agent write permissions. Back it up and anchor its highest
accepted checkpoint in a *separate independently administered store* for
stronger durability. It does NOT cryptographically prevent replacement of
the buyer database itself; tests explicitly demonstrate that rolling it
back makes an older checkpoint appear current again. For enterprise use,
prefer an actual buyer-controlled durable transactional service and a second
independent high-water witness. File-level fsync is not a remote monotonic
counter.

**Bootstrap:** this fixture uses buyer-pinned keys and the trusted GENESIS
sequence. An arbitrary initial checkpoint not independently authorized by
the buyer is a trust-on-first-use attack. The buyer should authenticate
the expected stream identity and genesis checkpoint before opening an
operational pipeline.

**Important:** the issuer uses the same stable COSE CWT subject for all
checkpoints in a stream; do not derive it per action.

## 2. Rekor v2 dry-run (no network)

scripts/rekor_v2_dryrun.py consumes only these three previously created,
publicly shareable artifacts:

1. Signed ProofRail COSE_Sign1 statement (binary)
2. ASN.1 DER ECDSA P-256 SHA-256 **detached signature over those exact COSE bytes**
3. The detached ECDSA P-256 signature key's public key in standard X.509
   SubjectPublicKeyInfo DER form (not a raw point or PEM text)

The script validates that the ECDSA-SHA256 detached signature covers the COSE
bytes and then writes two files: rekor-v2-request.json (the documented
hashedRekordRequestV002 API request body) and dry-run-metadata.json.
It writes nothing to GitHub or Rekor and contains no network transport or
submission command.

From a checkout on this branch, in an environment with project dependencies:

~~~sh
# Example: operator signs an already-created COSE file locally.
# NEVER commit the private key or upload it to an agent.
openssl ecparam -name prime256v1 -genkey -noout \
  -out /buyer/rekor-p256-private.pem
openssl dgst -sha256 -sign /buyer/rekor-p256-private.pem \
  -out /buyer/rekor-detached-signature.bin \
  /buyer/signed-checkpoint-statement.cose
openssl pkey -in /buyer/rekor-p256-private.pem -pubout -outform DER \
  -out /buyer/rekor-public-key.spki.der

python scripts/rekor_v2_dryrun.py \
  --statement /buyer/signed-checkpoint-statement.cose \
  --detached-signature /buyer/rekor-detached-signature.bin \
  --public-key-spki-der /buyer/rekor-public-key.spki.der \
  --out-dir /buyer/rekor-request-dry-run-001
~~~

The output directory MUST NOT already exist (no overwrites). Verify all
files before authorizing external publication. The request contains a digest,
signature and public key, but never the underlying COSE claim itself.
Still, a known-public digest can reveal a correlation with a public artifact.
A public key may link statements to the same organization or person. Do not
assume all metadata is private or free of identifying information.

Dry-run verification checks the **detached Rekor artifact signature** only.
It does not recheck that the COSE issuer statement's underlying authority,
consumption and reconciliation are true; that requires separate ProofRail
and independent provider evidence verification.

**The request has not been submitted to a live Rekor server, and server
algorithm policy might change.** The server implementation currently checks
for prehash capability (see sigstore/rekor-tiles
pkg/types/hashedrekord/hashedrekord.go), which is why pure Ed25519 was
replaced with ECDSA P-256 here. Use a separately permissioned service-acceptance
check before treating the body as supported.

**No automatic upload step follows this command.** Actual submission must
be separately authorized and implemented after confirming Rekor's currently
active service, acceptance policy, verified log trust keys, checkpoint and
inclusion-proof verification, and retention of the returned transparency
bundle. The public log is permanent; treat publishing as irreversible.

## 3. Rollback/fork acceptance gates

A real acceptance path needs ALL these distinct checks:

1. Locally valid authority + consumed-once proof + provider reconciliation
   against trusted, current provider state (not simulated fixture digests).
2. An issuer statement signed with a pinned key binding an exact checkpoint
   to that execution evidence, verified against the original ledger.
3. A Rekor v2 inclusion proof and log checkpoint verified against keys from
   authenticated Sigstore TrustedRoot (with correct shard/key validity).
4. A buyer-held high-water state securely updated *after* those proofs,
   including expected next sequence and previous checkpoint digest.
5. Protection/replication of the buyer high-water state to detect a
   **simultaneous rollback** of both issuer and buyer databases.
6. For cross-buyer fork discovery: an independent log monitor/gossip/checker
   that can compare the visible stream across relevant tiled log entries.

Only #2 and **buyer-local core of #4** are partially exercised here;
nothing claims real Rekor inclusion. #1 remains the existing ProofRail
research/pilot work. #3, #5 and #6 are not implemented here.

## Security test matrix

- Genuine signed genesis + exact next checkpoint: buyer local state advances.
- Duplicate valid checkpoint: idempotent, no new authority granted.
- Valid older checkpoint + its matching older ledger: rollback rejected if
  buyer still holds the later state.
- Same sequence with a different signed checkpoint: fork rejected.
- Gap, wrong predecessor, wrong issuer public key, wrong domain or changed
  expected action commitment: rejected.
- Concurrent updates: exactly one advance, remaining attempts idempotent.
- Rollback **of buyer DB itself**: succeeds and is demonstrated as a negative
  capability boundary.
- Rekor request SHA-256 digest, raw detached signature, ECDSA P-256 DER
  public key format match documented v2 shape; forged key/signature and
  unsupported pure Ed25519 key refused.
- Dry-run produces no side effects and refuses overwriting previous output.

## Decisions NOT bypassed

- No public Rekor publication has been authorized or executed.
- No draft merged, no branch protection changed, no release published.
- No production "latest" proof or compliant SCITT Receipt exists here.
- No third-party paid customer, independent witness or outside audit has
  been substituted with a local synthetic fixture.
