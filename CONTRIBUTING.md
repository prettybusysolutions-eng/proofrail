# Contributing to ProofRail

ProofRail is a security-sensitive reference implementation. Contributions are welcome, but an automated PASS result is not permission to merge, release, or execute a consequential external action.

## Before opening a pull request

1. Open or reference an issue describing the problem and the expected, testable behavior. For a security vulnerability, use the **private** channel in [SECURITY.md](SECURITY.md), not a public issue.
2. Make changes on a separate branch with a bounded scope. Avoid unrelated generated evidence, release metadata or lockfile changes.
3. Run the tests from a clean Python 3.11+ environment:

   ```sh
   python -m pip install -e .
   python -m unittest discover -s tests -v
   python scripts/check_adapter_e2e.py
   proofrail reproduce examples/reproduce_artifact/
   ```

4. For authority, trust, replay, provider or state-machine changes, add a negative regression that fails when the particular security check is removed; include the exact refusal reason or evidence field in its assertion.
5. Explain the new trust assumptions and residual limitations. A signed local receipt is not independent anchoring; internal tests are not an outside review.
6. Open a **draft** pull request with the base commit, commands, test results, behavior changes, migration/recovery impacts and what remains unverified.

## Review and release

The published `.github/CODEOWNERS` assigns ownership to `@prettybusysolutions-eng`; that is a requested-review signal, **not** proof that branch protection or approvals are currently enforced. Only authorized repository maintainers may approve and merge; CI and an AI agent cannot self-certify production readiness.

Review should include correctness, fail-closed behavior, cross-tenant and replay isolation, artifact reproduction, documentation, licensing and compatibility. Never assume a passing normal test suite catches a removed security check. A single reviewer who implemented a security-sensitive change is not an independent security assessor.

GitHub Actions release publication is a separate, manual event after a reviewed merge, version/changelog preparation, complete required CI, and explicit maintainer release approval. Do not publish from a contributor branch. See [RELEASING.md](RELEASING.md).

## Safe testing

Use disposable local databases, mock/fault providers and synthetic identities. Do not test against an external provider, live organization, customer account or credentials without explicit written authorization. Never commit private keys, access tokens, personal data, unredacted customer logs or disclosure reports.

## Contribution licensing

Code contributions are proposed for the repository under its [Apache-2.0 license](LICENSE). Contributors must have the right to submit their work. If you are using AI-assisted changes, identify that in the PR and retain human review/accountability for their correctness and origin.
