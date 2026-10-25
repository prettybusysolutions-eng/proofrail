# Changelog

This file records **published versions separately from unmerged development**. It follows a lightweight Keep a Changelog layout; entries are not independent evidence of implementation correctness.

## [Unreleased]

- Proposed: contributor and maintainer documentation, coordinated disclosure response targets, manual release gating and GitHub Sigstore-backed build provenance attestations.
- The authority-envelope, facility outcome, provider-enforcement, dispatch and registry-hardening draft PRs are **not part of v0.6.1**. Their exact contents and release notes must be settled after review and merge; nothing here marks them as released.

## [0.6.1] - 2026-10-11

- Published as a GitHub **prerelease**, including a Python wheel, source archive, independent-review input archive, SHA256SUMS and `provenance.json`.
- `provenance.json` was **unsigned workflow metadata**, not a cryptographic signature. Do not claim that this existing release meets signed-release requirements.
- Existing artifact is independently installable/reproducible in a clean environment, but its included tests are internally authored and do not establish production approval.

## [0.6.0] - 2026-10-11

- First published GitHub prerelease with installable wheel, source distribution, checksums and unsigned workflow provenance metadata.

[0.6.1]: https://github.com/prettybusysolutions-eng/proofrail/releases/tag/v0.6.1
[0.6.0]: https://github.com/prettybusysolutions-eng/proofrail/releases/tag/v0.6.0
