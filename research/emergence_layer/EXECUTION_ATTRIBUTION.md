# Discovery: state agreement is not execution attribution

Date: 2026-10-19. Scope: local research integration on PR #29.

Historical stage report: the subsequent shared-registry and real GitHub trial
are recorded in LIVE_GITHUB.md. The local findings below remain reproducible;
statements about the then-separate registry describe the earlier stage.

## Reproduced counterexample

The original read-only acceptance bridge returns MATCH for a valid, freshly
signed observation of the expected bytes. That statement alone does not prove
which run created those bytes. It was documented state verification, not a
production authorization bypass; execution_authorized remained false.

The executable two-run case now demonstrates the distinction:

1. A consumes authority and writes the expected artifact to the destination.
2. B receives freshly signed authority for the same task and target.
3. B consumes its authority, durably marks dispatch, and its actual child
   process terminates before the destination write (exit 73).
4. The destination still has A's correct bytes.
5. A valid state observation bound to B's handoff yields legacy MATCH.
6. The execution verifier reads destination-recorded provenance and rejects
   A's execution ID as evidence for B, despite identical content.

Counterfactual mutation: bypass only execution-ID and consumption-digest checks,
leaving signature, authority, content, tenant, target and freshness validation
intact. The same evidence again returns MATCH. The test restores the checks
afterward. This isolates the contribution of the provenance binding in this
fixture; it is not a comparison with a commercial product or a novelty claim.

Reproducer:

```bash
cd research/emergence_layer
python -m pip install ../.. -r requirements-dev.txt
python -m pytest -q tests/test_execution_binding.py
```

## Implemented reference path

- `ExecutionLedger.consume`: holds a SQLite write transaction, checks the exact
  handoff through the existing ProofRail authority verifier, assigns an execution
  UUID, signs its consumption record, and atomically stores unique authority
  digest and nonce. It returns the record only after commit.
- `dispatch_local`: checks current caller-supplied trust and validity at admission,
  compares the stored binding, and atomically changes dispatch_started from 0 to
  1 before the effect. Once started, a second dispatch fails regardless of whether
  the first call returned. The handler supports only the explicit local artifact
  fixture action; there is no arbitrary command or generated-code execution.
- `LocalArtifactDestination`: atomically writes content, execution ID and full
  consumption-record digest in its own database, separate from the ledger.
  Tenant and target identify the artifact. Observation obtains run identity
  from stored destination state, never by echoing a caller-supplied execution ID.
- `verify_execution`: requires the persisted signed consumption record, binds
  it back to the handoff, validates observer signature and freshness, and checks
  destination provenance and content. Missing evidence stays UNCONFIRMED; wrong
  content is DIVERGED; foreign provenance is rejected.

Successful evidence checking still returns execution_authorized=false. Neither
a MATCH response nor an observation can create another execution or clear the
consumed-authority record. Repeated read-only verification is allowed.

Authority validity is checked at consumption/admission. Later readback may occur
after expiry: the verifier checks historical authority at the signed consumption
time and requires a fresh observation. An expired authority cannot start dispatch.

## Measured tests

The complete research suite passed 63 tests in 2.74 seconds locally. The existing
24-cell counterfactual output reproduced byte-for-byte. Execution tests add 21
cases, including:

| Challenge | Observed result |
|---|---|
| No consumption record | Rejected |
| Actual authorized fixture write | MATCH with stored provenance |
| Old state-only receipt used for execution | Rejected |
| Consumed, not dispatched | UNCONFIRMED |
| Same authority submitted twice | Second claim rejected |
| Eight concurrent consumers | One claim succeeds |
| Eight concurrent dispatchers | One dispatch and one destination operation |
| Validly signed changes to execution/provenance/target/tenant/observer | Rejected |
| Real process crash after dispatch marker, before effect | UNCONFIRMED; redispatch refused |
| Real process crash after destination commit | MATCH after reopening ledger; redispatch refused |
| B crashes before effect while A's identical bytes exist | B cannot claim A's effect |
| Readback after authority expires | Allowed for already consumed execution |
| Expiry before dispatch | No effect |
| Consumption-record tampering | Rejected by signature/hash verification |
| Other tenant readback | Artifact absent |
| Actual stored content changed | DIVERGED |

The two provenance checks have an explicit disabled-check negative control in
the two-run test. GitHub CI runs this suite on Python 3.11 and 3.12 and uploads
JUnit results alongside the original counterfactual JSON. Crash tests use POSIX
fork and os._exit; they do not test machine power loss or a distributed cluster.

## Precise trust boundary and remaining gates

This is an experimental local execution path using ProofRail's cryptographic
and authority verification functions. Its dedicated registry does not consume
production ProofRail permits. Sharing authority across registries, restoration
from stale backups, and cross-host replay prevention remain unresolved here.

The operator owns ledger signing keys, database files, clock, expected contract,
current policy roots, and observer enrollment. Trust objects are supplied by the
trusted caller; no live identity/revocation provider is queried. There is still
a gap between local admission and an external policy change. A hostile operator,
database administrator or enrolled observer can forge or destroy provenance.
The direct fixture apply method is trusted test infrastructure, not an exposed
authenticated API. Cross-tenant database queries are separated, but there is no
network tenant-authentication service.

SQLite destination writes are real local effects; no external provider was
called. The prototype does not establish exactly-once external execution,
irreversible business outcome correctness, production deployment, independent
validation, commercial demand or competitive superiority. If a later legitimate
run overwrites the artifact, current-state readback cannot settle the earlier
run; a production adapter needs immutable operation/version history.

Next gate: integrate one installed ProofRail consumption path and one real,
permissioned destination whose immutable operation or version records expose
the run binding. Repeat lost-response, substitution, stale-read, concurrency and
rollback tests against that actual provider before making deployment claims.
