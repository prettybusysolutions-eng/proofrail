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

## Host inspection for implementation (2026-10-21) — STOPPED at step 1

Baseline: 6ed04c27fa6fd0b153073ebc63460aac607e9a09. Read-only inspection of a
second execution host; no host setting was changed and no daemon was started.

| Check | Command | Observed |
|---|---|---|
| OS / kernel | `uname -srm`; `/etc/os-release` | Linux 6.18.44-fc-v139 x86_64; Ubuntu 24.04.5 LTS |
| Identity | `id` | uid=0 gid=0 (root); single OS identity for every process |
| cgroup layout | `stat -f /sys/fs/cgroup`; `/proc/self/mountinfo` | `/sys/fs/cgroup` is tmpfs with v1 hierarchies (cpu, cpuacct, cpuset, memory, pids, freezer, blkio, devices, systemd) |
| cgroup v2 | mount of `/sys/fs/cgroup/unified` | cgroup2 mounted (hybrid); `cgroup.controllers` = `hugetlb` only; `cgroup.subtree_control` empty |
| v2 kill/empty confirmation | `cgroup.kill`, `cgroup.events` | absent at the available v2 root; cpu/memory/pids not delegated to v2 |
| Container runtime | `command -v docker dockerd containerd ctr runc podman crun bwrap` | docker client 29.8.2, dockerd, containerd v2.3.6, ctr, runc 1.5.1 installed; podman, crun, bwrap absent |
| Runtime daemon / socket | `docker version`; socket paths | no running dockerd/containerd; no `/var/run/docker.sock` or containerd socket |
| systemd | `systemctl is-system-running` | offline (PID 1 is the host process API) |

Outcome: required isolation cannot be enforced here. The design needs cgroup v2
resource controllers with `cgroup.kill`/`cgroup.events`, an independently
controlled runtime, and a controller under a different OS identity. This host
provides v1-bound controllers, no running runtime, and a single root identity.
Starting a daemon in the same root container, remounting cgroups, or creating
identities would weaken or alter host controls, and a boundary validated under
those conditions would not close either blocker. Steps 2–6 were not started;
no containment code was added and no test was skipped or relaxed.

Prerequisites for a validation host: unified cgroup v2 with cpu, memory and pids
delegated to the controller's subtree (`cgroup.kill`, `cgroup.events`
available); a container runtime whose socket is owned by the controller
identity and inaccessible to the sandbox; a distinct unprivileged identity for
sandbox processes; and a filesystem supporting output-byte quotas.

## Emulated validation guest (2026-10-22) — PARTIAL, STOPPED

Baseline: 4014d0c (containment code unchanged since 6ed04c2). This attempt
established a disposable guest and checked kernel/runtime prerequisites. It did
**not** implement or validate containment. Timings below are **emulated**
(QEMU TCG, no hardware acceleration) and say nothing about production
performance.

### Outer host and guest construction

- Outer host: Linux 6.18.44-fc-v140 x86_64 (itself a VM; no `/dev/kvm`, no
  vmx/svm flags), 2 vCPUs, 7 GiB RAM. QEMU 8.2.2 (Ubuntu 1:8.2.2+ds-0ubuntu1.18).
- Image: `ubuntu-24.04-minimal-cloudimg-amd64.img` from
  `https://cloud-images.ubuntu.com/minimal/releases/noble/release/`,
  SHA-256 `b3296484e362ba2e713489a5de6225c719d9500962bde25d15f2f21e512c7658`,
  matched against the published `SHA256SUMS` (fetched over HTTPS; its GPG
  signature was not verified).
- Disk: qcow2 overlay (20 GiB virtual) on the unmodified base image.
- cloud-init seed: user `controller` (uid 1000, SSH key auth only, password
  login disabled), proxy CA bundle installed via `update-ca-certificates`,
  apt/environment proxy pointing at the outer host's egress proxy.
- Boot command:

