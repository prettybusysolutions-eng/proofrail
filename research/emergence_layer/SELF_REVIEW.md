# Author self-review: mutation sweeps and fault matrices

Status: AUTHOR-RUN. This is not independent review. It removes what the authors
could find mechanically before a reviewer looks; it cannot show that nothing is
left. Gate 2 (independent review, issue #30) and gate 3 (witnessed live run) stay
open.

## Method

Every finding earlier in PR #40 had the same shape: a check that existed, or
should have existed, but that no test enforced. Three mechanical sweeps target
that shape. Each can be rerun with `review_tools/`.

1. **Check removal** (`review_tools/mutate_checks.py`). Disable each
   `require(...)` in `enforcing_dispatcher.py`, `github_artifact.py`,
   `acceptance_bridge.py` and `execution_binding.py` one at a time (condition →
   `True`) in a throwaway copy, then run the research suite. If the suite stays
   green, that check is unenforced.
2. **Operator mutation** (`review_tools/mutate_operators.py`). In the two
   modules that decide writes and confirmations (`enforcing_dispatcher.py`,
   `github_artifact.py`), make each of these changes one at a time:
   - flip each comparison;
   - swap `and` and `or`;
   - drop `not`;
   - flip `True` and `False`;
   - increment each integer constant.

   This finds checks that are present but wrong.
3. **Fault matrices** (`tests/test_fault_matrix.py`):
   - Interrupt a dispatch at every step boundary: 10 provider-side points, 4
     local points, and readback. Restart over the same stores and require all of
     the following:
     - recovery never writes;
     - recovery reports `MATCH` if and only if the branch update took effect;
     - the permit is never reusable;
     - at most one dispatcher commit exists.
   - Corrupt each provider response the dispatcher reads: 25 recovery
     responses, 2 reads before the write, and 2 misreported write
     acknowledgements. The result must never be `MATCH` and recovery must never
     write. A negative control, with the whole-tree check removed, makes 14 of
     these fail, so the matrix can detect regressions.

## Results

| Sweep | Before | After |
|---|---|---|
| Check removal | 80 of 110 checks unenforced | 0 of 111 (one guard added) |
| Operator mutation | 6 of 78 survived | 2 of 82 survive, both equivalent (below) |
| Research suite | 130 tests | 289 tests |

Load-bearing checks that were present in the code but had no test:

- **`branch_parent_changed`**: the only pre-write stop when the branch has moved
  since approval. Without it, tree and commit objects are written before the
  provider refuses the ref update.
- **`tree_entry_duplicate`**: without it, a tree listing with a duplicated entry
  confirms `MATCH`.
- **The real GitHub client's request construction.** No test let
  `GitHubAPI.request` build a request, so swapping GET and POST body handling
  left the suite green. This is the only code that carries the token.
  `tests/test_github_client.py` now covers the following with only the URL
  opener replaced:
  - URL, method, body bytes, headers and timeout;
  - that only the refusing redirect handler is installed;
  - that every failure maps to `provider_outcome_unknown` with no cause, body
    or token exposed.
- **`recovery_writes` was a hard-coded `0`**: the recovery result asserted a
  claim it never measured. It is now counted from the calls actually issued
  (`Dispatcher.write_calls`). A new guard, `recovery_issued_write`, refuses a
  recovery that wrote anything.
- **Retained journal file mode** (`0o600`) and **strict base64 decoding**:
  neither was asserted.

Why 80 checks survived: the earlier tests asserted only that *something* raised,
so a later layer could stand in for a missing one. The new tests
(`test_check_reasons.py`, `test_research_check_reasons.py`) each build the input
one check exists to reject and assert that check's exact reason. Wherever the
check is reachable they enter through the dispatcher, and on dispatch paths they
also assert zero provider writes. Checks reachable only by direct call are
labelled defence in depth in their tests.

One flaky test was found and fixed along the way. It had been created during
this review, not before. `test_verify_commit_rejects_another_approval_for_this_execution`
failed in 3 of 15 runs: the second approval was created after the first
consumption, so a clock second ticking between them made it look as if it came
from the future. The dispatcher was correct. Under a clock that advances a full
second on every call, the old test fails deterministically and the fixed one
passes, as do all 185 dispatcher-related tests.

Earlier sweep results were partly invalid while that flake existed. With `-x`,
a mutant could count as caught merely because the flaky test failed. The numbers
above come from runs after the fix.

## Survivors kept, with reasons

- `enforcing_dispatcher.py`, `Journal.db`: `uri=True` → `False`. Equivalent on
  this build, whose SQLite interprets `file:` names as URIs regardless of the
  flag. The flag matters on builds that don't. The property it protects is
  tested directly: a journal deleted underneath an open service is not
  recreated.
- `enforcing_dispatcher.py`, `Journal.db`: busy timeout `10` → `11`. An
  operational setting, not a correctness one.

## What this does not establish

- **Missing checks.** Mutation shows that existing checks are enforced. It cannot
  find a check nobody wrote; that is what the fault matrices and adversarial
  probes are for, and they are only as complete as the cases thought of.
- **GitHub, credentials and branch controls.** These are exercised only by the
  witnessed live trial (gate 3).
- **Transport-level interruption.** This remains open (see `live_trial/LIVE_TRIAL.md`).
- **Code outside the four modules**, including `proofrail/` core, `smatp.py`
  and `server.py`. Those were not swept.
- **Independent review.** The same authors wrote the code, the tests and this
  review.

## Reproduce

```sh
cd research/emergence_layer
python review_tools/mutate_checks.py . /tmp/checks.json 4      # expect: survived 0 of 111
python review_tools/mutate_operators.py . /tmp/ops.json        # expect: survived 2 of 82
python -m pytest -q tests/                                    # expect: all pass
```
