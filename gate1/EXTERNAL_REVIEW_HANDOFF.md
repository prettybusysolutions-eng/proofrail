# External semantic review handoff

Status: PROJECT-AUTHORED HANDOFF; NO EXTERNAL REVIEWER ENGAGED; GATE 1B OPEN.

This document prepares an external engagement. It does not attest to third-party
authorship, independence, semantic correctness, or review completion.

## Exact scope

Review Repair 4 Sections 22–40 against the six derived artifacts identified by
`INDEPENDENT_REVIEW_PACKET.md`. The source commit is
`651f34bb9768dfafd53ede612ef01c9a01bd534d`; the V2 derivation target is
`f81f0ca55b065d60e8c8439eb85d6358c608a45b`.
The governing target marker is at `47d0cb89f9f2c353a45acd4d30920352d12ba3e7`.
The source SHA-256 is
`9a5300ecf355095186a1683b12871b2aa7f06ef824db3389c8e4422a62b32cef`.
See `external-review-inputs.json` for exact file hashes and roles.

The old review-request and reviewer-selection references to `a0a168e...` are
superseded. Updating handoff instructions does not change the semantic target.

## Separation of responsibility

1. The project custodian freezes inputs and supplies reproduction instructions.
2. The derivation author owns repairs, traceability, and a new candidate commit
   when any of the six derived artifacts changes. Authorship may be internal
   or external and must be attributed accurately.
3. A reviewer outside that authoring process verifies the frozen candidate.
   They must satisfy `REVIEWER_SELECTION.md`, disclose conflicts and tools,
   and control their own method and conclusions. They may identify fixes;
   authoring a replacement derivation makes them ineligible to independently
   accept that same replacement. Another eligible reviewer must assess it.
4. The project checks admissibility and preserves the original review. The
   reviewer’s conclusions are not rewritten into a project-authored approval.

Running another model, account, browser, or subagent does not establish
third-party independence. An external reviewer may use tools, but must disclose
material AI assistance, validate the work, and take responsibility for it.

## Engagement sequence and required output

- First request scope fit, a named reviewer, public competence evidence in at
  least two required areas, conflict disclosure, availability, and a written
  quote. No contract, budget, or recipient is selected by this handoff.
- Deliver immutable source and target inputs. Ask for an initial source-driven
  mapping before presenting the project's suggested verdicts. Preserve known
  issues as a separately labeled annex; disclose them before final review.
- Require every source obligation to map to rule IDs and planned cases, and
  every derived assertion to map back to source. Record source line ranges,
  exact input hashes, classifications, counterexamples, and ambiguities.
- Require one entry for each section 22–40 and explicit answers to all 14
  adversarial questions, with evidence and uncertainty where applicable.
- Require severity and disposition for every finding. No expected PASS is a
  condition of payment. Preserve original report bytes and their SHA-256,
  reviewer-controlled delivery identity, date, exact commits, relationship,
  compensation, competence evidence, and permitted-evidence declaration.
- The existing JSON schema does not enforce all these conditions. Preserve a
  separate signed or reviewer-attributable disclosure/answers document and
  check the complete package; JSON validation alone is insufficient.
- If a revised derivation is authored, freeze a new commit, retain the old
  findings and require review of the new target. Do not carry forward approval
  automatically from V2 or silently replace source semantics.

Any authentic external review, including a negative result, can be attributed
to its verified third-party author. A passing Gate 1B requires additional
acceptance conditions. This task keeps Gate 1B open even after receipt; no
automatic gate closure, vectors, or verifier authorization follows.

## Reproduction

In a clone containing the two frozen commits:

```sh
git show 651f34bb9768dfafd53ede612ef01c9a01bd534d:esrm-conformance/v0.1-repair4/docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md | sha256sum
git archive f81f0ca55b065d60e8c8439eb85d6358c608a45b gate1
```

Extract that archive into an isolated directory and run
`python gate1/tools/validate_gate1.py`. A structural PASS is not a semantic
verdict. The prior local PASS reported 65 rules, 19 sections, 17 corpus families
and 15 registered domains.

## Known-issues annex: corrections to the prior assistant report

The earlier assistant report is internal, provisional, and not admissible as
third-party acceptance. Its blanket all-MATCH conclusion is withdrawn pending
re-review. In particular:

- Section 29 says an alternative logical sequence is explicitly **defined**;
  ESRM-R29-002 says explicitly **committed**. Establish whether the added
  requirement is sourced or is overreach before marking MATCH.
- Section 31 requires a new reconciliation artifact **and**, when applicable,
  a new epoch. ESRM-R31-003 uses artifact **or** epoch. The corpus mentions
  a new reconciliation, but the registry wording still needs disposition.
- The measured 128/130 name mismatches compare rule family labels to corpus
  family names. They do not prove 128 absent tests or semantic omissions:
  the registry may use finer-grained labels. A documented mapping is needed;
  the two naming levels and proof of coverage must be distinguished.
- Result-schema checks alone do not ensure unique section coverage, target
  identity, actual answers, conflict disclosures, or factual independence.
  Their absence from the schema is a validation gap, not proof that those
  items cannot be supplied in an accompanying reviewer document.
- Section 38's blanket D/K/Q/F validity wording and cross-family rule need
  branch-sensitive review: do they incorrectly require unused evidence for
  an otherwise justified recovery branch? This is an open review question.

The six semantic artifacts remain frozen; this annex corrects the handoff,
not the normative source or candidate. No independent-review result has been
received, and reviewer independence has not been verified.

## Candidate contact route, unengaged

Trail of Bits is a possible assessment provider, based on its advertised
cryptographic protocol services, not a verified independent reviewer for this
project. Its official contact page is https://trailofbits.com/contact/ .
Pricing, availability, reviewer identity and conflicts remain unknown.
The owner must select the recipient and any spending limit before engagement.
