# Replay-registry initialization and recovery

Status: draft operational guidance for the core atomic-publication change in PR #48. This is not a production incident procedure validated on live deployments.

## What changed

ProofRail spends single-use permits in a SQLite replay registry containing
`permit_claims` and `permit_events`. Previously, both `consume_permit` and
`migration._claim_permit` connected to a missing path, making an empty database
file visible, and then created the tables. During that interval a concurrent
reader could see an existing database with no `permit_claims` table.

`proofrail.trust.ensure_replay_registry` now constructs a complete database
in a private file in the registry directory, explicitly closes it, and uses a
same-directory atomic hard link to create the public path only if it is absent.
It does not overwrite an existing registry. All writers must continue to use
their normal SQLite transactions for actual permit consumption.

## Preflight before adopting the change

1. Confirm that the intended registry directory is on a filesystem supporting
   **atomic same-filesystem hard links** and that the service identity can create
   and remove its own staging files. Network and virtual filesystems may differ;
   do not assume POSIX hard-link semantics without testing the actual mount.
2. Back up the current registry using a SQLite-consistent snapshot mechanism.
   Preserve externally held signed trust checkpoints or anchors independently.
   Do not equate a filesystem copy of a live WAL-mode database with a consistent
   recoverable backup.
3. In an isolated maintenance window, exercise registry initialization and
   read-only replay checks on a **new disposable registry path** in the same
   filesystem and under the same service identity. Confirm both replay tables
   exist and no extra provider action is possible from the test.
4. Record the selected registry path and any corresponding checkpoints. Do not
   treat a change of path as permission to reset the replay history.

## Existing registry lacks one or both tables

A legacy crash may have left a SQLite file behind before schema creation.
Unlike the previous `CREATE TABLE IF NOT EXISTS` behavior, the new code
**fails closed** when an existing registry lacks its required schema.

1. Stop or fence all permit-consuming workers and provider dispatch paths.
2. Preserve the suspect database, associated WAL/SHM files if present, audit
   records, and available independently held checkpoints for review.
3. Inspect a **read-only copy** with an SQLite integrity check and schema
   inventory. Check records against trusted external replay/approval evidence.
4. Do **not** delete, truncate, or silently recreate an existing database
   merely because the file looks empty. Absence of tables is not sufficient
   proof that no authority has been spent or that the correct state can be
   reconstructed.
5. Resume only after an authorized operator has established a trustworthy
   recovery state. Restore from a consistency-verified backup that can be
   reconciled against independently retained monotonic state, or explicitly
   re-provision under a separately approved incident process if no prior
   consumption can be independently established. If that cannot be shown,
   leave permit consumption blocked and document the incident.

A rollback of the replay registry **and** every external checkpoint defeats
local replay protections; this change does not solve that threat.

## Hard links unavailable

If publication raises an `OSError` (for example, filesystem not supporting
hard links, permissions, or policy disallowing them), initialization fails
**before permit consumption**. This is an availability failure by design.

- Preserve the error, service identity and filesystem/mount details.
- Use a storage location with the required filesystem semantics after an
  authorized migration that preserves replay history and externally trusted
  checkpoints.
- Do **not** replace this publication step with a plain move/rename that could
  overwrite another publisher, or a file-creation step that makes an
  incomplete registry publicly visible.

## Crashes and abandoned staging files

A crash before publication can leave a hidden staging file. During a fenced
maintenance window, determine that no publisher remains active, preserve
forensic evidence if relevant, and remove only positively identified orphan
staging files. Never remove the published replay registry as part of staging
cleanup. A crash after publication leaves a complete SQLite schema, although
subsequent claims still require ordinary SQLite transaction verification.

## Dependency for the facility pilot

The facility pilot currently has a separate `Gateway._ensure_registry`
implementation because its feature branch predates this core helper. **After
PR #48 is merged and present in the pilot's base**, replace the pilot copy with
a call to `proofrail.trust.ensure_replay_registry`, run its process-race,
registry deletion/rollback, crash recovery and production-adapter tests, and
review schema compatibility. Do not change the pilot's ongoing classified
mutation-sweep baseline as part of this documentation work.
