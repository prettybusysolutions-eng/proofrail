# Gate 1 Internal Fidelity Red-Team

Status: INTERNAL REVIEW ONLY — NOT INDEPENDENT VALIDATION

Target head before corrective extraction: `8a8127002610e2d637f6b2fccb8529e6b9f86496`

Authoritative source: `esrm-conformance/v0.1-repair4/docs/ESRM_PROTOCOL_SECTIONS_22_40_SOURCE_LOCKED_ASCII.md`

## Purpose

This pass deliberately compares the Gate 1 derivation against Repair 4 before external review. It must not be represented as independent validation. Its only purpose is to find omissions, compressions, or overreach cheaply before an independent reviewer evaluates the package.

## Finding

`GATE1_STRUCTURAL_CI=PASS` did not imply `SOURCE_EXTRACTION_COMPLETE=TRUE`.

The first extraction covered Sections 22–40, but several security-relevant source requirements were compressed into broad rules or omitted from explicit rule/test mapping. A serious reviewer could therefore correctly classify parts of the derivation as PARTIAL or MISSING even though the structural validator passed.

## Corrective findings

The following source concerns require explicit extraction or stronger corpus coverage:

- Section 23: registered-domain byte grammar, NUL exclusion inside domain strings, and version-specific domains.
- Section 24: implementations must not dynamically construct security domains from artifact type.
- Section 26: the top-level JSON value must be an object, not merely a single JSON value.
- Section 28: quantities requiring signed, large, decimal, money, timestamp, hash, cryptographic, or arbitrary-precision representation must use strings with explicit grammars.
- Section 29: issued/observed/received/expires/evidence-deadline roles are distinct, and wall-clock values establish temporal validity only under a committed clock policy.
- Section 30: array reordering constraints and commitment of all extension material must remain explicit.
- Section 31: reconciliation conclusions are ADJUDICATED and are not themselves empirical evidence.
- Section 32: closed-world coverage evidence must be retained as well as cryptographically committed.
- Section 33: RESERVATION_CANCELLED is distinct from AUTHORITY_CONSUMED; reservation cancellation is permitted only before consumption; consumed transition identifiers must not be reused.
- Sections 34–36: the explicit dispatch lifecycle, ordered durable consumption/crossing boundary, and required dispatch-intent / dispatch-crossing artifact fields need direct mapping.
- Section 37: capability class closed set, transition-time capability evidence binding, QUERYABLE_EFFECT negative-result semantics, and OBSERVABLE_ONLY/OPAQUE_TARGET retry restrictions require explicit mapping.
- Section 39: transport-attempt records must remain distinguishable from transition, observation, reconciliation, and settlement artifacts.
- Section 40: the byte-level protocol boundary and external-execution boundary ordering should be explicit conformance concerns, not only narrative architecture.

## Disposition

Do not request an external `READY_FOR_VECTOR_DESIGN` recommendation until these concerns are represented in the rule registry, corpus manifest, and structural validator.

The independent reviewer remains free to find additional defects. Correcting this list does not establish completeness.