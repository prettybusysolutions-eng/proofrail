"""Attack matrix: the handoff's required cases, the invariant each must hold, and the test that exercises it.

    python review_tools/attack_matrix.py          # runs the suite, writes docs/WRN_ACCEPTANCE_GATES.md

Results come from an actual pytest run (JUnit XML), never typed by hand. A case
with no test is listed as NOT TESTED with the reason.
"""
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PILOT = Path(__file__).resolve().parents[1]
DOC = PILOT.parents[1] / 'docs' / 'WRN_ACCEPTANCE_GATES.md'

S, A, O, F, I, R = ('test_scenarios', 'test_authority_attacks', 'test_outcome_attacks', 'test_financial_attacks',
                    'test_isolation_and_recovery', 'test_adapter_attacks')
B, C = 'test_bundle', 'test_check_reasons'

# (class, case, invariant, provider side effects asserted, test module, test function or None, note)
MATRIX = [
    # ---- demonstrations
    ('Scenario', 'A: authorized success', 'every claim recorded separately; simulated settlement only', '1 order', S, 'test_A_authorized_success_keeps_every_claim_separate', ''),
    ('Scenario', 'B: quote / provider / area / cap changed after approval', 'original authority refused', '0 orders', S, 'test_B_changed_scope_rejects_the_original_authority', ''),
    ('Scenario', 'C: replay, including after process restart', 'no second work order', '1 order', S, 'test_C_replay_creates_no_second_work_order_including_after_restart', ''),
    ('Scenario', 'D: contractor claims done, inspection disagrees', 'execution RECONCILED, outcome REJECTED, not payable', '1 order', S, 'test_D_false_completion_never_becomes_a_verified_outcome', ''),
    ('Scenario', 'E1: timeout after the provider stored the order', 'reconciled from observation, never retried', '1 order, 1 call', S, 'test_E1_timeout_after_the_provider_stored_the_order', ''),
    ('Scenario', 'E2: connection dropped before any effect', 'stays EXECUTION_UNKNOWN; not retried', '0 orders, 1 call', S, 'test_E2_connection_dropped_before_any_effect_stays_unknown_and_is_not_retried', ''),
    ('Scenario', 'E3: provider dies mid-request, confirms after restart', 'unknown, then reconciled by reads only', '1 order, 1 call', S, 'test_E3_provider_dies_after_accepting_then_confirms_after_restart', ''),
    # ---- authority
    ('Authority', 'Forged issuer (another key)', 'refused: issuer_key_changed', '0', A, 'test_forged_issuer_with_another_key', ''),
    ('Authority', 'Forged issuer claiming the real key id', 'refused: invalid_envelope', '0', A, 'test_forged_issuer_claiming_the_real_key_id', ''),
    ('Authority', 'Incorrect signature (altered after signing)', 'refused: invalid_envelope', '0', A, 'test_altered_after_signing', ''),
    ('Authority', 'Incorrect issuer role', 'refused: issuer_changed', '0', A, 'test_issuer_role_other_than_verifier', ''),
    ('Authority', 'Wrong target', 'refused: target_changed', '0', A, 'test_validly_signed_wrong_target_string', ''),
    ('Authority', 'Changed parameters (validly signed)', 'refused: parameters_changed / target_changed', '0', A, 'test_validly_signed_but_wrong_effect', ''),
    ('Authority', 'Changed approval digest', 'refused: approval_scope_changed', '0', A, 'test_validly_signed_other_approval_digest', ''),
    ('Authority', 'Changed evidence / policy / identity / state root', 'refused: <root>_root_changed', '0', A, 'test_validly_signed_with_a_wrong_root', ''),
    ('Authority', 'Evidence changed after its root was approved', 'refused: evidence_root_changed', '0', A, 'test_evidence_changed_after_its_root_was_approved', ''),
    ('Authority', 'Policy changed after issuance', 'refused: policy_root_changed', '0', A, 'test_policy_changed_after_issuance', ''),
    ('Authority', 'Expired permit', 'refused: permit_expired', '0', A, 'test_expired', ''),
    ('Authority', 'Issued in the future (not-before)', 'refused: authority_not_yet_valid', '0', A, 'test_issued_in_the_future', ''),
    ('Authority', 'Duplicate nonce across two cases', 'second refused: permit_replayed', '1 order', A, 'test_duplicate_nonce_across_two_cases', ''),
    ('Authority', 'Replay of consumed permit', 'refused: permit_replayed', '1 order', S, 'test_C_replay_creates_no_second_work_order_including_after_restart', ''),
    ('Authority', 'Replay following process restart', 'refused: permit_replayed', '1 order', S, 'test_C_replay_creates_no_second_work_order_including_after_restart', ''),
    ('Authority', 'State drift (problem revised)', 'refused: state_root_changed', '0', A, 'test_state_drift_problem_revised', ''),
    ('Authority', 'Counter / checkpoint rollback', 'checkpoint-bearing envelopes refused (unsupported)', '0', A, 'test_checkpoint_bearing_authority_not_supported', 'Checkpoint epoch/counter integration is not implemented; see L-1.'),
    ('Authority', 'Conflicting concurrent attempts (two processes)', 'exactly one admitted', '1 order', A, 'test_concurrent_admission_from_two_processes', ''),
    ('Authority', 'Two permits for one case', 'second refused: state_root_changed', '1 order', A, 'test_two_approved_envelopes_for_one_case', ''),
    ('Authority', 'Approval revoked during admission', 'authority spent, no provider call, not reconcilable', '0, 0 calls', A, 'test_revoked_during_admission_stops_the_provider_call', ''),
    ('Authority', 'Tenant identity changes between authorization and dispatch', 'refused: identity_root_changed', '0', A, 'test_identity_changed_between_authorization_and_dispatch', ''),
    ('Authority', 'Subject is another executor', 'refused: subject_changed', '0', A, 'test_subject_is_another_executor', ''),
    ('Authority', 'Another tenant\'s issuer', 'refused: issuer_changed', '0', A, 'test_envelope_from_another_tenants_issuer', ''),
    ('Authority', 'Replay registry rolled back alone', 'refused: authority_already_admitted', 'no new order', A, 'test_replay_registry_rolled_back_alone', ''),
    # ---- adapter
    ('Adapter', 'Fake provider success (nothing created)', 'RECONCILIATION_FAILED', '0', R, 'test_fabricated_success_with_no_orders_at_all', ''),
    ('Adapter', 'HTTP success for the wrong external operation', 'RECONCILIATION_FAILED: provider_success_not_observed', 'unrelated order only', R, 'test_success_response_for_a_different_operation_is_not_attribution', ''),
    ('Adapter', 'Partial execution followed by timeout', 'reconciled by observation only', '1 order', S, 'test_E1_timeout_after_the_provider_stored_the_order', ''),
    ('Adapter', 'Malformed provider output', 'resolved by observation only', '1 order', R, 'test_malformed_success_body_is_resolved_only_by_observation', ''),
    ('Adapter', 'Provider succeeds while local process crashes', 'CONSUMED → reconciled after restart, no second call', '1 order', I, 'test_gateway_process_dies_while_the_provider_call_is_in_flight', ''),
    ('Adapter', 'Duplicate idempotency key / no idempotency', 'duplicates detected: RECONCILIATION_FAILED', '2 orders (forced)', R, 'test_provider_without_idempotency_duplicates_are_detected', ''),
    ('Adapter', 'Work-order record substituted after reconciliation', 'settlement denied: work_order_changed_since_reconciliation', '1 order', R, 'test_provider_record_changed_after_reconciliation_blocks_settlement', ''),
    ('Adapter', 'Provider stored different parameters', 'RECONCILIATION_FAILED: work_order_differs_from_authorized_effect', '1 order', R, 'test_order_stored_with_different_parameters_is_not_reconciled', ''),
    ('Adapter', 'Provider response belongs to another tenant', 'RECONCILIATION_FAILED: provider_response_inconsistent_with_observation', '1 order', R, 'test_response_naming_another_tenant', ''),
    ('Adapter', 'Provider status changes between reads', 'reconciliation not re-decided', '1 order', R, 'test_status_changing_between_reads_does_not_flip_reconciliation', ''),
    ('Adapter', 'Provider cannot guarantee idempotent creation', 'duplicates detected', '2 (forced)', R, 'test_provider_without_idempotency_duplicates_are_detected', ''),
    ('Adapter', 'Provider unreadable after create', 'EXECUTION_UNKNOWN, then reconciled', '1 order', R, 'test_provider_unreadable_after_create_is_unknown_not_success', ''),
    # ---- outcome
    ('Outcome', 'Contractor self-certifies completion', 'INSUFFICIENT_EVIDENCE; claim excluded', '—', O, 'test_contractor_self_certification_alone_is_insufficient', ''),
    ('Outcome', 'Photo of a different facility', 'excluded: evidence_location_mismatch', '—', O, 'test_photo_from_a_different_facility', ''),
    ('Outcome', 'Old photo reused', 'excluded: evidence_reused_from_problem_report / predates order', '—', O, 'test_old_photo_reused_from_the_problem_report', ''),
    ('Outcome', 'Observer credential unauthorized', 'excluded: inspector_not_designated_by_buyer / signature_invalid', '—', O, 'test_inspector_not_designated_by_the_buyer', ''),
    ('Outcome', 'Same party as executor and reviewer', 'refused: reviewer_not_independent_of_performer', '—', O, 'test_performer_cannot_be_the_reviewer', ''),
    ('Outcome', 'Provider-employed inspector', 'excluded: inspector_not_independent_of_performer', '—', O, 'test_inspector_employed_by_the_provider', ''),
    ('Outcome', 'Signed but factually contradicted', 'DISPUTED', '—', O, 'test_signed_but_contradicted_by_another_qualified_inspection', ''),
    ('Outcome', 'Acceptance criteria change after work begins', 'amend refused; tampered plan → acceptance_criteria_changed', '—', O, 'test_acceptance_criteria_changed_after_work_began', ''),
    ('Outcome', 'Inspection after the allowed window', 'excluded: inspection_after_allowed_window', '—', O, 'test_inspection_after_the_allowed_window', ''),
    ('Outcome', 'Missing observation evidence', 'excluded: inspection_without_evidence', '—', O, 'test_inspection_without_evidence', ''),
    ('Outcome', 'Two reviewers, conflicting decisions', 'rule-computed verdicts agree on the same evidence; definite disagreement is DISPUTED', '—', O, 'test_reviewers_cannot_reach_different_verdicts_on_the_same_evidence', ''),
    # ---- financial
    ('Financial', 'Duplicate settlement request', 'DENIED: duplicate_settlement', '—', F, 'test_duplicate_settlement_request', ''),
    ('Financial', 'Amount exceeds approved cap', 'DENIED: amount_exceeds_approved_cap', '—', F, 'test_amount_above_the_approved_cap', ''),
    ('Financial', 'Settlement attached to a different work order', 'DENIED: invoice_for_other_work_order', '—', F, 'test_invoice_for_a_different_work_order', ''),
    ('Financial', 'Previously rejected outcome becomes payable', 'DENIED: outcome_previously_rejected_or_disputed', '—', F, 'test_later_verified_verdict_does_not_override_an_earlier_rejection', ''),
    ('Financial', 'Settlement before buyer acceptance', 'DENIED: buyer_acceptance_missing', '—', F, 'test_settlement_before_buyer_acceptance', ''),
    ('Financial', 'Currency mismatch', 'DENIED: currency_mismatch', '—', F, 'test_currency_mismatch', ''),
    ('Financial', 'Forged invoice reference', 'DENIED: invoice_signature_invalid', '—', F, 'test_forged_invoice', ''),
    ('Financial', 'Replayed payment authorization', 'DENIED: duplicate_settlement; one authorization', '—', F, 'test_replayed_settlement_authorization_after_close', ''),
    ('Financial', 'Reviewer also authorizes settlement', 'DENIED: authorizer_not_independent', '—', F, 'test_reviewer_cannot_also_authorize_settlement', ''),
    # ---- isolation and privacy
    ('Isolation', 'Cross-tenant read', 'indistinguishable from missing: not_found', '—', I, 'test_cross_tenant_read_looks_like_a_missing_record', ''),
    ('Isolation', 'Cross-tenant mutation', 'refused before any tenant data is read', '—', I, 'test_cross_tenant_mutation_is_refused', ''),
    ('Isolation', 'Other tenant\'s gateway spends authority', 'refused: tenant_mismatch', '0', I, 'test_other_tenants_gateway_cannot_spend_this_tenants_authority', ''),
    ('Isolation', 'Unauthorized evidence export', 'refused: export_not_permitted', '—', B, 'test_export_requires_a_tenant_evidence_role', ''),
    ('Isolation', 'Unauthorized reviewer', 'refused: reviewer_not_permitted', '—', C, 'test_assessment_preconditions', ''),
    ('Isolation', 'Secret leakage in error messages', 'reason codes only', '—', I, 'test_refusals_carry_reason_codes_only', ''),
    ('Isolation', 'Sensitive content in telemetry', '—', '—', None, None, 'No telemetry is emitted yet (L-7).'),
    ('Isolation', 'Deleted evidence referenced by an accepted claim', '—', '—', None, None, 'Evidence blobs are not stored (L-8).'),
    ('Isolation', 'Bundle excludes other tenants and private material', 'no private keys, databases or tenant-b data', '—', B, 'test_bundle_holds_no_private_material_or_other_tenants', ''),
    # ---- concurrency and recovery
    ('Recovery', 'Multiple worker processes', 'exactly one admission', '1 order', A, 'test_concurrent_admission_from_two_processes', ''),
    ('Recovery', 'Restart after consumption, before provider response', 'reconciled by reads; replay refused', '1 order', I, 'test_gateway_process_dies_while_the_provider_call_is_in_flight', ''),
    ('Recovery', 'Restore from stale backup (registry only)', 'refused: authority_already_admitted', 'no new order', A, 'test_replay_registry_rolled_back_alone', ''),
    ('Recovery', 'Restore of both stores (joint rollback)', 'KNOWN LIMIT: second provider call happens; idempotency prevents a second order', '1 order, 2 calls', I, 'test_joint_rollback_of_registry_and_business_store_is_a_known_limit', 'Documented limitation L-1, not a guarantee.'),
    ('Recovery', 'Retained registry unavailable', 'refused: authority_already_admitted', '1 order', I, 'test_replay_registry_missing_entirely', ''),
    ('Recovery', 'Corrupt ledger tail', 'edits detected; truncation NOT detected without a checkpoint', '—', I, 'test_audit_chain_detects_edits_but_not_tail_truncation', 'Truncation: limitation L-2.'),
    ('Recovery', 'Observer temporarily unavailable', 'EXECUTION_UNKNOWN', '—', I, 'test_observer_unavailable_keeps_the_outcome_unknown', ''),
    ('Recovery', 'Out-of-order provider events / conflicting callbacks', '—', '—', None, None, 'The pilot polls; no provider callbacks exist to reorder.'),
    # ---- portable evidence
    ('Evidence', 'Tampered records with regenerated checksums', 'the affected dimension fails', '—', B, 'test_tampering_fails_the_right_dimension_even_with_new_checksums', ''),
    ('Evidence', 'Mismatched external (provider) evidence', 'authenticity and execution fail', '—', B, 'test_provider_observation_tampered_to_show_a_different_order', ''),
    ('Evidence', 'Invalid trusted keys', 'authenticity fails', '—', B, 'test_trusted_keys_upgrade_and_mismatch', ''),
    ('Evidence', 'Missing physical proof', 'never presents VERIFIED', '—', B, 'test_case_without_inspection_never_presents_a_verified_outcome', ''),
    ('Evidence', 'Inspection removed from the bundle', 'verdict no longer reproduces', '—', B, 'test_removed_inspection_means_the_verdict_no_longer_reproduces', ''),
]


