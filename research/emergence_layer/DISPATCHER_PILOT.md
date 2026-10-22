# Controlled GitHub artifact pilot

Status: implementation and synthetic failure tests; NOT a deployed credential-owning
service, NOT independently reviewed, NOT a production release. The earlier live
connector trial in LIVE_GITHUB.md does not validate this new dispatcher's transport.

## Deliverable and enforcement boundary

`enforcing_dispatcher.py` validates a signed handoff against operator-pinned trust,
reserves authority in a separately retained journal, consumes the ProofRail claim,
and admits one exact artifact write. The service config fixes one repository,
trial branch and evidence path. Parent SHA and base tree must match GitHub before
writes. Trees contain one file; commits contain one parent; ref updates never force.
`dispatcher_cli.py` provides dispatch, read-only recover and local check commands.

GitHub's REST ref update is fast-forward-only, not compare-and-swap with an expected
head. A diverging concurrent writer fails; administrative ref rewinds remain an
external risk. Disable force pushes and deletions, restrict other writers, and use
a dedicated trial repository. These controls have NOT been configured by this PR.
References: https://docs.github.com/en/rest/git/refs and
https://docs.github.com/en/rest/git/trees (checked 2026-10-19).

The service owns the token; requesters must never run arbitrary code as its OS user
or supply its config. GitHub credentials grant repository-level Contents permission;
path restrictions are enforced by this dispatcher, not by GitHub token scope.
An administrator or compromised service can bypass local enforcement. No claim of
credential isolation has been demonstrated in a deployed environment.

## Installation and operator inputs

Start on an isolated Linux worker (Python 3.11 or 3.12). Initial sizing assumption:
one CPU, 512 MiB RAM, 1 GiB persistent storage, one operation at a time. These are
pilot allocations, not benchmarked capacity. Budget by measured wall time and
storage growth; no throughput, profitability or latency guarantee is established.

1. Install a pinned reviewed commit into a dedicated service-account checkout:
   `python -m pip install .` then work in `research/emergence_layer`.
2. Provision a short-lived GitHub App installation token restricted to the dedicated
   repository with Contents write. Keep token refresh outside the request path.
   Mount the token in a service-owned 0600 file; never put it in argv, the handoff,
   repository, logs or a review bundle. Authentication/expiry failures fail closed.
3. Generate a dedicated Ed25519 consumer key; store raw private bytes as hex in a
   service-owned 0600 file. Enroll issuer and sender public keys out of band.
   Do not reuse temporary fixture keys or copy trust from an untrusted request.
4. Select a registry path and a journal path on a separately retained volume.
   Initialize the journal ONCE, before accepting work:
   `python -c "from enforcing_dispatcher import Journal; Journal.initialize('/srv/proofrail-retained/dispatch.db')"`
   Never initialize an empty replacement during disaster recovery.
5. Create a service-owned 0600 JSON config using the schema example below. The
   authority digest, approval digest, issuer and roots must be independently
   enrolled for this exact approved operation. This pilot pins one authority per
   config; it has no self-service approval API or general multi-tenant server.
6. From a trusted worker, run:
   `python dispatcher_cli.py check --config /etc/proofrail/pilot.json`
   Then `python dispatcher_cli.py dispatch --config /etc/proofrail/pilot.json --handoff /srv/inbox/approved.json`.
   The check verifies local state only; it does not validate token permissions.
7. After an ambiguous result, invoke `recover` with the same config and handoff.
   Never automatically retry `dispatch` based on an exit code.

Example config (placeholders are intentionally invalid; no bundled secrets):

