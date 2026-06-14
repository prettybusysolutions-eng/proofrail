# ProofRail Authority Object

**ProofRail turns authorization into a single-use cryptographic authority
object for autonomous execution.**

Version 0.3 makes that authority independently replayable and verifiable. A
stranger can inspect the evidence graph, recompute every record hash, verify
the causal chain, recompute the Merkle checkpoint root, and verify the
checkpoint signature without trusting the executor's narration.

## Authority Chain

```text
Intent
  -> identity root
  -> evidence root
  -> policy root
  -> external state root
  -> signed permit
  -> atomic permit consumption
  -> exact provider action
  -> independent reconciliation
  -> append-only receipt
  -> signed Merkle checkpoint
```

A GitHub merge permit binds:

- authorized verifier identity
- exact evidence and approval scope
- exact active policy
- exact observed GitHub state
- repository and pull request number
- expected PR head SHA
- merge method
- nonce, issue time, and expiry

Changed state invalidates the permit. Consumption spends it permanently.
Executor success is only a claim until the reconciler independently observes
the provider state.

## External Verification

The portable artifact set is:

- `proofrail-ledger.jsonl`: append-only evidence graph
- `proofrail-checkpoint.json`: signed Merkle commitment
- checkpoint public key: independently distributed verifier key
- optional transcript: human-readable interpretation, never the source of truth

Verification order:

1. Parse every JSONL record.
2. Recompute each entry or record hash.
3. Verify every `previous_hash` causal link.
4. Recompute the domain-separated Merkle tree.
5. Verify the checkpoint's Ed25519 signature.
6. Compare entry count, first hash, last hash, and Merkle root.

## Merkle Construction

Records are serialized with RFC 8785 JSON Canonicalization Scheme.

```text
leaf = SHA256(0x00 || canonical_record)
node = SHA256(0x01 || left || right)
```

An odd final node is duplicated. An empty ledger root is `SHA256("")`.
The prefix bytes separate leaves from internal nodes.

## CLI

Generate the complete offline proof:

```bash
proofrail demo github-merge-authority
```

Export and verify a ledger:

```bash
proofrail ledger export --out proofrail-ledger.jsonl
proofrail ledger verify proofrail-ledger.jsonl
```

Create and verify a checkpoint:

```bash
export PROOFRAIL_CHECKPOINT_PRIVATE_KEY="<32-byte Ed25519 key, hex or base64url>"
proofrail checkpoint create

export PROOFRAIL_CHECKPOINT_PUBLIC_KEY="<32-byte Ed25519 public key, hex or base64url>"
proofrail checkpoint verify
```

Defaults:

- ledger export source: `ledger/events.jsonl`
- checkpoint ledger: `proofrail-ledger.jsonl`
- checkpoint: `proofrail-checkpoint.json`
- demo output: `proofrail-demo/`

Historical unhashed ledger records are never rewritten. Export wraps each
legacy record as a payload inside a new hash-chained envelope and records the
canonical source-record digest.

## Trust Statement

A valid checkpoint proves that the holder of the checkpoint key signed a
commitment to an exact ledger. It does not by itself prove that the key holder
was authorized. External users must obtain the public key through an
independent trusted channel or identity-root chain.

The transcript is explanatory. The JSONL ledger, hashes, signature, public key,
and independently observed provider state are the proof.

A frozen proof bundle is available at
`examples/github-merge-authority-artifact/`. The test suite verifies its
checkpoint and rejects the included tampered ledger.

## Product Claim

**Anyone can independently verify that an autonomous agent action was
authorized, scoped, consumed once, reconciled against external reality, and
preserved in a tamper-evident evidence graph.**
