# Facility intervention verification pilot

Status: **local, synthetic, author-run.** Nothing here is deployed. The only
automated side effect is creating a work order in a local HTTP simulator, and no
money moves. INDEPENDENT VALIDATION: NOT COMPLETED.

The pilot implements the first WRN vertical slice:

> problem → approved intervention → ProofRail-governed work-order creation →
> provider observation → independent outcome assessment → simulated settlement →
> portable evidence.

Execution reconciliation ("did the authorized digital action happen?") and
outcome verification ("did the agreed real-world condition result?") are separate
records and separate state machines. Neither implies the other. See
[docs/WRN_ARCHITECTURE.md](../../docs/WRN_ARCHITECTURE.md).

## Run it

You need Python 3.11+, a ProofRail checkout, and no network beyond `127.0.0.1`.

```sh
python -m venv .venv && . .venv/bin/activate
python -m pip install -e . -r pilots/facility_outcomes/requirements-dev.txt
python -m unittest discover -s tests -q                        # existing ProofRail suite
cd pilots/facility_outcomes && python -m pytest -q tests/ && cd -   # pilot suite
python pilots/facility_outcomes/run_pilot.py --out /tmp/wrn-pilot  # scenarios A-E
python pilots/facility_outcomes/verify_bundle.py /tmp/wrn-pilot/bundle-A
```

`run_pilot.py` prints each scenario's separated claims and the provider's
ground-truth order count, and writes `summary.json`. It exits non-zero if any
scenario does not match its expected outcome. `verify_bundle.py` checks a bundle
offline in five dimensions:

1. integrity;
2. authenticity;
3. authority validity;
4. provider-observed execution;
5. attested physical outcome.

Pass `--trusted-keys` with independently obtained keys to authenticate
both admission-time and export-time signing keys. An issuer removed from the
export-time roster still needs a separately trusted historical key. Missing pins
fail trusted verification; a bundle's own key list is not an independent trust
source. Without trusted pins, key trust is `self_asserted`.

**Consumption claim boundary:** `records/consumption.json` is a snapshot
of the local replay-registry rows. The gateway now signs
`records/consumption-attestation.json` after the registry claim commits and
before the provider write. The verifier checks the signature with the
historical gateway key and binds the attestation to the exact exported rows.
This authenticates a **gateway attestation**, not an independently witnessed
or durably retained registry history. It does not solve joint rollback or
ledger-tail truncation. An independently held checkpoint/anchor remains a
separate unsatisfied security gate.

## Layout

| File | Role |
|---|---|
| `contracts/*.schema.json` | Strict schemas for the ten pilot resources. Not named `schemas/`, because that would shadow ProofRail's package. |
| `records.py` | Canonical digests, Ed25519 signing (ProofRail primitives), principals, tenant-scoped identity roots |
| `policy.py` | Tenant policy; the plan and approval checks shared by the issuer and the gateway |
| `lifecycle.py` | Work state machine (source of truth for `docs/WRN_STATE_MACHINES.md`) |
| `store.py` | Tenant-scoped business store, compare-and-set work state, per-tenant audit chain |
| `proofrail_gateway.py` | Authority issuer, gateway (the only path to the provider create call), observer, provider client |
| `provider_simulator.py` | Real HTTP work-order provider with fault modes and a ground-truth counter |
| `outcome_verifier.py` | Qualified-inspection rules and verdicts |
| `settlement_simulator.py` | Simulated settlement eligibility |
| `pilot.py` | The tenant-scoped workflow, one call per step |
| `evidence_export.py`, `verify_bundle.py` | Portable case bundle and its offline verifier |
| `run_pilot.py` | The five handoff demonstrations |
| `fixtures.py`, `worker.py` | Synthetic world; one-shot admission process for crash and concurrency tests |
| `review_tools/` | Check-removal sweep; attack-matrix generator |

## Evidence of enforcement

- **Attack matrix:** [docs/WRN_ACCEPTANCE_GATES.md](../../docs/WRN_ACCEPTANCE_GATES.md),
  generated from a pytest run.
- **Check-removal sweep:** `python review_tools/mutate_checks.py OUT.json`
  disables each enforcement check in turn. The first run left 66 of 107 checks
  unenforced: boundary tests are refused by whichever layer fires first.
  `tests/test_check_reasons.py` pins each check to its own reason. **After
  adding those tests: 0 of 107 survive.** Every enforcement check in the pilot
  now has a test that fails when the check is removed. This does not find checks
  nobody wrote; the attack matrix and fault scenarios are for that.

## Limits

See [docs/WRN_THREAT_MODEL.md](../../docs/WRN_THREAT_MODEL.md) for findings F-1
to F-10 and limits L-1 to L-8. The main limits:

- **L-1:** a joint rollback of the replay registry and the business store allows
  a second provider call; provider idempotency is the backstop.
- **Keys:** they are generated per run and prove only test identities.
- **Physical outcomes:** these are attested, not proven.
- **Infrastructure:** SQLite on one node, a local simulator, and no API, UI,
  MCP, A2A or telemetry yet.
