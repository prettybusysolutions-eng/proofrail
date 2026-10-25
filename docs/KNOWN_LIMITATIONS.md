# ProofRail Known Limitations

Applies to package version 0.6.1. (Earlier editions were headed v0.5; the
items below are unchanged by that correction.)

1. Deleting or rolling back both the replay registry and its independently
   retained signed trust checkpoint can erase replay evidence.
2. A standalone hash-chain verifier cannot detect valid tail truncation.
   ProofRail detects it only when an independently retained checkpoint or
   external anchor is available.
3. Wall-clock expiry still depends on trustworthy time until checkpoint epoch
   or monotonic counter progress invalidates the permit.
4. Compromise of enough governor keys to satisfy quorum can promote or roll
   back policy.
5. A compromised verifier key can mint valid-looking authority.
6. Compromise of enough observation keys to satisfy quorum can produce false
   reconciliation.
7. Local SQLite and JSONL storage are pilot components, not hardened
   multi-node consensus or WORM storage.
8. Header identity is suitable only behind an authenticated gateway.
9. The current validation suites are internally authored and independently
   replayable, but have not yet been executed by an independent third party.
10. GitHub merge and SQLite migration demonstrate two execution domains, but
    SQLite remains a local pilot adapter rather than a production database
    deployment target.
11. The pilot process currently holds the checkpoint signing key; production
    requires separate custody and independently retained checkpoints.
12. The command-line server does not configure independent observation sources;
    reconciliation fails closed until a quorum adapter is supplied.
13. The pilot control plane does not yet advance the ledger-checkpoint root
    automatically; it remains an explicit trust-checkpoint input.
14. Hardened permits bind one exact trust-checkpoint counter. Any checkpoint
    advance invalidates other outstanding permits, so the pilot serializes
    execution rather than supporting concurrent authority consumption.
15. The committed reproduction bundle is independently replayable but
    internally authored. External identity requires obtaining anchor and
    manifest public keys through an independently trusted channel and
    supplying them with `proofrail reproduce --trusted-keys DIR`. Without
    pinned keys, verification is `self_asserted` and a re-signed bundle
    verifies. The committed demo keys are derived from fixed byte patterns
    and must never be trusted for real evidence.
16. Database migration schema observation proves structural state and target
    version, not application-level data correctness or backward compatibility.
17. The local database-instance fingerprint is host-specific. In-place content
    replacement that preserves the same path, device, inode, schema, and
    version is outside schema-root reconciliation.
18. The pilot rechecks role, policy, and identity after acquiring its local
    execution lock. This rejects changes completed while waiting for that
    lock, but does not make governance changes and an external provider write
    atomic. A later revocation cannot cancel an already dispatched request.
    Multi-process fencing and provider-enforced revocation require additional
    design and evidence; the local lock is not a distributed revocation barrier.

19. Replay-registry initialization now uses an atomic hard link to publish a
    complete SQLite database only after both replay tables are present. This
    requires a local filesystem and permissions supporting same-filesystem
    hard-link creation. If `os.link` is unsupported or prohibited, a newly
    absent registry cannot be initialized and consumption fails closed. There
    is no non-atomic fallback. See
    [replay registry recovery](REPLAY_REGISTRY_RECOVERY.md).
20. Legacy deployments may contain an existing, incomplete replay-registry
    file after an older-version crash between file creation and schema setup.
    Earlier code could create missing tables automatically; this change
    deliberately refuses to repair an existing file because doing so might
    erase or misinterpret evidence of spent permits. An operator must verify
    and reconcile independently retained authority/consumption evidence before
    any explicit replacement or restart. This is an availability-breaking
    operational change; see the same recovery procedure.
