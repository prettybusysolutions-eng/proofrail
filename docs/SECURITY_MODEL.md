# ProofRail Security Model

ProofRail constrains autonomous execution by binding one signed permit to exact
identity, evidence, policy, state, approval, effect, nonce, and expiry values.
It prevents execution only when every enforcement dependency remains intact.

## Security Properties

- The executor must verify a trusted verifier signature.
- Changed signed content invalidates a permit.
- A persistent replay registry spends each permit and nonce once.
- Role checks prevent learners and executors from minting or promoting policy.
- Provider state, not caller claims, determines reconciliation.
- Hash chains expose in-place history mutation.
- Signed checkpoints expose history replacement or truncation after anchoring.
- Signed trust checkpoints bind replay, ledger-checkpoint, and observation
  roots to a monotonic epoch and counter.
- M-of-N signed attestations constrain policy rollback and reconciliation.
- Signed external anchors expose valid ledger-tail truncation when retained
  independently from the ledger.
- Database migration permits bind the exact migration source and both pre- and
  post-migration schema roots.
- Database migration reconciliation uses a fresh read-only schema observation,
  not the executor's success claim.
- Local database migration permits bind the resolved path and device/inode
  fingerprint, and reject symlink or path-target replacement.

## Security Dependencies

- Verifier and checkpoint keys remain confidential and correctly distributed.
- Executor time is trustworthy enough to enforce expiry.
- Trust checkpoints are retained independently from replay state.
- Enough governor and observer keys remain independent and uncompromised.
- GitHub and quorum observation inputs are authentic.
- Independent checkpoints remain available outside the ledger writer.
- Anchor and manifest public keys are obtained through a trusted channel.

## Falsification Standard

A claim is considered falsified when an attack produces an unauthorized effect,
undetected historical rewrite, false reconciliation, or authority expansion
while satisfying the claim's stated assumptions. Validation failures remain in
the report as evidence; they are not relabeled as passes.
