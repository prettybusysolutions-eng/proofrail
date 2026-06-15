# ProofRail

**Single-use cryptographic authority for autonomous execution.**

ProofRail issues signed permits that bind an autonomous agent to one exact
action, target, evidence set, policy state, approval, and expected outcome.
Authority is consumed before the side effect. Provider state is checked after
execution. Changed or ambiguous conditions fail closed.

```text
intent -> evidence -> policy -> approval -> signed permit
       -> one execution -> provider observation -> audit proof
```

ProofRail currently demonstrates the same authority model across two
high-consequence domains:

1. merging an exact GitHub pull-request head
2. applying an exact SQLite schema migration to a bound database instance

This supports a narrow, testable claim: the authority primitive is not tied to
GitHub. It does not claim that every execution domain is already supported or
that the pilot components are production infrastructure.

## Why It Exists

An audit log can show what an agent says it did. It does not necessarily prove:

- who authorized the action
- which evidence and policy justified it
- whether approval matched the state that was actually changed
- whether authority was reused
- whether the provider confirms the claimed outcome
- whether history was replaced after the fact

ProofRail makes those conditions part of the execution boundary.

## What Is Enforced

- RFC 8785 canonical records and Ed25519 signatures
- identity, evidence, policy, state, and approval roots
- exact-effect permits with nonce and expiry
- atomic permit consumption before side effects
- state-drift and replay denial
- role separation between verification, execution, learning, and governance
- provider observation before claimed success becomes reconciled truth
- non-retryable handling of ambiguous outcomes
- hash-chained ledgers, signed Merkle checkpoints, and external anchors
- deterministic adversarial and reproduction artifacts

The GitHub permit binds repository, pull request, expected head SHA, and merge
method. The database permit binds exact SQL, pre/post schema roots, target
version, and the local path/device/inode identity of the SQLite file.

## Verify It Yourself

Requirements: Python 3.11 or newer.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/proofrail reproduce examples/reproduce_artifact/
.venv/bin/python -m unittest discover -s tests -v
```

Expected results:

- the committed reproduction artifact exits `0`
- all tests pass
- a modified declared artifact file exits `4`

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for the complete ten-minute
verification and break-test sequence.

## Evidence Included

- `VALIDATION_REPORT.md`: generated adversarial results
- `validation-results.json`: machine-readable validation evidence
- `examples/reproduce_artifact/`: signed portable proof bundle
- `docs/INDEPENDENT_REPRODUCTION_TRIAL.md`: clean-environment replay record
- `docs/KNOWN_LIMITATIONS.md`: preserved trust boundaries and residual risks
- `docs/SECOND_EXECUTION_DOMAIN.md`: database migration authority model

Current evidence demonstrates:

- 13/13 current adversarial expectations reproduced
- authentic portable artifact accepted
- substituted artifact rejected
- consumed permit replay denied
- signed authority mutation denied
- changed provider or database state denied
- false executor success denied by observation
- anchored ledger-tail truncation detected
- the same permit architecture applied to two execution domains

The validation is internally authored and independently replayable. It has not
yet been independently authored or validated by a third party.

## Open Protocol Direction

ProofRail is being developed as a vendor-neutral runtime authority protocol
for autonomous actions. The Action Authority Envelope v1 draft is designed to
complement agent communication, tool, observability, policy, and attestation
standards rather than replace them.

The open-source evaluation path is deliberately falsifiable. An evaluator
should be able to:

1. install ProofRail without hidden dependencies
2. reproduce the signed evidence artifact
3. run the adversarial tests
4. modify state or evidence and observe fail-closed behavior
5. inspect every trust dependency and known limitation
6. identify where the protocol's trust assumptions or guarantees fail

Start with:

- [docs/OPEN_STANDARD_DIRECTION.md](docs/OPEN_STANDARD_DIRECTION.md)
- [docs/ACTION_AUTHORITY_ENVELOPE_V1.md](docs/ACTION_AUTHORITY_ENVELOPE_V1.md)
- [docs/MCP_AUTHORITY_PROFILE_V1.md](docs/MCP_AUTHORITY_PROFILE_V1.md)
- [docs/MCP_GATE2_VALIDATION_REPORT.md](docs/MCP_GATE2_VALIDATION_REPORT.md)
- [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md)
- [SECURITY.md](SECURITY.md)

## Pilot Boundaries

ProofRail is not yet:

- third-party validated
- a hosted managed service
- a replacement for identity providers, KMS/HSM, database backup, or GitHub
  branch protection
- a multi-node consensus system
- proven against production database workloads
- market validated by a paid customer

The local server uses pilot-grade SQLite and JSONL storage. Production use
requires buyer-controlled identity, key custody, retention, observation
sources, and deployment hardening.

## Repository Map

- `proofrail/`: authority, permit, trust, checkpoint, anchor, and reproduction
  logic
- `integrations/openclaw/`: governed execution adapters
- `adversarial/`: replayable attack suites
- `tests/`: behavioral and security regression tests
- `schemas/`: Draft 2020-12 evidence contracts
- `examples/`: offline demonstrations and portable reproduction bundle
- `docs/`: protocol, security model, trust boundaries, and evaluation material

## Product Line

**ProofRail issues single-use cryptographic permits for autonomous agents,
binding exact authority to exact actions across code, infrastructure, and data
changes.**

Code and data changes are demonstrated today. Infrastructure changes are the
intended substrate direction, not a currently verified adapter claim.

## License

Apache License 2.0. See [LICENSE](LICENSE).
