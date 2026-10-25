# Releasing ProofRail

## Current published state (verified 2026-10-25)

- `v0.6.0` and `v0.6.1` were published as GitHub prereleases on **2026-10-11**.
- The latest published prerelease is [v0.6.1](https://github.com/prettybusysolutions-eng/proofrail/releases/tag/v0.6.1), matching the version currently declared in `pyproject.toml`.
- Both historical prereleases have checksums and **unsigned** `provenance.json` workflow metadata, not signed build provenance.
- Draft authority-envelope, facility-pilot, dispatcher and trust-hardening PRs are **not included** in v0.6.1. The next version must be chosen after review and successful integration.

## Future release gate (proposed; not yet exercised)

1. Merge reviewed changes under enforced repository rules (an admin must confirm branch rules and authorization). Do not merge solely because an AI agent or its own CI says PASS.
2. Verify the exact `main` commit, source tests, installed wheel, reproducible examples, documented migrations, and compatibility changes.
3. Update `CHANGELOG.md`, the project version and release notes for the **actual** merged changes. Confirm the release version has no existing tag or release; no replacing old assets.
4. Have an authorized maintainer manually start the `Publish tested pilot` GitHub Actions workflow on `main`. It must not be triggered simply by a push.
5. In the release job, build wheel, sdist and independent-review input archive, compute hashes, and publish signed Sigstore-backed build provenance attestations for **every asset**. Verify every asset's digest, expected repository, signer workflow and source commit **before** publication. If signing or verification fails, do not publish.
6. The workflow publishes a prerelease from the exact source commit; a versioned tag is created by `gh release create`. An administrator may additionally require a separately signed or annotated tag through a reviewed change to this workflow.
7. Have an external evaluator download the artifacts and follow [release attestation verification](docs/VERIFY_RELEASE_ATTESTATIONS.md). Archive the exact tag, source SHA, attestation verification output and evaluation limits.

**Important:** merely merging this workflow change does not create or validate an attestation. The first manual future release must pass a witnessed execution test; absent that evidence, mark signed-release controls **configured but unverified**.

## Claim boundary

A successful signed build-provenance attestation binds an artifact digest to the certified workflow identity. It does not establish an independent semantic review, production safety, a paid deployment, reliable real-world provider authorization, or independently witnessed trust checkpoints. Those are separate gates.
