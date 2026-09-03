# Audit Finding Disposition

| ID | Finding | Status | Disposition |
| --- | --- | --- | --- |
| AUD-001 | authoritative ESRM numbering replaced | CORRECTED_IN_REPAIR_2 | Protocol Sections 22-40 and harness requirements are now separate; Section 22 title restored. |
| AUD-002 | recursive raw/canonical hashes | CORRECTED_IN_REPAIR_2 | Subject schemas contain no raw_sha256 or canonical_sha256. |
| AUD-003 | domain commitment formula absent | CORRECTED_IN_REPAIR_2 | C_x = SHA256(ASCII(RegisteredDomain(artifact_type)) || 0x00 || B_x) is normative. |
| AUD-004 | transition schema semantically replaced | CORRECTED_IN_REPAIR_2 | Transition schema restores supplied canonical package fields. |
| AUD-005 | signature envelope semantically replaced | CORRECTED_IN_REPAIR_2 | Signature schema restores E_tau plus signature; public key omitted. |
| AUD-006 | registered domains changed | CORRECTED_IN_REPAIR_2 | Uppercase domains restored. |
| AUD-007 | mandatory headers incomplete | CORRECTED_IN_REPAIR_2 | Mandatory header fields required in both governed schemas. |
| AUD-008 | binary manifest contains no binary vectors | CORRECTED_IN_REPAIR_2 | Artifact is renamed binary-vector-plan.json and does not claim populated vectors. |
| AUD-009 | reproduction script absent | CORRECTED_IN_REPAIR_2 | Generation and validation scripts are committed. |
| AUD-010 | release-root hash mislabeled | CORRECTED_IN_REPAIR_2 | file_hash_manifest_sha256 and release_root_record_sha256 are distinct. |
