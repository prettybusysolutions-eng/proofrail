# Grantifold — Provisional Naming and Python Packaging Migration

**Status (2026-11-04): working name only.** No trademark ownership or
registration is claimed. This is a technical disambiguation and is not a legal
clearance opinion. Obtain an attorney-led search before public brand investment.

## Verified naming conflict

The historical project used `ProofRail`; another publisher, DrDeese, controls
`proofrail` on PyPI as of the current check, and other software projects use
the same brand. `pip install proofrail` therefore **does not install this
project**. This repository and its SHA history are unaltered by the migration.

## Safe entry points from THIS repository

```bash
git clone https://github.com/prettybusysolutions-eng/proofrail.git
cd proofrail
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/grantifold reproduce examples/reproduce_artifact/
.venv/bin/grantifold compare-github-prs --help
```

The local source distribution metadata uses `grantifold`, subject to final
brand clearance and publishing review; **it is not yet a verified or owned
PyPI project**. Installing from this trusted source checkout is currently
the supported way to exercise the provisional new CLI.

## Compatibility and integrity

- `proofrail` and `proofrail-server` remain local installed CLI aliases
  for transition, alongside `grantifold` and `grantifold-server`.
- The Python import package remains `proofrail` for compatibility with existing
  source/tests. This does not imply that the name is a cleared mark.
- Existing `proofrail.*` JSON kinds, signed manifests, key IDs, validation
  fixtures, cryptographic domain separators and package paths are **not**
  blindly renamed: changing them would invalidate existing reproducible
  evidence and may require a versioned schema migration.
- The repository URL `prettybusysolutions-eng/proofrail` remains the actual,
  verified address. GitHub repository renaming is deferred until existing
  links, Actions workflows, release tooling and buyer documentation have been
  inventoried and a redirect/backward-compatibility plan exists.
- Do not claim `pip install grantifold` works until a verified GitHub-to-PyPI
  publishing route exists and the uploaded distribution is independently
  confirmed.
- Apache-2.0 copyright and license obligations remain unchanged. This rebrand
  does not assign IP or revoke any prior open-source grants.

## Unresolved before a permanent commercial launch

1. Current and comprehensive trademark clearance for Grantifold, including
   common-law uses and lookalike marks; the absence of an exact-indexed hit
   does not prove availability.
2. Domain, DNS, professional email and PyPI namespace reservation (not yet done).
3. Chain of title for the source and executed company/individual IP transfers
   where legally required.
4. Signed-authorization GitHub App enforcement sandbox, third-party security
   evaluation and buyer-facing claims review (tracked separately in Issue #71).
5. Update every shipping/install guide and external integration only after the
   verified migration, not by replacing arbitrary text inside signed records.
