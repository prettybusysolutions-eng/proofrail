# POLICY

## Branch policy
- the current default branch is the attested history branch (`master` at present)
- direct pushes should be disabled once branch protection is enabled
- all material state changes should flow through pull requests
- branch-name migration (`master` -> `main`) is optional hardening, not assumed current fact

## Approval policy
A state change counts as approved only when it is tied to a real GitHub principal through review, comment, or authenticated action.

## Verification policy
A claim does not count because it is written down.
It counts only when its verification path resolves through GitHub state, workflow output, or linked evidence.

## Outcome policy
Outcomes require at least one evidence reference.
No unsupported outcome claims.

## Non-goals
- synthetic progress
- unverifiable success claims
- hidden adjudication
- private rewrite of public history
