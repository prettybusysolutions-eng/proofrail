# External containment design — OPEN implementation gate

Date: 2026-10-20. This is a design, not an implemented or validated sandbox.
Baseline reviewed: 42e3c1aa21f18d2b41d3f439233ba3cc0c58b4d3 (PR #11).

## Reproduced failures

A finite detached child retaining the acceptance stdout pipe made a 1-second
limit return after 4.17 seconds (timed_out=true). A detached child with output
redirected to /dev/null let the acceptance command return 0 while a fixture file
was absent at return and appeared 1.5 seconds later. Both probes used disposable
paths and finite-lived children. These reproduce the two outstanding mechanisms;
they do not claim to exhaustively reproduce the reviewer's exact fixtures.

## Selected design

Use a dedicated Linux sandbox worker backed by an independently controlled
container runtime and cgroup v2. The trusted controller owns the runtime socket,
consumption ledger, trust keys and immutable inputs; none are mounted in the
sandbox. Job callers cannot select images, mounts, privileges or runtime arguments.
Cgroups alone restrict lifetime/resources, not filesystem or network authority.

Each job uses a fresh scratch repository copied from the approved base. Never
mount the live repository or host home. Pin the image digest; read-only root;
unprivileged UID; drop capabilities; no new privileges; default deny network;
private HOME/TMP; fixed environment; CPU/memory/PID/output-byte limits. Require
actual cgroup resource support at startup and fail closed if absent. Protect the
host/controller with a different OS identity and no worker-writable installation.

Run both worker and acceptance commands through the same trusted containment
interface. Use separate disposable sandbox instances for the worker and tests:
terminate the entire worker boundary before inspecting its output; then run tests
against the resulting scratch snapshot. Output goes to quota-limited regular files,
not inherited pipes. File logging fixes the pipe-lifetime coupling but does not
establish process containment or prevent disk exhaustion without quotas.

The controller uses a monotonic absolute deadline. On success, timeout or error,
it asks the runtime to terminate the whole cgroup including descendants, then
requires `cgroup.events` populated=0 before progressing. The sandbox cannot move
itself into another cgroup or access the host runtime API. If termination or empty
confirmation fails, quarantine the scratch tree and emit no successful attestation.
A host watchdog handles controller death; restart reconciliation treats unfinished
jobs as quarantined until the runtime independently confirms they are empty.

Only after both worker and test boundaries are empty: snapshot control files and
working tree from the trusted controller, compare to expected scope, and create
an immutable candidate artifact. Atomically publish the reviewed candidate using
a base-version check. The host repository never receives writes from a sandbox
process; later attestation refers to the immutable candidate, not mutable scratch.

## Required validation before replacing the current runner

- Timeout, normal exit, failure and controller death with detached grandchildren.
- Grandchild retains stdout/stderr: wall-clock bound remains timeout plus a declared
  cleanup grace; log files stay within quota; no blocking pipe read.
- Grandchild schedules a late write: boundary is empty before snapshot, and neither
  scratch nor published candidate changes afterward.
- Resource-limit availability is verified; unsupported cgroup/runtime configuration
  denies admission rather than falling back to same-user subprocess execution.
- Host HOME, loader variables, credentials, trust stores and runtime socket remain
  inaccessible. No mutable host repository mount or cgroup migration access.
- Acceptance tests change git config/hooks/info/replace refs: fail before publication.
- Runtime unavailable, kill fails, deadline expires during cleanup, controller restarts,
  output disk fills, concurrent publication: no success and no blind restart.

## This execution environment

No Docker or Podman executable was found. /sys/fs/cgroup is mounted read-only.
An attempted Bubblewrap user/PID namespace setup returned Operation not permitted.
An attempted user systemd invocation reported no bus. No controls were weakened or
bypassed. A suitable dedicated host is needed for implementation and live validation;
mocking this boundary would not close either blocker.

## Primary references

- Linux cgroup v2 (`cgroup.kill`, `cgroup.events`):
  https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
- Docker rootless resource-limit requirements:
  https://docs.docker.com/engine/security/rootless/tips/
- Container controls and limits:
  https://docs.docker.com/reference/cli/docker/container/run/

These references describe building blocks, not an endorsement of this unimplemented
design. Retain PR #11's draft status until the actual boundary survives the probes
and an independent reviewer assesses the exact new commit.

## Local validation record

Four added hardening tests passed: fake python on caller PATH, forbidden registry
variables, fresh home/temp plus minimal git environment, and post-test git control
mutation. The 161-test regression run was NOT green: the existing descendant
cleanup test errored on a replay claim. Isolated reruns of that same test failed
with a late child write on BOTH pristine 42e3c1a and the hardened version. This
runtime therefore cannot validate the old subreaper claim. The test is retained,
not skipped or relaxed. Full closure requires external containment and rerunning
the unchanged failure probes on the dedicated host.

## Interim fail-closed guard (2026-10-21)

The dispatcher now requires successful subreaper setup before recording a dispatch
claim or starting a worker. It also requires /proc/self/stat's PID to match
os.getpid(): the existing descendant scanner cannot work correctly against a proc
mount from a different PID namespace. Either failure exits with
`descendant_containment_unavailable`; there is no process_group_only fallback.
Authority already consumed by the adapter remains spent; this refusal does not
authorize an automatic retry.

A direct capability probe in the author runtime returned successful prctl setup,
but os.getpid() and /proc/self/stat reported different PIDs (5 and 3933 in that
probe). This corrects the earlier suggestion that denied subreaper setup alone
explained the observed failure. The mismatch invalidates the scanner's PID
comparison and is now explicitly rejected.

Tests force failed setup and mismatched PID views, assert no dispatch claim or
worker spawn on denial, and require the existing descendant test to either prove
cleanup or observe the exact refusal with an unchanged repository. Other errors
remain failures. The two external sandbox blockers remain open; this guard is
necessary host validation, not a replacement for the containment design.

## Adapter preflight before consumption

The adapter now invokes the same host-capability helper in an isolated, bounded
subprocess before consuming authority. A failed probe, timeout or launch error
returns `descendant_containment_unavailable` without spending the permit or
starting the dispatcher. The probe uses the adapter's interpreter, installed
helper path and fresh environment; it does not execute the job or change the
adapter process's subreaper state. The dispatcher still repeats the actual setup
before dispatch. A capability loss after preflight can therefore still leave an
already consumed permit spent; the preflight is not a reservation or retry grant.
