# ProofRail Adversarial Proof Matrix

The matrix defines observable failure behavior. A scenario passes only when it
denies, reconciles, or exposes tampering deterministically.

| Scenario | Attack | Required result | Proof surface |
| --- | --- | --- | --- |
| Valid permit | Present exact signed authority object | One execution, then `RECONCILED` | Permit registry and provider receipt |
| Expired permit | Execute at or after expiry | `permit_expired`; provider untouched | Permit verifier |
| Changed PR head | Replace bound external state | `state_root_changed` or provider head mismatch | State root and GitHub preflight |
| Changed policy | Activate a different policy root | `policy_root_changed` | Permit verifier |
| Changed approval | Alter scope or approval digest | `approval_scope_changed` | Evidence root and permit verifier |
| Permit replay | Reuse consumed permit or nonce | `permit_replayed`; no second call | Atomic replay registry |
| Learner promotion | Learner activates proposed policy | RBAC denial | Governor promotion gate |
| False merge success | Executor claims success; GitHub remains open | `RECONCILIATION_FAILED` | Independent provider GET |
| Ambiguous execution | Timeout during merge and reconciliation | Permit remains consumed; no retry | Replay registry and receipt |
| Ledger mutation | Edit a prior outcome | Entry hash and checkpoint root mismatch | Ledger verifier and Merkle checkpoint |
| Checkpoint mutation | Edit signed root or count | Ed25519 verification failure | Checkpoint verifier |
| Record deletion | Remove a ledger line | Causal link, count, last hash, or root mismatch | Ledger and checkpoint verifier |
| Record reordering | Reorder valid records | Causal link and Merkle root mismatch | Ledger and checkpoint verifier |
| Wrong checkpoint key | Verify with unrelated public key | Signature failure | Checkpoint verifier |

## Demo Mapping

`proofrail demo github-merge-authority` executes and records:

1. valid permit -> execution allowed
2. changed PR head -> denied
3. consumed permit replay -> denied
4. false merge success -> reconciliation failed
5. learner promotion attempt -> denied
6. ledger mutation -> tamper detected

The demo uses an offline simulated provider. It never merges a real pull
request. Its artifacts are designed to test the authority protocol, not to
claim a production GitHub action occurred.

## Independent Reproduction

```bash
proofrail demo github-merge-authority --out-dir proofrail-demo
proofrail ledger verify proofrail-demo/proofrail-ledger.jsonl
proofrail ledger verify proofrail-demo/tampered-ledger.jsonl
```

The first ledger must verify. The tampered ledger must fail. The generated
checkpoint public key can then verify the checkpoint against the original
ledger.

The repository also includes a frozen copy at
`examples/github-merge-authority-artifact/` for verification without first
running the generator.
