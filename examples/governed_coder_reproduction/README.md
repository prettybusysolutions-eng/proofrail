# Governed Coder Reproduction

This directory documents the local replay path for the ProofRail-governed `xzenia-coder` bridge.

The replay suite verifies:

- missing authority is denied before worker launch
- signed authority is consumed once before mutation
- replay is denied
- mutated scope is denied
- repo base drift is denied
- worker false success and failed tests are rejected by reconciliation
- expired authority is denied
- two concurrent consumers result in exactly one authority consumption

Run from the repo root:

```bash
python adversarial/governed_coder_suite.py
python examples/governed_coder_reproduction/verify.py
```

This verifier is offline. It exercises ProofRail authority and reconciliation
logic using temporary local repositories and does not call a live coding model.

`validation-result.json` records the internally authored validation boundary in
machine-readable form. It is not a production readiness claim.
