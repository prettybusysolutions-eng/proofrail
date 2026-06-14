# ProofRail v0.5.1 Trust Elimination

Version 0.5.1 hardens the assumptions exposed by adversarial validation.

## Trust Checkpoint

A signed trust checkpoint commits:

```text
replay root
+ ledger checkpoint root
+ observation root
+ checkpoint epoch
+ monotonic counter
+ previous checkpoint hash
```

Hardened permits bind the trust checkpoint record hash, replay root,
observation root, minimum epoch, and exact counter. Before consumption, the
executor verifies the checkpoint signature and recomputes the replay root.
After consumption, the old checkpoint no longer matches until an authorized
checkpoint signer advances it. This deliberately fails closed after an
interrupted checkpoint update.

## Quorum

Observation and governor decisions use distinct signed attestations. ProofRail
groups valid attestations by their signed statement hash and accepts only a
single group meeting the configured M-of-N threshold. A signer that attests to
conflicting statements is excluded, and conflicting groups that each meet the
threshold fail closed.

The pilot proof uses 2-of-3:

- one compromised observer cannot create a false reconciliation
- one governor cannot roll policy backward

## Remaining Boundary

ProofRail cannot remove trust entirely. If an attacker controls enough quorum
keys, or rolls back both protected state and every independently retained
checkpoint, the current model cannot distinguish the attack from authorized
history. Wall-clock expiry also remains a time-source dependency until epoch or
counter progress invalidates the permit.
