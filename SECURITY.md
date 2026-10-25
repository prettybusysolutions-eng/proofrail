# Security Policy

ProofRail is security-sensitive software. Reports that could enable
unauthorized execution, authority replay, signature bypass, false
reconciliation, trust-state rollback, or evidence forgery should be handled
privately.

## Supported Version

Security fixes are evaluated against the latest commit on the active ProofRail
development branch. Historical prototype versions may not receive separate
patches.

## Reporting A Vulnerability

Do not open a public issue containing exploit details, secrets, customer data,
or a working bypass.

Use the repository host's private vulnerability-reporting or security-advisory
feature. If that feature is unavailable, contact the maintainer through the
established private project channel and request a secure reporting route.

Include:

- affected commit
- threat and expected security property
- minimal reproduction steps
- whether a side effect occurred
- relevant permit, checkpoint, anchor, or receipt identifiers
- logs with secrets and private customer data removed
- proposed embargo needs

Do not test against systems, repositories, databases, accounts, or credentials
you do not own or have explicit authorization to assess.

## Response Standard

A valid report should receive:

1. acknowledgement
2. reproduction or a precise request for missing evidence
3. severity and affected-boundary assessment
4. remediation or a documented decision not to change behavior
5. regression evidence
6. coordinated disclosure timing when applicable

### Response targets and staffing boundary

For privately reported vulnerabilities, the proposed maintainer **targets** are:

- acknowledge receipt within **7 calendar days**;
- triage the affected boundary and communicate next steps within **14 calendar days**;
- provide a status update at least every **30 calendar days** until coordinated closure;
- coordinate disclosure timing with the reporter, weighing exploitation risk,
  affected releases, available mitigations and a normally reviewed **90-day**
  disclosure window rather than publishing exploit details immediately.

These are **targets, not an SLA or a guarantee**. The repository has not
independently established a staffed public security contact or 24/7 coverage.
Until an administrator confirms the private reporting route, assigns maintainers
and accepts the timetable, do not claim this policy is operationally enforced.
A reporter should receive a private, safe channel before providing sensitive
reproduction material.

Report receipt, severity classification and disclosure decisions remain human
maintainer responsibilities. AI-generated triage is advisory and must not
unilaterally publish vulnerability details or approve a release.

## High-Value Report Areas

- permit signature or content-hash bypass
- replay after valid consumption
- replay-registry or checkpoint rollback acceptance
- authority minted by an unauthorized role
- learner or executor self-promotion
- effect changes that preserve permit validity
- provider or database state changes accepted as reconciled success
- ambiguous outcomes marked retry-safe
- ledger, checkpoint, anchor, or manifest tampering that verifies
- artifact path traversal, symlink, or undeclared-file acceptance
- secret or private-data disclosure in logs and portable artifacts

## Known And Non-Security Limitations

Read `docs/KNOWN_LIMITATIONS.md` before filing. A documented trust dependency
is not automatically a vulnerability.

Examples:

- internally authored validation is not third-party validation
- local SQLite and JSONL are pilot storage
- compromise of enough explicitly trusted keys can satisfy quorum
- schema reconciliation does not prove application-data correctness

A report is still valuable when it shows that behavior exceeds the documented
boundary or that the boundary is materially incomplete.

## Safe Research

Use the credential-free examples, temporary databases, and local test suite.
Preserve exact commands and exit codes. Stop if testing could affect external
state or expose another party's information.
