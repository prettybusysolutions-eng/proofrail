# Run a measured audit-triage pilot

Status: tooling ready for a local trial; no adopter, completed human observations,
payment commitment or independent review is established by this package.

## Objective and limits

Determine whether audit triage reduces review time without increasing mistakes
for one real workflow. The tool reviews claims in ProofRail pilot audit JSONL.
It does not accept arbitrary GitHub Actions logs or prove policy authorization.
If the adopter uses another event format, first specify and validate a mapping;
do not relabel unsupported records or discard inconvenient fields to get a pass.

The baseline is the adopter's normal review process, including its existing log
viewer, searches and scripts. Do not intentionally weaken it. Both arms receive
the same records and access to the same supporting evidence. The assisted arm
also receives ProofRail's review report. This measures a workflow, not universal
security superiority. Keep production execution and retries outside the trial.

## Prepare the trial

1. Obtain permission to use one team's redacted export. Keep the original in its
   controlled location, preserve a checksum and document redaction. Removing or
   replacing fields changes signatures; never present a redacted copy as the
   cryptographically verified original. Remove secrets before sharing copies.
2. Copy `examples/adopter-trial` to a private working directory. Keep completed
   customer data and observations out of the public repository.
3. Fill the manifest's workflow, exact baseline tools, assisted source commit and
   label approver. Select at least 20 distinct review cases with both labels and
   at least five critical cases requiring review. Mutated/synthetic challenges
   may supplement scarce real cases, but record provenance and report them
   separately; challenge enrichment does not measure production error frequency.
4. A domain-competent adjudicator sets each expected label (`needs_review` or
   `no_findings`), critical flag, evidence path and rationale before the review.
   Do not derive truth labels from ProofRail's output. These are triage decisions,
   not determinations that the underlying provider action was authorized.
5. Give reviewers evidence and assignments, not the answer manifest. Replace the
   two reviewer aliases with distinct stable pseudonyms. The supplied schedule
   gives each reviewer ten cases in each arm and prevents seeing a case twice;
   for more cases, preserve that balance. Allow equal training on unrelated cases.

## Collect and score

For each assigned case, start timing when the evidence is opened and stop at the
recorded decision. Include searching and follow-up inspection. Record interruptions
and exclusions separately; do not remove slow or wrong answers after seeing them.
Record setup/training time separately and include it in commercial cost estimates.
Do not use assistant-generated answers or synthetic test times as human results.

```bash
proofrail audit-review --events case.jsonl --tenant TENANT --output review.json
python scripts/score_adopter_trial.py --manifest /private/trial/manifest.json --observations /private/trial/observations.csv
```

The scorer requires complete paired observations, finite positive timings,
approved labels, different reviewers for each case and balanced arms per reviewer.
It rejects the unfilled templates with exit 2. Valid measurements produce exit 0
even if the proposed continuation threshold is not met; inspect the report fields.
It cannot authenticate the people, times, labels, preregistration or source data.

The predeclared exploratory technical threshold is:

- At least 30% median paired time reduction.
- Assisted accuracy no worse than baseline.
- Zero missed critical review cases in the assisted arm.

This is a proposed business hurdle, not a regulatory standard or statistical
guarantee. A small, enriched and counterbalanced sample can still have reviewer,
learning and selection effects. Preserve raw observations and adjudicate disputes
without changing labels solely to match the tool. Any departure from the schedule
or trial design must be reported, not hidden in the aggregate score.

## Commercial decision

If the technical threshold fails, inspect the error categories and stop expansion
unless there is a specific fix worth retesting. If it passes, ask the adopter
whether the savings justify continued paid use. Calculate monthly hours saved
from its actual review volume and measured time savings, then subtract setup,
maintenance and additional review costs. Use its actual loaded labor costs.

Do not assign a price or acquisition value from synthetic timings. A paid pilot
needs an agreed scope, success criteria, support obligations and an actual buyer.
This repository contains no executed agreement, buyer promise or invented revenue.

## Installation verification

The installed-artifact verifier now exercises audit review from a temporary
directory using Python's isolated mode. It checks contradictory and consistent
claims, input preservation and tenant mismatch. Existing Python 3.11/3.12 CI wheel
jobs invoke this verifier automatically. Local validation used a built wheel in
the existing audit environment; it was not a fresh independent machine.
The candidate wheel retains development version 0.6.1 and is not a replacement
for the published release. Pin the reviewed source commit for a trial until a
separately versioned release is prepared. No deployment is performed here.
