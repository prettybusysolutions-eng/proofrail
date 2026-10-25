# Public Release Boundary

This repository is a sanitized, code-only public release of ProofRail.

It contains:

- the ProofRail protocol and reference implementation;
- the Action Authority Envelope v1 protocol draft;
- technical security and trust-boundary documentation;
- schemas, tests, adversarial suites, examples, and reproduction artifacts.

It intentionally excludes private operating records, outreach history,
contact ledgers, commercial tracking, collaborator-invite evidence, and
private repository history.

The release was exported from the verified technical baseline ending at:

```text
319931b8f18acb7396470cb1235f5e68280ce8de
```

That identifier is provenance only. The public repository begins with a clean
history so omitted private records cannot be recovered from earlier commits.

## Honest Status

ProofRail is an open protocol draft and reference implementation. It is not:

- a standards-body specification;
- third-party validated;
- production infrastructure;
- a hosted managed service;
- proof of market adoption.

The public evidence is independently replayable. Independent authorship,
cross-implementation conformance, and production hardening remain future
evidence gates.

## Pilot artifact publication

The pilot publication workflow builds a wheel and source distribution from one
exact main commit, repeats the source suite, and verifies installed-wheel
reproduction and tamper rejection before creating a prerelease. Historical v0.6.0/v0.6.1 prereleases include SHA256SUMS and unsigned workflow
provenance metadata identifying the source commit and run. Neither historical
release has the signed build attestations now proposed in draft governance work.

The next release workflow revision is intended to be manually initiated,
attest every release asset using Sigstore-backed GitHub provenance and verify
each attestation before publishing. An existing tag or release must never be
silently replaced. See `RELEASING.md` and
`docs/VERIFY_RELEASE_ATTESTATIONS.md`. A configured workflow is not a verified
signing practice until its first signed release is independently checked.

Publishing the pilot does not satisfy independent semantic review or external
reproduction. Both remain distinct, externally supplied evidence gates.
