# ProofRail Demo Video Script

Target length: 6 minutes.

Audience: skeptical security and platform engineers.

## 0:00 - The Claim

On screen:

> ProofRail issues single-use cryptographic permits for autonomous agents,
> binding exact authority to exact actions.

Narration:

"An agent should not be able to touch an important system because it produced
a plausible explanation. ProofRail requires a signed, one-time permission that
matches the exact action, target, evidence, policy, approval, and state."

Show:

```text
intent -> evidence -> policy -> signed permit
       -> one execution -> provider observation -> audit proof
```

## 0:40 - Install And Reproduce

Run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/proofrail reproduce examples/reproduce_artifact/
```

Narration:

"This bundle contains signed authority, a consumed permit, replay state,
ledger, checkpoint, external anchor, adversarial results, and expected
failures. The verifier does not need a network connection or our private
keys."

Zoom in on:

```json
"valid": true
```

## 1:40 - Break The Evidence

Run:

```bash
cp -R examples/reproduce_artifact /tmp/proofrail-tampered
printf '\nchanged\n' >> /tmp/proofrail-tampered/TRANSCRIPT.md
.venv/bin/proofrail reproduce /tmp/proofrail-tampered
echo $?
```

Show exit code `4` and the failed file-hash check.

Narration:

"A changed declared file no longer matches the signed manifest. Failure stays
visible; it is not relabeled as success."

## 2:25 - First Domain: GitHub Merge

Run:

```bash
demo_dir="$(mktemp -d)"
.venv/bin/proofrail demo github-merge-authority --out-dir "$demo_dir"
.venv/bin/proofrail ledger verify "$demo_dir/proofrail-ledger.jsonl"
```

Narration:

"The GitHub authority binds one repository, pull request, head SHA, and merge
method. If the head changes, the permit is stale. If execution times out,
ProofRail observes provider state. Unknown is not success, and the permit is
not replayed."

Show the valid ledger and the committed tampered sample.

## 3:35 - Second Domain: Database Migration

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_database_migration_authority -v
```

Narration:

"The same model governs an exact SQLite migration. The permit binds the SQL,
current and expected schema roots, target version, and local database
instance. The tests attempt changed SQL, schema drift, a same-schema wrong
database, path replacement, cross-database attachment, replay, and false
success."

Show the passing test names, not just the final count.

## 4:35 - Trust Boundaries

Open:

- `docs/KNOWN_LIMITATIONS.md`
- `docs/SECURITY_MODEL.md`

Narration:

"ProofRail does not eliminate trust. It makes the remaining trust explicit.
A compromised verifier key can mint authority. Enough compromised observers
can falsify reconciliation. SQLite and JSONL are pilot storage, not consensus.
The current validation is internally authored and replayable, not third-party
validation."

## 5:20 - Open Evaluation Question

Open:

- `docs/OPEN_STANDARD_DIRECTION.md`
- `docs/ACTION_AUTHORITY_ENVELOPE_V1.md`
- `docs/KNOWN_LIMITATIONS.md`

Narration:

"The next question is not whether another control can be added. It is whether
an outside team can reproduce the evidence, break-test the boundary, and build
an independent conforming implementation."

End card:

> One exact action. One consumed permit. One independently checkable outcome.
