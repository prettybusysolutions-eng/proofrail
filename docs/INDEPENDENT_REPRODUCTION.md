# ProofRail Independent Reproduction

The committed `examples/reproduce_artifact/` bundle is a portable verification
contract. It contains a signed manifest that commits every proof file and its
expected verdict.

From a clean clone:

```bash
pip install -e .
proofrail reproduce examples/reproduce_artifact/
```

ProofRail v0.6 also packages the authority schemas in built wheels, so the same
reproduction command works after a standard non-editable package install.

The command independently checks:

- all repository schemas are valid Draft 2020-12 schemas
- the reproduction manifest signature and every declared file hash
- valid and intentionally invalid permits against exact authority context
- a signed permit-consumption receipt, replay-registry claim, and pre/post
  trust-checkpoint chain
- ledger hash-chain and Merkle integrity
- checkpoint signature and ledger commitment
- external anchor signature, trust-checkpoint binding, and ledger continuity
- trust-checkpoint signature
- deterministic validation-report hash
- expected failure of the tampered ledger

Exit code `0` means every expected result was reproduced. Exit code `4` means
one or more checks failed.

## Trust Boundary

The bundle is independently replayable, not independently authored. Its
verification keys are shipped with the artifact so a stranger can reproduce
the evidence. To establish external identity rather than internal consistency,
the manifest and anchor public keys must be obtained through an independently
trusted channel.
