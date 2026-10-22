# Gate-3 live dispatcher trial

Status: PREPARED, NOT EXECUTED. No live run has happened. The dedicated repository,
the restricted credential, confirmed branch controls and a witness are all
prerequisites, and none is satisfied here. Preparing and self-testing this runner
does not close gate 3.

This trial exercises the unchanged `enforcing_dispatcher.Dispatcher` against one
dedicated GitHub repository, in three scenarios:

- **A — real write and read-back.** Approve exact bytes on the repository's current
  head, dispatch, and confirm the commit by reading the whole tree back.
- **B — application-level response loss.** Approve again and dispatch through an
  in-process fault. Then read-only recovery must confirm the exact approved tree
  with zero write calls, and reusing the permit must be refused.
- **C — registry rollback.** Back up the registry, dispatch (consuming a permit),
  restore the older registry while keeping the retained journal, and confirm that a
  further dispatch is blocked before any provider write.

## The fault model, stated plainly

Scenario B models **application-level response loss after a completed GitHub call**.
`live_trial/app_fault.py` forwards the dispatcher's request to the real client, so
the branch update genuinely happens on GitHub. It then discards the success
response and raises the client's own `provider_outcome_unknown` error before the
dispatcher sees the response. From the dispatcher's side this is indistinguishable
from a response that was lost in transit after the server committed the change.

This is **not** a transport-level interruption. It does not reproduce a connection
reset, a socket timeout, a half-open connection, or a truncated or malformed
response body during the call itself. Those paths run inside the real client's
`request()` and its `urllib` stack, which this trial does not perturb.

**Transport-level fault injection remains an open validation item.** This
substitution does not establish equivalent coverage. A full gate-3 sign-off still
needs a transport-interruption exercise (for example a controlled network
intermediary that severs a connection mid-response), designed and witnessed
separately. Treat scenario B as evidence for the dispatcher's *reconciliation
logic* on an unknown outcome, not as proof of its behaviour under every network
failure.

## What the evidence contains

`summary.json` holds public material only: the pinned source commit of this
checkout, the repository / branch / path, each scenario's outcome, the commit
SHAs and file digests produced, provider call counts (method and path strings,
never bodies), and the recovery and block reasons. It is covered by `SHA256SUMS`.

It deliberately excludes every secret: no private key, no installation token, no
request or response body. Keys are generated per run (see "Limits").

The summary includes an explicit `verdict`. The runner exits nonzero if a scenario
does not satisfy its expected assertions. Scenario B requires exactly one recorded
discarded response, the exact unknown-outcome error, successful read-only recovery,
and the expected replay refusal. Scenario C requires the specific missing-execution
refusal after restoration, not an arbitrary exception. A disabled fault must fail
the trial even if all writes and subsequent recovery otherwise succeed.

The scenario results are the run's own observations. They come from the call log
it wraps around the client and from the dispatcher's own `recover()`, which is the
code under test. They cannot show what else happened on the branch. So, after the
scenarios, the runner reads the branch back from the provider (GET only) and
requires all of the following:

- exactly three new commits since the starting head: A, then B, then C;
- one linear chain, each commit with one parent;
- each commit's tree equal to the previous tree plus only the approved regular
  file;
- file bytes matching the digests recorded during the run.

An unapproved commit in the trial window, a double write, a later edit, or a
look-alike commit replacing a trial commit each produce `verdict: FAIL`.
`provider_end_state` in the summary holds the chain, so a witness can compare it
with the repository's history.

Before this check, a run in which someone else committed to the branch between
scenarios A and B still exported `verdict: PASS`. `tests/test_gate3_trial.py` now
covers that case and the two others.

All three scenarios share one service: one registry and one retained journal,
reopened for each step as a restarted process would. Scenario C therefore restores
an older registry that still holds A and B and lacks only C. The block has to come
from C's missing record, not from an empty registry. The summary records this
under `restored_registry_holds`.

## Running the self-test (no network)

```sh
python live_trial/run_trial.py --local --evidence /tmp/gate3-evidence
```

This uses a disposable local git repository through
`buyer_demo/local_git_provider.py` and makes no network call. It is covered by
`tests/test_gate3_trial.py`.

## Running the live trial (prerequisites, executed by the operator with a witness)

The work and evidence directories must be separate, with neither inside the other.
The runner reserves a new evidence directory and writes an `INCOMPLETE` marker
before any provider call. An existing destination or invalid parent path therefore
refuses before the trial writes. On completed export, the marker is removed after
the summary and checksums are written. If it remains, preserve the work stores and
inspect the provider before deciding how to recover; do not blindly rerun.
This upfront write check cannot guarantee disk capacity or availability throughout
the run, and the marker is not a crash-durable transaction journal.

1. Create a dedicated throwaway repository. It must hold nothing else of value.
2. Configure branch controls on the trial branch and confirm them out of band:
   no force-push, no deletion, writers restricted to the service identity.
   Record how this was confirmed.
3. Provision a GitHub App installation token restricted to that one repository
   with Contents write. Put it in a service-owned `0600` file. Never pass it on
   the command line, place it in the repository, or copy it into the evidence.
4. Write a `0600` config file:

   ```json
   {
     "repository": "OWNER/DEDICATED_REPO",
     "branch": "trial/emergence-gate3",
     "path": "evidence/gate3.json",
     "github_token_file": "/run/secrets/github-installation-token"
   }
   ```

   The branch must start with `trial/emergence-` and the path with `evidence/`;
   the dispatcher enforces both.
5. With a witness present, run:

   ```sh
   python live_trial/run_trial.py --config /etc/proofrail/trial.json \
       --evidence /srv/proofrail/gate3-evidence --workdir /srv/proofrail/gate3-work
   ```

6. Archive the evidence directory and the witness's attestation. Delete the
   throwaway repository afterwards.

## Expected results

| Scenario | Expected |
|---|---|
| A | `MATCH`; the branch advances by one commit; read-back confirms the approved tree |
| B | dispatch raises `provider_outcome_unknown`; recovery `MATCH` with 0 write calls; reuse refused (`retained_authority_already_reserved`) |
| C | first dispatch `MATCH`; restored registry holds A and B but not C; the next dispatch is blocked (`execution_not_found`) with 0 provider calls |
| End state | branch history since the start is exactly A → B → C, each adding only the approved file with the recorded bytes; 0 write calls |

## Limits (do not overstate)

- **Not independent.** Author-run. Gate 2 (an outside reviewer) is separate and open.
- **Key custody not shown.** The trial generates the agent, approver, consumer and
  observer keys per run. A pass shows the dispatcher's behaviour, not who controls
  the keys or who approved. Production key custody is out of scope.
- **Branch controls assumed.** The runner does not verify that force-push and
  deletion are disabled; that must be confirmed out of band (step 2). An
  administrator who can rewind the branch is outside this trial's model, as in #29.
- **One transport, one provider.** GitHub only; no claim about other providers.
- **Transport interruption uncovered**, as above.
- **End-state check is not fully independent.** It uses the same GitHub client and
  the same tree-comparison helper as the dispatcher. The witness should also
  inspect the branch history directly, for example `git log` on a fresh clone,
  and compare it with `provider_end_state.chain`.
