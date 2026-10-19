# Comparative integration and outside review scope

## Decision being tested

Does ProofRail provide a useful advantage over a conventional signed-grant,
durable-claim and provider-observation composition for one exact GitHub merge?
This is a technical evaluation, not an acquisition valuation or certification.

## Runnable integration

```bash
python -m pip install .
python benchmarks/comparative_github.py --samples 100 --seed 20261012 --output comparison.json
python -m unittest discover -s tests -v
```

The harness starts a loopback HTTP server using an ephemeral port. It stores
provider effects in a separate SQLite database and reads that database directly
to check actual outcomes. It uses a synthetic token and makes no external GitHub
requests. Temporary databases and in-memory private keys are destroyed on exit.
Outputs retain case outcomes, error details, environment, hashes and all timing
samples. Exit 1 indicates an unexpected result. No API key or external account is
required.

The conventional baseline implements RFC 8785 canonical signed grants using
Ed25519, expiry, current identity/policy/evidence/state comparison, approval
binding, atomic nonce/hash claims, and the same GitHub adapter as ProofRail.
It does not call ProofRail's permit/signature/replay-claim code. It is a local
reference implementation, not Cerbos, Cedar, Authzed or Temporal.

Using the same adapter isolates the authority-layer integration and avoids
giving one implementation a weaker provider check. It also creates correlated
adapter risk: this comparison cannot independently validate that adapter.

## Cases and success criteria

| Scenario | Expected evidence |
| --- | --- |
| Normal request | One real fixture effect; success |
| Expired permit | No effect; rejected |
| Policy changed before gate | No effect; rejected |
| Identity changed before gate | No effect; rejected |
| Signature tampering | No effect; rejected |
| Replay | One effect total; repeated authority rejected |
| Provider head changed | No effect; no success |
| Response lost after commit | Exactly one effect; independently read outcome |
| Competing actor merges changed head | Competing effect observed; no false success |
| Interruption after claim, before write | No effect; no retry using spent authority |
| Four concurrent uses of one permit | One effect and one successful caller |
| Revocation after local check, before HTTP write | Known limitation: effect still occurs |

The last row is a counterexample, not a security pass. An interruption is an
exception injection, not a killed process. See the separate operational recovery
drill for the narrower existing forced-exit and restoration exercise.

## Measurement boundaries

- Five warmups per implementation; seeded randomized order within each pair.
- Timing begins after permit minting and provider-fixture setup; ends after gate
  execution and adapter reconciliation. It includes local HTTP and SQLite writes.
- Same host and synthetic action; serial benchmark, not throughput or load.
- Each gate reuses its growing registry across cases and measurements.
- Base ProofRail permits only: no trust checkpoints, quorum observation, external
  anchors, proof export, KMS, human approvals or portable-proof verification in the
  timing comparison. Do not extrapolate timing to those features.
- Conventional baseline initialization is outside timing; ProofRail's repeated
  schema checks and replay-root calculation remain inside its public API call.
- Integration effort, security superiority, production reliability, live GitHub
  behavior, total cost and market demand are unmeasured.
- The same assistant authored both the harness and the candidate repairs. This
  is not an independent experiment or third-party review.

## Outside-review work order (uncommissioned)

Status: READY FOR SCOPING; NO REVIEWER ENGAGED; NO FEES AUTHORIZED.

Request a narrowly scoped runtime correctness and comparison-methodology review.
Start with a scoping response stating proposed effort, price, availability and
conflicts. No work or payment should begin without a separately accepted scope.

Required reviewer outputs:

1. Identity, relevant protocol/distributed-systems experience and conflicts;
   confirm no authorship of this implementation, repairs or comparison.
2. Exact commit/tree/harness hashes, environment, unedited command logs and raw
   data from an independent machine; record assistance and failed attempts.
3. Independently authored counterexamples for claim atomicity, stale authority,
   provider-state attribution, expiry, rollback and interrupted execution.
4. Review the baseline for missing protections, asymmetric costs and correlated
   fixture/adapter bugs. Propose a corrected baseline when warranted.
5. Classify every proposed guarantee as supported, contradicted, conditional or
   untested; state assumptions and severity for each defect.
6. Explain whether any demonstrated advantage is reusable beyond this fixture,
   and whether the extra evidence features warrant a separate comparison.

Prioritize these files: `proofrail/permit.py`, `proofrail/server.py`,
`proofrail/trust.py`, `integrations/openclaw/github_adapter.py`,
`tests/test_execution_admission.py`, `tests/test_reconciliation_exact_effect.py`,
and `benchmarks/comparative_github.py`.

Explicit questions:

- Is the exact effect actually bound, or merely a resource identifier/head?
- Does a merged-head observation establish causation or only matching state?
- Can stale role/policy/expiry pass after local admission under concurrency?
- Can state restoration or ambiguous writes restore usable authority?
- Are success receipts and UNKNOWN outcomes interpreted safely by callers?
- What bypasses remain if an agent retains the underlying provider credential?
- Are checkpoint-mode semantics materially different from this base-mode test?

Exclude universal revocation claims, acquisition valuations, patent opinions,
commercial endorsements and production certification. Preserve reviewer findings
verbatim, including findings against the baseline and the project's hypothesis.

## Separate frozen semantic gate

The existing Gate 1B packet uses historical source and derivation commits and
requires a source-fidelity classification of Sections 22–40. This runtime review
does not close Gate 1B. Its frozen source must not be replaced with these results.
No reviewer is named in the inspected selection document or assigned to PR #24.

## Shortlist for scoping, not endorsements

- Trail of Bits: protocol/code analysis and cryptography practice.
  https://trailofbits.com/services/software-assurance/
  https://trailofbits.com/services/cryptography
  Official inquiry: https://trailofbits.com/contact/
- NCC Group: source-code and cryptographic assessment capability.
  https://www.nccgroup.com/technical-assurance/application-security/code-review/
  https://www.nccgroup.com/research/zcash-cryptography-and-code-review/

These sources establish service capability only. Availability, affordability,
independence, willingness to assess this pilot, and any grant-funded eligibility
have not been established. No firm has been contacted or commissioned.
