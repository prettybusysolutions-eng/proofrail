# ProofRail Independent Reproduction Trial

Date: 2026-06-12

## Trial Boundary

The v0.5.2 artifact was exported from commit `4f198a9` into a new temporary
directory, installed into a fresh virtual environment, and verified without
using the repository's existing environment.

This is a clean-environment internal reproduction. It is not a fresh physical
machine, independently authored validation, or third-party human review.

## Procedure

```bash
git archive --format=tar 4f198a9 | tar -xf - -C "$trial_root"
python3 -m venv "$trial_root/.venv"
"$trial_root/.venv/bin/pip" install -e "$trial_root"
"$trial_root/.venv/bin/proofrail" reproduce \
  "$trial_root/examples/reproduce_artifact"
```

The artifact was then copied, `TRANSCRIPT.md` was altered without updating the
signed manifest, and the reproduction command was rerun against the copy.

## Result

- authentic artifact exit code: `0`
- authentic artifact verdict: `valid: true`
- tampered artifact exit code: `4`
- tampered artifact verdict: `valid: false`
- detected tamper: signed manifest file-hash mismatch
- schema validation: 14 Draft 2020-12 schemas from v0.5.2

The trial demonstrates that the documented clean-install procedure is
sufficient to reproduce the committed evidence and reject a substituted file.
It does not establish external key identity or third-party independence.

An uninvolved isolated verifier session separately repeated the archive,
Python 3.11 virtual-environment install, authentic reproduction, and declared
file substitution. It independently observed exit codes `0` and `4` and found
the reproduction documentation consistent with the checks. This adds internal
independence of execution, not third-party authorship or human validation.

During v0.6 release verification, a standard non-editable install exposed that
the JSON schemas were not included in the wheel. Packaging was corrected to
ship the schemas, and both editable and non-editable clean installs are release
gates for v0.6.
