#!/usr/bin/env python3
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES = ROOT / "esrm-rule-registry.json"
ROLES = ROOT / "artifact-role-registry.json"
CORPUS = ROOT / "conformance-corpus-manifest.json"


def load(path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def require(condition, message, failures):
    if not condition:
        failures.append(message)


def main():
    failures = []
    rules_doc = load(RULES)
    roles_doc = load(ROLES)
    corpus_doc = load(CORPUS)

    rules = rules_doc.get("rules", [])
    ids = [r.get("id") for r in rules]
    require(len(ids) == len(set(ids)), "duplicate rule IDs", failures)
    require(all(ids), "empty rule ID", failures)

    expected_sections = set(range(22, 41))
    rule_sections = {r.get("section") for r in rules}
    require(rule_sections == expected_sections,
            f"rule section coverage mismatch: got {sorted(rule_sections)}",
            failures)

    for rule in rules:
        rid = rule.get("id", "<missing>")
        section = rule.get("section")
        require(isinstance(section, int) and 22 <= section <= 40,
                f"{rid}: invalid section", failures)
        for key in ("concern", "roles", "stage", "positive_family", "negative_family", "expected"):
            require(key in rule and rule[key] not in (None, "", []),
                    f"{rid}: missing {key}", failures)
        if isinstance(section, int):
            require(rid.startswith(f"ESRM-R{section}-"),
                    f"{rid}: ID/section mismatch", failures)

    required_rule_ids = {
        "ESRM-R23-003", "ESRM-R24-003", "ESRM-R25-005", "ESRM-R26-004",
        "ESRM-R28-003", "ESRM-R29-003", "ESRM-R30-003", "ESRM-R30-004",
        "ESRM-R31-004", "ESRM-R32-002", "ESRM-R33-003", "ESRM-R33-004",
        "ESRM-R34-003", "ESRM-R34-004", "ESRM-R35-002", "ESRM-R36-002",
        "ESRM-R37-003", "ESRM-R37-004", "ESRM-R37-005", "ESRM-R37-006",
        "ESRM-R38-003", "ESRM-R38-004", "ESRM-R39-003", "ESRM-R40-005"
    }
    missing_rule_ids = sorted(required_rule_ids.difference(ids))
    require(not missing_rule_ids,
            f"known source obligations missing from rule registry: {missing_rule_ids}", failures)

    by_rule_id = {r.get("id"): r for r in rules}
    r22 = by_rule_id.get("ESRM-R22-002", {}).get("concern", "")
    require("committed temporal/state predicates" not in r22,
            "Section 22 extraction still strengthens temporal/state predicates to committed predicates", failures)
    require("temporal/state predicates that hold" in r22,
            "Section 22 extraction does not preserve temporal/state predicate truth requirement", failures)

    r25 = by_rule_id.get("ESRM-R25-005", {}).get("concern", "")
    require("PROOFRAIL:SIGNATURE:V1" in r25 and "NUL" in r25 and "JCS(E_tau)" in r25,
            "Section 25 exact signature-input construction is not explicitly preserved", failures)

    r29 = by_rule_id.get("ESRM-R29-001", {}).get("concern", "")
    require("no whitespace" in r29,
            "Section 29 timestamp whitespace prohibition missing", failures)

    r35 = by_rule_id.get("ESRM-R35-002", {}).get("concern", "")
    require("transition_id" in r35,
            "Section 35 dispatch-intent transition_id missing", failures)

    r38 = by_rule_id.get("ESRM-R38-004", {}).get("concern", "")
    for token in ("valid durable crossing artifact D", "valid durable-idempotency evidence K",
                  "admissible authoritative effect-status evidence Q",
                  "admissible final non-occurrence evidence F"):
        require(token in r38,
                f"Section 38 recovery precondition missing: {token}", failures)

    domains = roles_doc.get("registered_domains", [])
    domain_names = [d.get("domain") for d in domains]
    require(len(domain_names) == 15,
            f"expected 15 registered domains, got {len(domain_names)}", failures)
    require(len(domain_names) == len(set(domain_names)),
            "duplicate registered domains", failures)

    required_settlement_roles = {
        "STATE", "DERIVATION", "AUTHORITY", "ADMISSION", "CONSUMPTION",
        "DISPATCH", "OBSERVATION", "RECONCILIATION", "SETTLEMENT"
    }
    actual_settlement_roles = set(roles_doc.get("settlement_required_distinguishable_roles", []))
    require(actual_settlement_roles == required_settlement_roles,
            "settlement distinguishable-role set mismatch", failures)

    epistemic = {r.get("role"): r.get("meaning", "") for r in roles_doc.get("epistemic_roles", [])}
    settled_meaning = epistemic.get("SETTLED", "")
    require("final protocol conclusion" not in settled_meaning.lower(),
            "SETTLED role still imports unsupported global-finality wording", failures)
    require("global-finality" in settled_meaning,
            "SETTLED role must explicitly disclaim stronger global-finality semantics", failures)

    families = corpus_doc.get("families", [])
    family_ids = [f.get("id") for f in families]
    require(len(family_ids) == len(set(family_ids)),
            "duplicate corpus family IDs", failures)

    corpus_sections = set()
    by_name = {}
    for family in families:
        fid = family.get("id", "<missing>")
        name = family.get("name")
        by_name[name] = family
        src = family.get("source_sections", [])
        corpus_sections.update(src)
        require(family.get("must_cover"), f"{fid}: empty must_cover", failures)
        require(family.get("classes"), f"{fid}: empty classes", failures)
        require(all(isinstance(s, int) and 22 <= s <= 40 for s in src),
                f"{fid}: invalid source section", failures)

    require(corpus_sections == expected_sections,
            f"corpus source coverage mismatch: got {sorted(corpus_sections)}", failures)

    required_family_tokens = {
        "raw-byte-framing": {"exactly-one-top-level-object", "reject-top-level-array-or-scalar"},
        "numeric-lexical-profile": {"special-quantities-use-profiled-strings"},
        "timestamp-profile": {"reject-timestamp-whitespace", "distinct-timestamp-roles", "temporal-validity-requires-committed-clock-policy"},
        "mandatory-header-and-extensions": {"preserve-array-order-unless-explicit-sorted-set", "all-extension-material-committed"},
        "domain-separated-commitment": {"domain-ascii-0x21-through-0x7e", "reject-nul-inside-domain", "domain-version-specific", "reject-dynamic-domain-construction"},
        "signature-envelope-and-base64url": {"signature-input-domain-prefix-nul-jcs-envelope"},
        "four-way-reconciliation": {"match", "diverged", "insufficient-window-open", "unresolved-window-closed", "reconciliation-is-adjudicated-not-empirical"},
        "closed-world-absence": {"coverage-evidence-retained", "coverage-evidence-committed"},
        "irreversible-consumption": {"reservation-cancel-before-consumption", "reject-reservation-cancel-after-consumption", "reject-reused-transition-id"},
        "crash-safe-dispatch-boundary": {"dispatch-lifecycle-distinct-states", "dispatch-intent-transition-id", "dispatch-intent-required-fields", "dispatch-crossing-required-fields", "crossing-recorded-immediately-before-dispatch"},
        "target-capability-evidence": {"capability-evidence-bound-to-transition-time", "reject-post-crash-reclassification", "queryable-negative-proves-noneffect-only-if-evidence-says-so", "observable-only-ambiguous-dispatch-forbids-auto-retry", "opaque-target-ambiguous-dispatch-forbids-auto-retry"},
        "recovery-function": {"valid-durable-crossing-artifact-input", "valid-durable-idempotency-evidence-input", "admissible-authoritative-effect-status-evidence", "admissible-final-nonoccurrence-evidence", "durable-idempotency-same-effect-retransmission", "otherwise-unresolved", "noneffect-never-restores-original-authority"},
        "transport-attempt-versus-semantic-effect": {"attempt-record-distinct-from-transition-observation-reconciliation-settlement"},
        "global-safety-properties": {"byte-level-boundary-order-preserved", "external-execution-boundary-order-preserved"}
    }

    for family_name, tokens in required_family_tokens.items():
        family = by_name.get(family_name)
        require(family is not None, f"missing corpus family {family_name}", failures)
        if family:
            cover = set(family.get("must_cover", []))
            missing = sorted(tokens.difference(cover))
            require(not missing,
                    f"{family_name}: missing required coverage {missing}", failures)

    vector_policy = corpus_doc.get("vector_policy", {})
    require(vector_policy.get("binary_vectors_present") is False,
            "Gate 1 must not claim Repair 4 binary vectors exist", failures)

    result_vocabulary = set(corpus_doc.get("result_vocabulary", []))
    require("RECONCILIATION_FAILED" not in result_vocabulary,
            "legacy RECONCILIATION_FAILED leaked into result vocabulary", failures)

    semantic_slots = []
    for family in families:
        semantic_slots.extend(family.get("must_cover", []))
    semantic_text = json.dumps(semantic_slots, sort_keys=True).upper()
    require("RECONCILIATION_FAILED" not in semantic_text,
            "legacy RECONCILIATION_FAILED leaked into expected corpus semantics", failures)
    require("EXACTLY_ONCE" not in semantic_text,
            "unbounded exactly-once token leaked into expected corpus semantics", failures)

    if failures:
        print("GATE1_STRUCTURE: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("GATE1_STRUCTURE: PASS")
    print(
        f"rules={len(rules)} sections={min(rule_sections)}-{max(rule_sections)} "
        f"corpus_families={len(families)} domains={len(domain_names)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
