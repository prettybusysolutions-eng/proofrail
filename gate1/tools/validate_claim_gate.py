#!/usr/bin/env python3
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = ROOT.parent
STATE = ROOT / "claim-gate-state.json"
POLICY = REPO / "governance" / "EPISTEMIC_CLAIM_GATE.md"

ORDER = [
    "DRAFT",
    "INTERNALLY_CHECKED",
    "READY_FOR_INDEPENDENT_REVIEW",
    "INDEPENDENTLY_REVIEWED",
    "READY_FOR_VECTOR_DESIGN",
    "IMPLEMENTATION_CONFORMANCE_CANDIDATE",
    "CONFORMANT",
]


def fail(msg, failures):
    failures.append(msg)


def main():
    failures = []

    if not POLICY.exists():
        fail("missing governance/EPISTEMIC_CLAIM_GATE.md", failures)
    if not STATE.exists():
        fail("missing gate1/claim-gate-state.json", failures)

    if failures:
        for item in failures:
            print(f"- {item}")
        return 1

    state = json.loads(STATE.read_text(encoding="utf-8"))
    claim = state.get("claim_state")
    if claim not in ORDER:
        fail(f"invalid claim_state: {claim}", failures)
        rank = -1
    else:
        rank = ORDER.index(claim)

    source_commit = state.get("authoritative_source_commit", "")
    target_commit = state.get("candidate_target_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        fail("authoritative_source_commit must be a full lowercase SHA-1", failures)
    if not re.fullmatch(r"[0-9a-f]{40}", target_commit):
        fail("candidate_target_commit must be a full lowercase SHA-1", failures)

    trace = state.get("bidirectional_traceability", {})
    trace_complete = trace.get("complete") is True
    unmapped = trace.get("unmapped_source_obligations") or []
    unsupported = trace.get("unsupported_or_overreaching_derived_rules") or []

    if trace_complete and (unmapped or unsupported):
        fail("traceability cannot be complete while unmatched sets are non-empty", failures)

    ready_review_rank = ORDER.index("READY_FOR_INDEPENDENT_REVIEW")
    if rank >= ready_review_rank and not trace_complete:
        fail("claim_state requires complete bidirectional traceability", failures)
    if rank >= ready_review_rank and (unmapped or unsupported):
        fail("claim_state requires empty bidirectional traceability defect sets", failures)

    review = state.get("independent_semantic_review", {})
    review_complete = review.get("complete") is True
    recommendation = review.get("recommendation")
    unresolved_blockers = review.get("unresolved_blockers")
    unresolved_majors = review.get("unresolved_major_defects")

    independently_reviewed_rank = ORDER.index("INDEPENDENTLY_REVIEWED")
    if rank >= independently_reviewed_rank and not review_complete:
        fail("claim_state implies independent review but independent_semantic_review.complete is false", failures)

    vector_rank = ORDER.index("READY_FOR_VECTOR_DESIGN")
    if rank >= vector_rank:
        if recommendation != "READY_FOR_VECTOR_DESIGN":
            fail("vector-design readiness requires explicit independent recommendation", failures)
        if unresolved_blockers != 0 or unresolved_majors != 0:
            fail("vector-design readiness requires zero unresolved BLOCKER and MAJOR defects", failures)

    vectors = state.get("vectors", {})
    vectors_authorized = vectors.get("authorized") is True
    if vectors_authorized:
        if not trace_complete or unmapped or unsupported:
            fail("vectors cannot be authorized before complete clean bidirectional traceability", failures)
        if not review_complete:
            fail("vectors cannot be authorized before independent semantic review", failures)
        if recommendation != "READY_FOR_VECTOR_DESIGN":
            fail("vectors cannot be authorized without READY_FOR_VECTOR_DESIGN recommendation", failures)
        if unresolved_blockers != 0 or unresolved_majors != 0:
            fail("vectors cannot be authorized with unresolved BLOCKER/MAJOR review defects", failures)

    verifiers = state.get("independent_verifiers", {})
    if verifiers.get("authorized") is True and not vectors_authorized:
        fail("independent verifiers cannot be authorized before vector design is authorized", failures)

    next_stage = state.get("next_stage")
    if not trace_complete and next_stage != "BIDIRECTIONAL_TRACEABILITY":
        fail("while traceability is incomplete, next_stage must remain BIDIRECTIONAL_TRACEABILITY", failures)
    if trace_complete and not review_complete and next_stage not in {"INDEPENDENT_SEMANTIC_REVIEW", "REPAIR_INTERNAL_DEFECTS"}:
        fail("after clean traceability and before independent review, next_stage must be INDEPENDENT_SEMANTIC_REVIEW or REPAIR_INTERNAL_DEFECTS", failures)

    prohibited = set(state.get("prohibited_current_claims", []))
    if not review_complete:
        required_prohibited = {
            "INDEPENDENTLY_VALIDATED",
            "READY_FOR_VECTOR_DESIGN",
            "CONFORMANT",
            "PRODUCTION_READY",
            "FORMALLY_PROVEN",
        }
        missing = sorted(required_prohibited - prohibited)
        if missing:
            fail(f"missing required prohibited claims before independent review: {missing}", failures)

    if failures:
        print("EPISTEMIC_CLAIM_GATE: FAIL")
        for item in failures:
            print(f"- {item}")
        return 1

    print("EPISTEMIC_CLAIM_GATE: PASS")
    print(f"claim_state={claim} next_stage={next_stage} traceability_complete={trace_complete} independent_review_complete={review_complete} vectors_authorized={vectors_authorized}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
