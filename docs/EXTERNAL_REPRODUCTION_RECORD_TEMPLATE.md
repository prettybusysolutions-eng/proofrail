# ProofRail External Reproduction Record

Use one copy of this record per evaluator. Do not complete fields on the
evaluator's behalf.

This record captures an external reproduction attempt. It is evidence of what
the named evaluator observed, including failures and assistance. It is not
automatically a security audit, certification, endorsement, or proof of
production readiness.

## Record Identity

- Record ID:
- Evaluation date:
- Target repository:
- Target commit: `02097bc798817f96b06aef9116a20ebe710096a5`
- Record status: `not_started | in_progress | completed | withdrawn`
- Final verdict: `succeeded | partially_succeeded | failed | inconclusive`

## Evaluator

- Name:
- Organization:
- Role:
- Relevant experience:
- Public profile or other identity reference:
- Contact method:

### Independence Statement

Answer each item directly.

- I did not design or implement ProofRail: `yes | no`
- I had no financial stake in the result when testing began: `yes | no`
- I had not previously configured this repository or its test environment:
  `yes | no`
- I received the repository and written instructions before receiving live
  implementation assistance: `yes | no`
- Other relationships, incentives, or conflicts:

Evaluator statement:

> I performed the reproduction described below and recorded the observed
> results, including failures, disagreements, and assistance received.

## Machine And Environment

- Physical machine, virtual machine, or hosted runner:
- Machine owner/operator:
- Operating system and version:
- Architecture:
- Python version:
- Shell:
- Git version:
- Network access available during install: `yes | no`
- Existing ProofRail installation before the trial: `yes | no`
- Repository obtained by: `clone | archive | other`
- Clean environment method:
- Additional relevant packages, proxies, mirrors, or security controls:

Attach or paste:

```text
uname -a
python3 --version
git --version
```

## Instructions Received

- Files or links supplied before testing:
- Verbal or live guidance supplied before testing:
- Expected results disclosed in advance:
- Any instruction missing, unclear, or contradictory:

## Commands And Results

Record commands exactly. Do not normalize failed commands after the fact.

| Step | Exact command | Start time | Exit code | Observed result |
| --- | --- | --- | ---: | --- |
| Acquire target |  |  |  |  |
| Create environment |  |  |  |  |
| Install |  |  |  |  |
| Verify CLI |  |  |  |  |
| Reproduce authentic artifact |  |  |  |  |
| Modify declared file |  |  |  |  |
| Reproduce modified artifact |  |  |  |  |
| Run full tests |  |  |  |  |
| Run GitHub offline demo |  |  |  |  |
| Run database authority tests |  |  |  |  |
| Regenerate validation evidence |  |  |  |  |

Attach complete stdout/stderr or identify where it is retained:

- Command transcript location:
- Raw logs location:

## Artifact Hashes

State the hashing command used:

```text
<exact hashing command>
```

| Artifact | Expected or source hash | Observed hash | Match |
| --- | --- | --- | --- |
| Repository archive or commit |  |  | `yes | no` |
| `reproduction-manifest.json` |  |  | `yes | no` |
| Authentic `TRANSCRIPT.md` |  |  | `yes | no` |
| Modified `TRANSCRIPT.md` | n/a |  | n/a |
| `VALIDATION_REPORT.md` |  |  | `yes | no` |
| `validation-results.json` |  |  | `yes | no` |
| Other material artifact |  |  | `yes | no` |

## Time To Complete

- Start time:
- End time:
- Active evaluator time:
- Waiting/install time:
- Time blocked:
- Time receiving assistance:

## Assistance Required

List every intervention after testing began. A reproduction that required
assistance may still be useful, but must not be reported as unassisted.

| Time | Blocker | Person or system providing help | Exact assistance | Result |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

- Was any undocumented assistance required? `yes | no`
- Could the evaluator have completed using only the repository? `yes | no`
- If no, what must change?

## Failures, Findings, And Disagreements

Record all observed failures, even if they were later resolved.

| ID | Severity | Claim or step affected | Observation | Reproduction | Disposition |
| --- | --- | --- | --- | --- | --- |
| EXT-001 |  |  |  |  | `open | explained | fixed | disputed` |

Evaluator disagreements with repository claims:

-

Unexpected successful behavior:

-

Unexpected failed behavior:

-

## Evaluator Conclusions

Answer without relying on project marketing language.

- Did the authentic artifact reproduce? `yes | no | partial`
- Did the declared-file modification fail verification? `yes | no`
- Did the full test suite pass? `yes | no | partial`
- Did deterministic evidence regenerate byte-for-byte? `yes | no | not_run`
- Were trust boundaries understandable? `yes | no | partial`
- Was the process independently executable without assistance?
  `yes | no | partial`
- What, if anything, does this evaluation demonstrate?
- What does it not demonstrate?
- What should be tested next?

## Sign-Off

Evaluator:

- Name:
- Date:
- Signature or verifiable acknowledgement:

Project acknowledgement:

- Received by:
- Date:
- Record preserved at:
- Project response:

Project acknowledgement confirms receipt only. It does not change the
evaluator's verdict.