def run():
    with tempfile.TemporaryDirectory() as d:
        xml = Path(d) / 'results.xml'
        subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests/', f'--junitxml={xml}'],
                       cwd=PILOT, capture_output=True, text=True)
        outcomes = {}
        for case in ET.parse(xml).getroot().iter('testcase'):
            module = case.get('classname').split('.')[-1]
            name = case.get('name').split('[')[0]
            failed = any(child.tag in ('failure', 'error') for child in case)
            prior = outcomes.get((module, name), 'PASS')
            outcomes[(module, name)] = 'FAIL' if failed or prior == 'FAIL' else 'PASS'
    return outcomes


def main():
    outcomes = run()
    commit = subprocess.run(['git', '-C', str(PILOT), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(['git', '-C', str(PILOT), 'status', '--porcelain', '--', '.'],
                                capture_output=True, text=True).stdout.strip())
    rows, missing = [], []
    for cls, case, invariant, effects, module, test, note in MATRIX:
        if test is None:
            result = 'NOT TESTED'
        else:
            result = outcomes.get((module, test))
            if result is None:
                missing.append(f'{module}::{test}')
                result = 'MISSING TEST'
        where = f'`{module}::{test}`' if test else '—'
        rows.append(f'| {cls} | {case} | {invariant} | {effects} | {where} | **{result}** |' + (f' {note}' if note else ''))
    counts = {k: sum(1 for r in rows if f'**{k}**' in r) for k in ('PASS', 'FAIL', 'NOT TESTED', 'MISSING TEST')}
    text = f"""# WRN acceptance gates: facility-outcome pilot

Generated by `pilots/facility_outcomes/review_tools/attack_matrix.py` from an actual pytest run.
Source commit `{commit}`{' (working tree has uncommitted pilot changes)' if dirty else ''}.
Command: `cd pilots/facility_outcomes && python review_tools/attack_matrix.py`

Totals: {counts['PASS']} PASS, {counts['FAIL']} FAIL, {counts['NOT TESTED']} NOT TESTED, {counts['MISSING TEST']} MISSING TEST.
"Side effects" is what the test asserts about provider work orders and create calls.
These are author-run tests. INDEPENDENT VALIDATION: NOT COMPLETED.

| Class | Case | Invariant | Side effects | Test | Result |
|---|---|---|---|---|---|
""" + '\n'.join(rows) + f"""

## Enforcement coverage (mutation)

`review_tools/mutate_checks.py` disables each `require(...)`, outcome-exclusion and settlement-denial
check in turn and reruns the pilot suite. The latest result is recorded in
`pilots/facility_outcomes/README.md`.

## Exit gates (handoff Phase 2-4)

| Gate | Evidence | Status |
|---|---|---|
| Authorized synthetic success | Scenario A row | {'PASS' if outcomes.get((S, 'test_A_authorized_success_keeps_every_claim_separate')) == 'PASS' else 'FAIL'} |
| Altered scope rejected | Scenario B row | {'PASS' if outcomes.get((S, 'test_B_changed_scope_rejects_the_original_authority')) == 'PASS' else 'FAIL'} |
| Replay rejected | Scenario C row | {'PASS' if outcomes.get((S, 'test_C_replay_creates_no_second_work_order_including_after_restart')) == 'PASS' else 'FAIL'} |
| False completion rejected | Scenario D row | {'PASS' if outcomes.get((S, 'test_D_false_completion_never_becomes_a_verified_outcome')) == 'PASS' else 'FAIL'} |
| Ambiguous execution represented correctly | Scenario E1-E3 rows | {'PASS' if all(outcomes.get((S, t)) == 'PASS' for t in ('test_E1_timeout_after_the_provider_stored_the_order', 'test_E2_connection_dropped_before_any_effect_stays_unknown_and_is_not_retried', 'test_E3_provider_dies_after_accepting_then_confirms_after_restart')) else 'FAIL'} |
| Tampered records fail; missing physical proof never verifies | Evidence rows | {'PASS' if all(outcomes.get((B, t)) == 'PASS' for t in ('test_tampering_fails_the_right_dimension_even_with_new_checksums', 'test_case_without_inspection_never_presents_a_verified_outcome')) else 'FAIL'} |
| Real PostgreSQL / Compose integration | — | BLOCKED (no Docker daemon in this environment) |
| Independent review | — | NOT COMPLETED |
"""
    DOC.write_text(text)
    print(f"{counts} -> {DOC}")
    if missing:
        print('missing tests:', missing)
    return 1 if counts['FAIL'] or counts['MISSING TEST'] else 0


if __name__ == '__main__':
    sys.exit(main())
