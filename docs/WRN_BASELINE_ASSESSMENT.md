# WRN Phase 0: baseline assessment

Recorded 2026-10-23 by the implementing agent (author-run; not independent review).

## Baseline

| Item | Observed |
|---|---|
| Repository | `prettybusysolutions-eng/proofrail` |
| Branch / commit | `main` @ `807a1117910ff6373ce7d3b25d86eb48652d46d6` (committed 2026-10-19), matching the handoff |
| Working tree | clean worktree from `origin/main`; work proceeds on `feat/verified-outcome-facility-pilot` |
| Package version | `0.6.1` (`pyproject.toml`) |
| GitHub releases | `v0.6.0` (prerelease, target `e23d778c`), `v0.6.1` (prerelease, target `8e84c17f`), both published 2026-10-11; tags match |
| Branch protection | `main` reports `protected=true`; the rule details are not readable through this integration and are **not** assumed |
| Checks at baseline | restore-backup, create-backup, attestation-check, installed-artifact 3.11/3.12/3.14: all `success` (2026-10-19) |
| Local interpreter | Python 3.13.16 (requirement: 3.11+) |
| Dependencies | cryptography 50.0.2, jsonschema 4.26.0, rfc8785 0.1.4, referencing 0.37.0, attrs 26.1.0, cffi 2.1.1, pycparser 3.12, rpds-py 2026.9.1 |

## Existing suites, run locally

| Command | Result |
|---|---|
| `python -m unittest discover -s tests -v` | 105 tests, OK |
| `python scripts/check_adapter_e2e.py` | "6 adapters checked, OK" |
| `proofrail reproduce examples/reproduce_artifact/` | `valid: true`, `key_trust: self_asserted`. Internal consistency only: a bundle re-signed with a new key also verifies unless `--trusted-keys` is supplied |
| `python scripts/generate_validation_report.py` | regenerated `validation-results.json` is byte-identical to the committed file; the report differs only in the evidence filename passed on the command line. 13/13 adversarial expectations reproduce |
| `python adversarial/<suite>.py` | fails with `ImportError` (relative imports). Not a defect: the suites are case libraries run through the report generator, as CI does |

No failures were masked. None needed masking.

## Code compared with documentation

1. **The Action Authority Envelope v1 is not connected to execution on `main`.**
   `proofrail/envelope.py` provides `mint_action_authority_envelope` and
   `verify_action_authority_envelope`. The only callers are their unit tests.
   There is no envelope consumption, replay registration or adapter. The GitHub
   merge and SQLite migration paths use their own permit kinds (`consume_permit`,
   `proofrail.execution-permit.v0.2`). The facility pilot therefore builds the
   envelope-to-execution integration explicitly
   (`pilots/facility_outcomes/proofrail_gateway.py`) as a new capability.
2. **`verify_action_authority_envelope` checks less than `verify_permit`.**
   It checks the schema, signature, expiry, the four roots, the approval digest
   and the exact effect. It does **not** check:
   - the issuer role against `PERMIT_ISSUER_ROLES` (that is enforced only when
     minting);
   - the subject (which executor the authority is for);
   - the `state`, beyond what the schema enforces;
   - `failure_semantics`.

   A caller relying on it alone would accept authority minted outside
   `mint_action_authority_envelope` with a non-verifier issuer role, as long as
   the key verifies. The pilot gateway enforces all four. A core fix is proposed
   in `docs/WRN_THREAT_MODEL.md` (finding F-1); `proofrail/` is not changed in
   this phase.
3. **`RELEASING.md` is stale.** It says the package declares `0.6.0` and that no
   release is published; the package is `0.6.1` and two prereleases exist. It
   also contains escaped backticks (`\`vMAJOR.MINOR.PATCH\``). Corrected in this
   branch.
4. **`docs/KNOWN_LIMITATIONS.md` is headed "ProofRail v0.5 Known Limitations".**
   The heading is corrected to name the package version; the limitations
   themselves are unchanged.
5. **The ESRM Gate 1B targets are frozen and left untouched.**
   `docs/OPERATIONAL_ACCEPTANCE.md` gives:
   - handoff metadata at `55fa2c47608287e9b22d09c7982d9949b079a232`;
   - semantic comparison of source `651f34bb9768dfafd53ede612ef01c9a01bd534d`
     against derivation `f81f0ca55b065d60e8c8439eb85d6358c608a45b`.

   Nothing in this branch touches those artifacts.

## Live evidence carried forward

`evidence/live-github-2026-10-19/README.md`: GitHub answered 200 to a merge
request on an already-merged pull request whose merged head was not the
authorized one, and the older adapter attributed that merge to its own authority.
This becomes a pilot rule: **a successful provider response never establishes
the authorized effect**. The pilot confirms work orders only from an
independent read of provider state that matches the exact authorized effect, and
tests a provider that answers success for a different operation (adapter attack
A-2 in `docs/WRN_ACCEPTANCE_GATES.md`).

## Environment blockers

- **No Docker daemon** (`/var/run/docker.sock` absent). The PostgreSQL / Docker
  Compose stack the handoff suggests cannot run here. The pilot's business records
  use SQLite behind a small storage interface. ProofRail's replay registry stays
  SQLite in any case, as the handoff requires. Recorded as a limitation, not
  worked around.
- **No live work-order provider.** The provider is a local HTTP simulator, as the
  handoff specifies.

## Exit gate

- Exact baseline identified: yes.
- Existing suite results recorded: yes; all pass.
- Security regression introduced: none (no `proofrail/` code changed in Phase 0).
- Actual limitations documented: yes (above and in `docs/KNOWN_LIMITATIONS.md`).

Status: **PASS — EXECUTED AND VERIFIED** for Phase 0's scope.
INDEPENDENT VALIDATION: NOT COMPLETED
