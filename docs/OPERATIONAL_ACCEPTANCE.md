# Operational acceptance evidence

The 0.6.1 candidate rejects an already-merged pull request whose head differs from the signed effect. Replay trust is rechecked while the SQLite write transaction is held, preventing distinct concurrent permits from spending one prior checkpoint. The regression deliberately synchronizes two verification reads before either claim can write.

Run `python -m unittest discover -s tests -v` after installation.

## Recovery drill

```
python scripts/operational_recovery_drill.py prepare --bundle /tmp/new-recovery-bundle
python scripts/operational_recovery_drill.py restore --bundle /tmp/new-recovery-bundle --output /tmp/new-restored-state
```

Use fresh destination directories. Preparation generates synthetic keys in memory, commits a claim in a child process, forces exit 137, then takes an integrity-checked online SQLite backup. No private keys enter the backup. Restoration verifies file hashes and a signed checkpoint, rejects stale state and spent authority, and consumes a fresh preissued permit exactly once. `Cross-runner operational restoration` transfers this backup through a 30-day Actions artifact to a separate fresh runner and records observed restoration time and claim loss.

This demonstrates restoration of synthetic replay authority state. It does not certify production key recovery, complete ledger/observation restoration, an independently administered retention domain, or production RTO/RPO. Establish trusted public keys out of band; bundled keys demonstrate consistency, not external identity. Production backup/quiescence and checkpoint publication must preserve one consistent state boundary.

## Separate independent gates

The public runtime pilot and ESRM Gate 1B have distinct targets. The current Gate 1B handoff metadata lives at commit `55fa2c47608287e9b22d09c7982d9949b079a232`, while its semantic comparison is source `651f34bb9768dfafd53ede612ef01c9a01bd534d` against derivation `f81f0ca55b065d60e8c8439eb85d6358c608a45b`. Earlier marker files inside the frozen target mention the superseded `a0a168e925ca28fc95967980fd99f3116f9f36ec`; the V2 handoff explicitly supersedes that target. Do not silently retarget the frozen artifacts or treat runtime repair tests as semantic review.

External review must preserve the original independent report, reviewer competence/conflict evidence, all Sections 22–40, exact inputs, findings and dispositions. Project-authored reports, additional internal tests and automated security scans cannot by themselves close that gate.
