# Contributing and provenance

This is a public Apache-2.0-licensed software repository. A contribution can
be reviewed for inclusion without transferring ownership of the contributor's
copyright. Submitting a pull request does not establish that the repository
maintainer or any future company owns all contributed IP.

## Before opening a pull request

- Use an issue or discussion for significant new features or security-sensitive
  changes. Never publish exploit details, customer secrets, private keys or
  confidential contracts. Follow [SECURITY.md](SECURITY.md).
- Submit only code, text and assets you have the right to contribute under
  Apache-2.0. Identify significant third-party source or dependencies and their
  licenses, and preserve required notices.
- Disclose when an employer, client or other party may own rights to the
  contribution. Obtain appropriate permission **before** contributing; don't
  upload employment contracts or private clearance evidence to GitHub.
- For material AI-assisted code, identify the assisted portions and confirm
  that a human reviewed behavior, security, third-party source risks and
  licensing. An AI tool's output does not by itself prove copyright ownership.
- Explain changes, tests, threat-model implications and breaking changes.
  Keep new authorization or enforcement behavior in draft review until
  independently tested as required by the project release gates.

## Developer Certificate of Origin (DCO)

For *new* authored contributions, please certify provenance by signing off
the relevant commits with `git commit --signoff` (or `git rebase --signoff`
when appropriate). The trailer looks like:

```text
Signed-off-by: Your Name <your-address@example.com>
```

By signing off, you attest that you have the right to submit the contribution
under the repository's license according to the
[Developer Certificate of Origin 1.1](https://developercertificate.org/).

**A DCO sign-off is a contributor certification, not a copyright assignment,
a trademark license, a guarantee of originality, or proof that an employer
waived ownership.** A maintainer may request separate private evidence or a
written rights agreement when provenance is uncertain. The initial policy is
reviewer-enforced: a GitHub commit-signoff setting by itself does not enforce
signoffs for all command-line commits. Existing history is not retroactively
attested by this document.

## Acceptance

Maintainers may reject an otherwise working patch because ownership,
third-party licensing or security evidence is unclear. Follow the current
release and review requirements and do not assume that a green CI job
automatically authorizes merging.

See [IP provenance register](docs/IP_PROVENANCE_REGISTER.md) for the
repository-wide audit plan. Public PRs must not contain private legal records.
