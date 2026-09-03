# Audit Finding Disposition

| ID | Status | Disposition |
| --- | --- | --- |
| AUD-018 | CORRECTED_IN_REPAIR_4 | Corrupted Repair 3 source is preserved; Repair 4 uses ASCII source lock and control-byte scan. |
| AUD-019 | CORRECTED_IN_REPAIR_4 | pre_state.commitment is hex64 string. |
| AUD-020 | CORRECTED_IN_REPAIR_4 | evidence_deadline is timestamp string with lexical and semantic calendar validation. |
| AUD-021 | CORRECTED_IN_REPAIR_4 | Extensions fail closed: critical_extensions maxItems=0 and noncritical_extensions maxProperties=0. |
| AUD-022 | CORRECTED_IN_REPAIR_4 | Validator tests every mismatched signed_artifact_type/signed_artifact_domain pair. |
| AUD-023 | CORRECTED_IN_REPAIR_4 | Canonical transition package source appendix maps nested fields to source. |
| AUD-024 | CORRECTED_IN_REPAIR_4 | Strict Base64url decode/reencode canonicality is specified for signatures and future public keys. |
