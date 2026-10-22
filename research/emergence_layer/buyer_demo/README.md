# Buyer demonstration: an AI workflow writes only the artifact you approved

Status: reproducible local demonstration. NOT a GitHub deployment, NOT independently
reviewed, NOT a production release. The go-live gates in
[../DISPATCHER_PILOT.md](../DISPATCHER_PILOT.md) remain open.

## What it shows

A reporting agent prepares a weekly report. A person approves those exact bytes for
one repository, branch, path and parent commit. The unmodified pilot dispatcher
(`enforcing_dispatcher.Dispatcher`) then does the following.

| Step | What happens | Expected outcome |
|---|---|---|
| 1 | Approve one exact artifact (SHA-256 of the text, target, parent commit, 1-hour expiry) | Signed approval |
| 2a | Report text altered after the agent signed it | `REFUSED`: signature check; no provider call |
| 2b | Agent re-signs altered text with its own valid key | `REFUSED`: `predicate_not_authorized`; no provider call |
| 3 | Approved text dispatched | `MATCH`: one branch update, confirmed by reading the commit back |
| 4 | Same approval submitted again | `REFUSED`: `retained_authority_already_reserved`; no provider call |
| 5 | Someone edits the published file outside ProofRail; verification rerun | `REFUSED`: `commit_parent_changed`; reads only, no write |
| 6a | Second approval; branch update succeeds but the response is lost | `OUTCOME_UNKNOWN`, never reported as success |
| 6b | Read-only recovery | `MATCH` using GET requests only |
| 6c | Retry of that approval | `REFUSED`; the total stays at one branch update |

Steps 2a and 2b happen before the approved write and do not use up the approval.
Step 3 therefore succeeds with the same approval.

The file the dispatcher writes is a JSON record. It contains the approved text and
its execution ID and consumption digest, so the commit itself shows which approved
execution produced it.

## Run it

The demo needs Linux or macOS with git and Python 3.11 or 3.12. It needs no
credentials, no network access after installation, and no model calls. Run these
commands from a clean checkout of the reviewed commit:

```sh
python -m venv .venv && . .venv/bin/activate
python -m pip install . -r research/emergence_layer/requirements-dev.txt
cd research/emergence_layer
python buyer_demo/run_demo.py --workdir /tmp/pr-demo-work --evidence /tmp/pr-demo-evidence
python buyer_demo/verify_evidence.py /tmp/pr-demo-evidence
```

The last line of the verifier's output should be `VERDICT: PASS`. It exits 1 on any
failure.

Both directories must not already exist.

- **Work directory** (`--workdir`): holds the disposable repositories and the
  service databases. The signing keys are generated in memory for each run and
  are never written to disk or exported.
- **Evidence directory** (`--evidence`): holds only public material.
  - `approval/`: the signed handoff, which includes the approver's authority, and
    the contract.
  - `execution/`: the dispatcher's signed consumption record and the retained
    journal row.
  - A git bundle of each repository.
  - The four public keys.
  - The approved text.
  - `summary.json`: each step's outcome, the refusal reason, and every provider call
    with its method and path.
  - `SHA256SUMS`.

Copy the evidence directory to someone else and they can run `verify_evidence.py`
on it without any of your files. The verifier checks:

- the checksums;
- each signature;
- the approval → consumption → journal chain;
- the real git objects in the bundles: exactly one dispatcher commit per approval,
  on the approved parent, changing only the approved path, with exactly the
  approved bytes.

Altered evidence fails even if `SHA256SUMS` is regenerated, because the signatures
and the git objects no longer agree. `tests/test_buyer_demo.py` covers this.

## What it does not show

- **GitHub.** The provider is `local_git_provider.py`. It runs real git operations on
  a disposable bare repository and answers the same five Git Data API calls the
  dispatcher makes. It does not exercise:
  - the HTTPS client;
  - authentication;
  - GitHub App token scope;
  - branch protection;
  - GitHub's fast-forward-only ref update. The local ref update is a
    compare-and-swap, which is stricter than GitHub's.

  Validating this path is go-live gate 3: a real write and a real fault injected at
  a controlled proxy.
- **Key custody.** The run generates every key. A PASS means the evidence is
  consistent. It does not mean a particular person approved anything.
- **The run's own claims.** `summary.json` is the run's own record of each step. The
  verifier cross-checks it against the bundles, but a bundle contains only reachable
  history. For example, a refused attempt that left an unreachable object would not
  show up.
- **Joint rollback and administrator bypass.** Restoring both the registry and the
  journal, or bypassing the dispatcher as an administrator, is not prevented.
  [../DISPATCHER_PILOT.md](../DISPATCHER_PILOT.md) describes this boundary.
- **Performance.** `seconds_to_first_confirmed_write` is local wall time and does not
  predict GitHub latency.

## Measuring an evaluation

For each operator trial, record the following in `../pilot_metrics.csv`:

- the minutes from a clean machine to `VERDICT: PASS`, which covers installation
  plus the demo;
- `seconds_to_first_confirmed_write` from `summary.json`;
- any help the operator needed, in minutes.

During a buyer pilot, also record:

- the team's current human minutes per comparable artifact, before and during the
  pilot;
- how often an intervention or recovery was needed;
- whether the buyer pays to continue.

## Independent review

[REVIEW_PACKAGE.md](REVIEW_PACKAGE.md) defines what a reviewer must reproduce and try
to break. `buyer_demo/package_review.py` builds the package for one exact commit.
