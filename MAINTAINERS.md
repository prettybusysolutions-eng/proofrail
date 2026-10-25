# Maintainers and repository access

## Recorded public ownership

- GitHub organization: [`prettybusysolutions-eng`](https://github.com/prettybusysolutions-eng).
- Repository: [`prettybusysolutions-eng/proofrail`](https://github.com/prettybusysolutions-eng/proofrail).
- CODEOWNERS currently requests ownership/review from `@prettybusysolutions-eng` for all paths.

These facts identify the published repository owner, **not** the identities of specific administrators or the actual effective permission assignments. No individual maintainer, 24/7 response team, separate independent reviewer or enforcement of required reviews is established by this document.

## Operational responsibilities

| Function | Responsible party / verification state |
| --- | --- |
| Repository administration and branch rules | Organization-appointed repository administrator; current effective access and rules require direct Settings review |
| Security triage and embargo decisions | Authorized maintainer(s) with private vulnerability-advisory access; staffing to be confirmed |
| Code review / release approval | Authorized maintainers; an automated agent cannot authorize its own protected merge or release |
| Signing provenance | GitHub Actions release workflow, with verifiable Sigstore-issued short-lived certificate, once implemented and run |
| Independent security validation | Not yet assigned or evidenced |

## Before public security maturity claims

A repository administrator should publish a non-sensitive list of human maintainers and their general roles (without exposing confidential permissions), confirm security-report routing is enabled, verify actual write/admin access, enforce appropriate branch rules and record a witnessed release authorization procedure.

This document deliberately does **not** invent the identities or access rights of private organization members.
