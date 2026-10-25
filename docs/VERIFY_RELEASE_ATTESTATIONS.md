# Verifying ProofRail release artifacts and provenance

Status: proposed verification procedure for **future** signed prereleases. Existing v0.6.0 and v0.6.1 prereleases contain checksums and unsigned provenance metadata; this procedure must not be used to imply they already have signed attestations.

## Obtain the release

Install the GitHub CLI (`gh`), and ensure you trust the repository identity `prettybusysolutions-eng/proofrail` independently of a downloaded asset. The public repository is the identity to verify, not a public key shipped in the same archive.

```sh
repo=prettybusysolutions-eng/proofrail
tag=vX.Y.Z
mkdir proofrail-release
gh release download "$tag" --repo "$repo" --dir proofrail-release
cd proofrail-release
sha256sum --check SHA256SUMS
```

The checksum file detects accidental changes relative to the published list. **It does not authenticate the publisher.** The historical checksum file does not include `provenance.json`; verification must not rely solely on checksums.

## Verify every signed asset against the expected workflow

Future prereleases built under the proposed workflow have a signed Sigstore-backed GitHub build-provenance attestation associated with each published asset.

```sh
repo=prettybusysolutions-eng/proofrail
signer=prettybusysolutions-eng/proofrail/.github/workflows/pilot-release.yml
for artifact in ./*.whl ./*.tar.gz ./SHA256SUMS ./provenance.json ./independent-review-inputs.zip; do
    test -f "$artifact" || exit 1
    gh attestation verify "$artifact" --repo "$repo" --signer-workflow "$signer" || exit 1
done
```

Check the verified certificate's workflow repository and source commit against the GitHub release tag's intended commit. A signer-workflow check narrows the trusted actor compared with repository-only verification. To run an offline verification, separately obtain the trusted root and attestation bundles according to [GitHub's offline verification guide](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline).

The proposed publishing workflow performs these checks **before** `gh release create`. If an attestation cannot be minted or verified, publication fails; it must not silently fall back to unsigned release assets.

## Interpretation and residual risks

A valid attestation proves an artifact digest is bound to the identity of a GitHub Actions workflow recorded in a signed certificate and its provenance statement. It is **not** proof that the code is bug-free, an independently validated security protocol, trusted key custody, a non-bypassable GitHub merge gate or production readiness.

Build-workflow compromise, insufficient branch protection, unreviewed changes to release permissions, trust in the GitHub/Sigstore infrastructure and private signing-root lifecycle remain distinct risks. Preserve verified attestations and exact commit references when collecting independent review evidence.

**Never** use the existing `provenance.json` field `signature: "unsigned workflow metadata"` as a signing check. The proposed workflow does not replace this metadata file with a cryptographic signature; it attests to the asset that contains it.
