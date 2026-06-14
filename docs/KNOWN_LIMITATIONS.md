# ProofRail v0.5 Known Limitations

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
    manifest public keys through an independently trusted channel.
16. Database migration schema observation proves structural state and target
    version, not application-level data correctness or backward compatibility.
17. The local database-instance fingerprint is host-specific. In-place content
    replacement that preserves the same path, device, inode, schema, and
    version is outside schema-root reconciliation.
