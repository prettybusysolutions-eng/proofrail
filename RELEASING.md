# Releasing

The package declares `0.6.1`. Two GitHub prereleases are published: `v0.6.0`
(tag target `e23d778c`) and `v0.6.1` (tag target `8e84c17f`), both on 2026-10-11.
Each public protocol release must match the package version and include the
reproduction artifact and validation evidence. A prerelease is not a production
release (see Claim boundary).

## Required gate

1. Start from the exact default-branch commit to be released.
2. Reproduce the repository quickstart in a clean environment.
3. Confirm all required GitHub checks pass on that commit.
4. Update the changelog or prepare generated release notes.
5. Create an annotated Semantic Versioning tag: `vMAJOR.MINOR.PATCH`.
6. Create a GitHub release from that exact tag.
7. Verify any package registry version and digest match the release.

## Claim boundary

A release proves a versioned artifact exists. It does not prove production
readiness, security certification, third-party validation, adoption, revenue,
or performance. Those claims require separate evidence.
