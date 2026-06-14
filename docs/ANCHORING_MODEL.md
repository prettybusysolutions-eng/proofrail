# ProofRail External Anchoring Model

ProofRail v0.5.2 uses a signed local/file anchor as the first external
continuity primitive. The anchor commits one exact ledger state:

```text
ledger Merkle root
+ first and last ledger hashes
+ sequence range and entry count
+ trust checkpoint hash
+ creation time
+ anchor provider and reference
+ anchor signature
```

The anchor is useful only when it and its verification key are retained
independently from the mutable ledger. A ledger hash chain can detect rewritten
records, but it cannot detect deletion of a valid tail by itself. Comparing the
truncated ledger to an independently retained anchor exposes the missing
history.

## Local/File Provider

The v0.5.2 provider is `local-file`. `proofrail anchor create` writes:

- the signed anchor JSON
- a separate Ed25519 public-key file referenced by the anchor

For the full authority chain, pass `--trust-checkpoint`. If omitted, the anchor
records `trust_checkpoint_present: false` and binds a domain-separated absence
digest rather than pretending a trust checkpoint was supplied.

This proves the mechanism without blockchain, hosting, wallets, or a remote
transparency service. Production deployments should retain anchors and trusted
public keys in a separately administered WORM store, transparency log, or
equivalent independent system.

## Boundary

An anchor makes rewrite and truncation detectable; it does not make storage
immutable. An attacker who can replace the ledger, anchor, and every trusted
copy of the verification key can replace history. Anchor custody and
independent retention remain governance responsibilities.
