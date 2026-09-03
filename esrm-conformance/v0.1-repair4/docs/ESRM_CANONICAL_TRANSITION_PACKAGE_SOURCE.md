# ESRM Canonical Transition Package Source

Status: Repair 4 locked normative appendix for the canonical transition body. This appendix supplies the transition package source mapping that Repair 3 lacked. It does not implement lifecycle, dispatch, reconciliation, settlement, recovery, Rust, Go, or vector generation.

## Canonical Unsigned Transition Body

NORMATIVE:
- ESRM-CTP-MUST-001: A transition artifact MUST contain artifact_type equal to proofrail.transition.
- ESRM-CTP-MUST-002: A transition artifact MUST contain protocol_version equal to 0.1.
- ESRM-CTP-MUST-003: A transition artifact MUST contain crypto_suite equal to PR-ESRM-JCS-SHA256-ED25519-v1.
- ESRM-CTP-MUST-004: A transition artifact MUST contain transition_id.
- ESRM-CTP-MUST-005: A transition artifact MUST contain nonce.
- ESRM-CTP-MUST-006: A transition artifact MUST contain epoch.
- ESRM-CTP-MUST-007: pre_state MUST contain commitment, source_set_commitment, and freshness_policy_commitment.
- ESRM-CTP-MUST-008: rules MUST contain ruleset_commitment and semantics_version.
- ESRM-CTP-MUST-009: authority MUST contain authority_commitment, issuer_id, subject_id, and lineage_commitment.
- ESRM-CTP-MUST-010: transition MUST contain operation_commitment, effect_commitment, and expected_post_state_commitment.
- ESRM-CTP-MUST-011: execution MUST contain executor_identity_commitment, target_commitment, precondition_commitment, and idempotency_commitment.
- ESRM-CTP-MUST-012: settlement MUST contain predicate_commitment, observer_policy_commitment, and evidence_deadline.
- ESRM-CTP-MUST-013: critical_extensions MUST equal an empty array until extension semantics are frozen.
- ESRM-CTP-MUST-014: noncritical_extensions MUST equal an empty object until extension semantics are frozen.
- ESRM-CTP-MUST-015: All commitment fields MUST be exactly 64 lowercase hexadecimal characters.
- ESRM-CTP-MUST-016: evidence_deadline MUST use timestamp grammar YYYY-MM-DDTHH:MM:SSZ.
- ESRM-CTP-MUST-NOT-001: A transition artifact MUST NOT contain unspecified top-level members.
- ESRM-CTP-MUST-NOT-002: A transition nested object MUST NOT contain unspecified members.

Canonical field outline:
```text
artifact_type = "proofrail.transition"
protocol_version = "0.1"
crypto_suite = "PR-ESRM-JCS-SHA256-ED25519-v1"
transition_id
nonce
epoch
pre_state:
  commitment
  source_set_commitment
  freshness_policy_commitment
rules:
  ruleset_commitment
  semantics_version
authority:
  authority_commitment
  issuer_id
  subject_id
  lineage_commitment
transition:
  operation_commitment
  effect_commitment
  expected_post_state_commitment
execution:
  executor_identity_commitment
  target_commitment
  precondition_commitment
  idempotency_commitment
settlement:
  predicate_commitment
  observer_policy_commitment
  evidence_deadline
critical_extensions = []
noncritical_extensions = {}
```
