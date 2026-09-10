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

    domains = roles_doc.get("registered_domains", [])
    domain_names = [d.get("domain") for d in domains]
    require(len(domain_names) == 15, f"expected 15 registered domains, got {len(domain_names)}", failures)
    require(len(domain_names) == len(set(domain_names)), "duplicate registered domains", failures)

    required_settlement_roles = {
        "STATE", "DERIVATION", "AUTHORITY", "ADMISSION", "CONSUMPTION",
        "DISPATCH", "OBSERVATION", "RECONCILIATION", "SETTLEMENT"
    }
    actual_settlement_roles = set(roles_doc.get("settlement_required_distinguishable_roles", []))
    require(actual_settlement_roles == required_settlement_roles,
            "settlement distinguishable-role set mismatch", failures)

    families = corpus_doc.get("families", [])
    family_ids = [f.get("id") for f in families]
    require(len(family_ids) == len(set(family_ids)), "duplicate corpus family IDs", failures)
    corpus_sections = set()
    for family in families:
        fid = family.get("id", "<missing>")
        src = family.get("source_sections", [])
        corpus_sections.update(src)
        require(family.get("must_cover"), f"{fid}: empty must_cover", failures)
        require(family.get("classes"), f"{fid}: empty classes", failures)
        require(all(isinstance(s, int) and 22 <= s <= 40 for s in src),
                f"{fid}: invalid source section", failures)

    require(corpus_sections == expected_sections,
            f"corpus source coverage mismatch: got {sorted(corpus_sections)}", failures)

    four_way = next((f for f in families if f.get("name") == "four-way-reconciliation"), None)
    require(four_way is not None, "missing four-way-reconciliation family", failures)
    if four_way:
        cover = set(four_way.get("must_cover", []))
        require({"match", "diverged", "insufficient-window-open", "unresolved-window-closed"}.issubset(cover),
                "four-way reconciliation coverage incomplete", failures)

    recovery = next((f for f in families if f.get("name") == "recovery-function"), None)
    require(recovery is not None, "missing recovery-function family", failures)
    if recovery:
        cover = set(recovery.get("must_cover", []))
        require("durable-idempotency-same-effect-retransmission" in cover,
                "recovery missing durable-idempotency retransmission branch", failures)
        require("otherwise-unresolved" in cover,
                "recovery missing unresolved fallback", failures)

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
    print(f"rules={len(rules)} sections={min(rule_sections)}-{max(rule_sections)} corpus_families={len(families)} domains={len(domain_names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