```
qemu-system-x86_64 -name proofrail-validation -machine q35,accel=tcg -cpu max \
  -smp 2 -m 4096 -nographic -serial file:serial.log -monitor none \
  -drive file=guest.qcow2,if=virtio,format=qcow2 \
  -drive file=seed.img,if=virtio,format=raw \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:2222-:22 \
  -device virtio-net-pci,netdev=n0
```

- Boot to SSH + cloud-init completion: 202 s (emulated).
- The egress proxy rejects plain-HTTP forwarding (405), so the guest's apt
  sources were switched from `http://` to `https://archive.ubuntu.com`
  (apt signature verification unchanged). Package install: 6 min 42 s (emulated).

### Guest facts (queried from the guest)

| Item | Value |
|---|---|
| Kernel / OS | Linux 6.8.0-147-generic x86_64; Ubuntu 24.04.5 LTS |
| Resources | 2 vCPUs; 3914 MiB visible |
| Init | systemd 255 (255.4-1ubuntu8.18), state `running` |
| cgroup filesystem | `cgroup2fs` (unified, no v1 hierarchies) |
| Root `cgroup.controllers` | cpuset cpu io memory hugetlb pids rdma misc |
| Root `cgroup.subtree_control` | `cpu memory pids` before runtime install; `cpuset cpu io memory pids` after |
| `system.slice` controllers | cpuset cpu io memory pids |
| `cgroup.kill` / `cgroup.events` in a child cgroup | present / present |
| Runtime | podman 4.9.3 (rootful), crun 1.14.1 |
| Tools | git 2.43.0, Python 3.12.3 |
| Image | `docker.io/library/python:3.12-slim`, digest `sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2`, image ID `a33c10a97f11005523814c6eee013986119fe41f3122f444518117536675c8e1` |

### Prerequisite status

| Prerequisite | Status |
|---|---|
| Unified cgroup v2 with cpu, memory, pids delegated to child cgroups | VERIFIED (kernel/systemd level only) |
| `cgroup.kill` and `cgroup.events` available in child cgroups | VERIFIED (presence only; not exercised) |
| Container runtime installed, image pinned by digest | VERIFIED (installed and pulled; no container run) |
| Runtime socket owned by controller identity, inaccessible to sandbox | UNVERIFIED |
| Separate unprivileged sandbox identity; no access to controller secrets or state | UNVERIFIED |
| Restricted mounts (read-only root, disposable scratch only) | UNVERIFIED |
| Network denied by default | UNVERIFIED |
| CPU, memory and PID limits actually enforced | UNVERIFIED |
| Output-byte limits enforced on regular files | UNVERIFIED |
| Whole-boundary termination with confirmed populated=0 | UNVERIFIED |
| All failure probes in "Required validation" above | NOT RUN |

### Stopping point

The session's response was stopped by a safety classifier while it was
proceeding from the image pull toward the remaining checks. The image pull had
completed. The only explanation provided was this notice, quoted exactly:

> Your response above was stopped by a safety classifier — this is not a tool or
> API error. The rest of it was withheld, and tool calls in it that had not
> finished did not run.

No reason was given. An earlier response in this PR's work (2026-10-20, while
drafting an in-process supervisor helper) was stopped with the same notice and
no reason. Neither withheld output was reconstructed or retried in another form.
A reviewer should decide whether a materially different validation method
addresses whatever the rejection concerned.

### Shutdown

`sudo systemctl poweroff` in the guest; the serial log shows
`Reached target poweroff.target` and `reboot: Power down` (856 s guest uptime,
emulated). The QEMU process (PID 849) exited with status 0 after 10 s; no
process with executable `qemu-system-x86_64` remained. No guest state is kept
for later runs.

### Conclusion

A software-emulated Ubuntu 24.04 guest provides the kernel facilities the design
requires (unified cgroup v2 with delegated cpu/memory/pids, `cgroup.kill`,
`cgroup.events`) and a rootful container runtime. That shows suitable
facilities are available; it does **not** demonstrate containment. No
containment code was written, no probe was run, and both PR #11 blockers remain
open. PR #11 stays draft.
