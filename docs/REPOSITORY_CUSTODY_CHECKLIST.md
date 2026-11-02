# Repository Custody and Review Controls — Admin Checklist

The current GitHub owner account is a **User**, not an incorporated legal
entity merely because its login resembles a business name. These items
protect operational control and evidence; they do not transfer copyright.

## Immediate account protections (admin actions)

- [ ] Turn on a phishing-resistant passkey/security key and a second
  recovery method; store recovery codes offline.
- [ ] Confirm verified account email, owner login, recovery process and
  restricted access to any linked CI/release accounts.
- [ ] Review connected OAuth apps, GitHub App installations, personal tokens,
  deploy keys, Actions secrets and collaborator access. Remove unnecessary
  permissions and rotate any exposed secret.
- [ ] Create a private, independently accessible Git repository backup and
  periodically test restoration. Do not include credentials or signed IP
  agreements in a public backup.
- [ ] Preserve original repository ID, relevant commit SHAs, tags, and
  verifiable release artifacts without altering historical attribution.

## Branch protection / rulesets — NOT YET ENFORCED

As of 2026-11-02, the repository ruleset list returned `[]`. The current
`.github/CODEOWNERS` names `@prettybusysolutions-eng`, but **CODEOWNERS
does not block direct pushes or require review by itself**.

With a suitable GitHub plan and an *independent* reviewer where feasible,
configure on `main`:

- [ ] Require pull requests before merging and at least one qualified
  approval from a person other than the author when supported.
- [ ] Require CODEOWNERS review and dismiss stale approvals after updates.
  Protect `.github/CODEOWNERS` itself (its current wildcard owner applies
  to this file).
- [ ] Require only verified, appropriately scoped CI checks; measure
  whether required statuses originate from a trusted integration.
- [ ] Block force pushes and deletion of `main`; minimize bypass access.
- [ ] Test the rule on a disposable branch/PR, including direct push,
  force-push and bypass attempts; retain read-back evidence.
- [ ] Re-read ruleset/branch protection after setup. An admin UI screenshot
  alone is not proof that all actors or API paths are blocked.

**Caveat:** For a one-maintainer personal repository, requiring another
independent reviewer may prevent merging until another trusted person joins;
do not add fake reviewers or silently bypass protections. Branch rules are
not configured through this document. Native GitHub App status-source
enforcement for autonomous merges is still separately tracked in
[Issue #71](https://github.com/prettybusysolutions-eng/proofrail/issues/71).

## Company custody, when the legal entity is decided

- [ ] Identify a legally existing entity and verify its authority to receive
  assets. Avoid claiming a GitHub username is an LLC.
- [ ] Ask counsel to verify rights and obtain signed, dated IP assignments
  from actual copyright holders where required. Preserve originals privately.
- [ ] If appropriate, create a **company-owned GitHub organization** with
  multiple authorized administrators, hardware-backed 2FA and documented
  recovery/succession. Plan repository transfer without deleting history,
  verifying permissions, integrations, webhooks, Secrets and release paths.
- [ ] Update CODEOWNERS, release identities, domain email and contracts only
  after the legal and GitHub changes are actually made.
- [ ] Preserve Apache-2.0 rights previously granted to recipients. A
  repository transfer or license notice cannot retroactively revoke them.
- [ ] Clear the product/company name separately from copyright and ownership
  of the software.

## Do not store in public GitHub

Signed IP assignment documents, founder IDs, capitalization records, customer
contracts, tax identifiers, access credentials, recovery codes, private legal
advice, trade-secret implementation details or undisclosed vulnerabilities.
A private repository is still not automatically an appropriate legal vault.

This checklist does **not** certify compliance or establish exclusive IP
ownership. Each checkbox needs independent evidence when completed.