```json
{
  "repository": "OWNER/DEDICATED_REPO",
  "branch": "trial/emergence-pilot",
  "path": "evidence/approved.json",
  "registry_path": "/srv/proofrail/registry.db",
  "journal_path": "/srv/proofrail-retained/dispatch.db",
  "consumer_key_file": "/run/secrets/proofrail-consumer.hex",
  "consumer_key_id": "pilot-consumer",
  "github_token_file": "/run/secrets/github-installation-token",
  "trust": {
    "sender_public_b64": "ENROLLED_PUBLIC_KEY",
    "authority_public": "ENROLLED_PUBLIC_KEY",
    "authority_key_id": "ENROLLED_KEY_ID",
    "authority_digest": "PINNED_SIGNED_AUTHORITY_DIGEST",
    "issuer": {"principal_id": "ENROLLED_ISSUER", "role": "verifier"},
    "observer_public": "ENROLLED_PUBLIC_KEY",
    "observer_key_id": "ENROLLED_OBSERVER_KEY_ID",
    "roots": {"identity": "DIGEST", "evidence": "DIGEST", "policy": "DIGEST", "state": "DIGEST"},
    "approval_digest": "ENROLLED_APPROVAL_DIGEST"
  }
}
```

## Recovery checkpoints and limits

The retained journal records nonce, signed authority digest, binding, execution ID,
prepared request, consumption digest and the post-consumption replay-root snapshot.
Before admitting work, every retained prepared execution must still have its signed
consumption, shared permit claim and dispatch flag in the registry. Restoring an
older registry blocks admissions. A pre-consumption crash leaves an incomplete
reservation that blocks admissions until operator investigation. This deliberately
trades availability for no automatic replay. The root snapshot is audit metadata;
per-execution commitments enforce the restoration check as the registry grows.

Never delete reservations to restore availability. Preserve both stores, compare
with retained backups and provider evidence, restore missing execution records from
a trustworthy later backup, and re-run `check`. If those records cannot be restored,
keep the service blocked. A new authority is not a license to repeat an uncertain
effect: reconcile it first. A full journal scan currently costs O(number of runs).

Rolling back BOTH registry and journal, deletion of retained reservations by an
administrator, and disaster loss of the retained volume are NOT solved. A separately
administered monotonic anchor is still required to defend against that failure model.
Legacy trust-checkpoint-bearing authority remains rejected; this PR does not advance
ProofRail's checkpoint epoch/counter protocol or migrate deployed checkpoint stores.

Recovery performs GET requests only. It validates parent, exact file bytes, run ID
and consumption digest at the observed immutable commit, and that the commit's whole
tree equals the approved base tree plus exactly one regular 100644 file with those
bytes (complete recursive listings; a truncated listing blocks confirmation). Byte
equality alone would confirm a look-alike commit someone else wrote. A moved branch, unavailable
provider, incomplete preparation or mismatching content blocks confirmation; there
is no write retry or broad commit search. This is conservative reconciliation,
not a general exactly-once external transaction protocol.

## Paid pilot offer (proposed, not booked revenue)

One team, one isolated repository, one artifact type, two-week evaluation after
review and deployment gates close. Proposed fixed fee: $2,000, capped at 16 hours
of implementation/support. Proposed continuation: $500/month for evidence retention,
maintenance and a monthly recovery exercise, with hosting and expanded scopes priced
separately. These are offer hypotheses, not validated willingness to pay.

Deliver installation/configuration, approved-action demonstration, denied-action
negative controls, audit export, timeout reconciliation and rollback rehearsal.
Exclude merges, releases, production deployments, payments and arbitrary generated
code execution. No performance warranty or security certification is implied.

Record baseline and pilot measurements in `pilot_metrics.csv`: setup minutes,
request-to-confirmation seconds, human intervention minutes, result, recovery mode,
number of provider writes and buyer acceptance. Obtain the team's existing review
cost first; compare equivalent tasks. Stop the pilot if a denied action writes,
a restored permission can write twice, or recovery needs a blind retry. Proposed
usability targets: setup <=60 minutes and >=90% of valid trials without intervention;
these are acceptance targets to measure, not current results.

Go-live gates: independently reproduce/review exact commit; deploy constrained
credentials under the service user; confirm branch controls; perform one real
write/readback through this dispatcher; inject a real response-loss fault at a
controlled proxy; restore registry while retaining journal; record evidence and
buyer acceptance. All remain open until witnessed and recorded.
