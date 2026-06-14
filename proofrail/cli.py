from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .core import (
    Ledger,
    ProofRailError,
    approve_action,
    atomic_write_json,
    evaluate_action,
    sign_document,
)
from .checkpoint import (
    create_checkpoint,
    export_ledger,
    verify_checkpoint,
    verify_ledger,
)
from .anchor import (
    create_anchor,
    encode_public_key,
    resolve_file_anchor_public_key,
    verify_anchor,
)
from .crypto import hash_record


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.handler(args)
    except (ProofRailError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proofrail")
    commands = parser.add_subparsers(required=True)

    sign = commands.add_parser("sign-claim")
    sign.add_argument("--input", required=True)
    sign.add_argument("--output", required=True)
    sign.add_argument("--key-id", required=True)
    sign.add_argument("--secret-env", default="PROOFRAIL_EVIDENCE_SECRET")
    sign.set_defaults(handler=handle_sign)

    approve = commands.add_parser("approve")
    approve.add_argument("--action", required=True)
    approve.add_argument("--output", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--scope", required=True)
    approve.add_argument("--expires-at", required=True)
    approve.add_argument("--key-id", required=True)
    approve.add_argument("--secret-env", default="PROOFRAIL_APPROVAL_SECRET")
    approve.set_defaults(handler=handle_approve)

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--action", required=True)
    evaluate.add_argument("--evidence", required=True, nargs="+")
    evaluate.add_argument("--policy", required=True)
    evaluate.add_argument("--approval")
    evaluate.add_argument("--output")
    evaluate.add_argument("--decision-key-id", default="proofrail-gate")
    evaluate.add_argument("--evidence-secret-env", default="PROOFRAIL_EVIDENCE_SECRET")
    evaluate.add_argument("--approval-secret-env", default="PROOFRAIL_APPROVAL_SECRET")
    evaluate.add_argument("--decision-secret-env", default="PROOFRAIL_DECISION_SECRET")
    evaluate.set_defaults(handler=handle_evaluate)

    record = commands.add_parser("record")
    record.add_argument("--action", required=True)
    record.add_argument("--decision", required=True)
    record.add_argument("--ledger", required=True)
    record.add_argument("--outcome", required=True)
    record.add_argument("--actor", required=True)
    record.add_argument("--decision-secret-env", default="PROOFRAIL_DECISION_SECRET")
    record.set_defaults(handler=handle_record)

    verify = commands.add_parser("verify-ledger")
    verify.add_argument("--ledger", required=True)
    verify.set_defaults(handler=handle_verify)

    ledger = commands.add_parser("ledger")
    ledger_commands = ledger.add_subparsers(required=True)
    ledger_export = ledger_commands.add_parser("export")
    ledger_export.add_argument("--ledger", default="ledger/events.jsonl")
    ledger_export.add_argument("--out", required=True)
    ledger_export.set_defaults(handler=handle_ledger_export)
    ledger_verify = ledger_commands.add_parser("verify")
    ledger_verify.add_argument("ledger")
    ledger_verify.set_defaults(handler=handle_ledger_verify)

    checkpoint = commands.add_parser("checkpoint")
    checkpoint_commands = checkpoint.add_subparsers(required=True)
    checkpoint_create = checkpoint_commands.add_parser("create")
    checkpoint_create.add_argument("--ledger", default="proofrail-ledger.jsonl")
    checkpoint_create.add_argument("--out", default="proofrail-checkpoint.json")
    checkpoint_create.add_argument("--key-id", default="proofrail-checkpoint")
    checkpoint_create.add_argument(
        "--private-key-env",
        default="PROOFRAIL_CHECKPOINT_PRIVATE_KEY",
    )
    checkpoint_create.set_defaults(handler=handle_checkpoint_create)
    checkpoint_verify = checkpoint_commands.add_parser("verify")
    checkpoint_verify.add_argument(
        "checkpoint",
        nargs="?",
        default="proofrail-checkpoint.json",
    )
    checkpoint_verify.add_argument("--ledger", default="proofrail-ledger.jsonl")
    checkpoint_verify.add_argument(
        "--public-key-env",
        default="PROOFRAIL_CHECKPOINT_PUBLIC_KEY",
    )
    checkpoint_verify.set_defaults(handler=handle_checkpoint_verify)

    anchor = commands.add_parser("anchor")
    anchor_commands = anchor.add_subparsers(required=True)
    anchor_create = anchor_commands.add_parser("create")
    anchor_create.add_argument("--ledger", required=True)
    anchor_create.add_argument("--out", required=True)
    anchor_create.add_argument("--trust-checkpoint")
    anchor_create.add_argument("--key-id", default="proofrail-anchor")
    anchor_create.add_argument("--private-key-env", default="PROOFRAIL_ANCHOR_PRIVATE_KEY")
    anchor_create.add_argument("--public-key-out")
    anchor_create.set_defaults(handler=handle_anchor_create)
    anchor_verify = anchor_commands.add_parser("verify")
    anchor_verify.add_argument("--ledger", required=True)
    anchor_verify.add_argument("--anchor", required=True)
    anchor_verify.add_argument("--trust-checkpoint")
    anchor_verify.set_defaults(handler=handle_anchor_verify)

    reproduce = commands.add_parser("reproduce")
    reproduce.add_argument("artifact")
    reproduce.set_defaults(handler=handle_reproduce)

    demo = commands.add_parser("demo")
    demo_commands = demo.add_subparsers(required=True)
    github_demo = demo_commands.add_parser("github-merge-authority")
    github_demo.add_argument("--out-dir", default="proofrail-demo")
    github_demo.set_defaults(handler=handle_github_demo)
    return parser


def handle_sign(args: argparse.Namespace) -> int:
    document = read_json(args.input)
    signed = sign_document(document, read_secret(args.secret_env), args.key_id)
    atomic_write_json(args.output, signed)
    print(json.dumps({"ok": True, "claim_id": signed.get("claim_id"), "output": args.output}))
    return 0


def handle_approve(args: argparse.Namespace) -> int:
    action = read_json(args.action)
    approval = approve_action(
        action,
        approved_by=args.approved_by,
        scope=args.scope,
        expires_at=args.expires_at,
        secret=read_secret(args.secret_env),
        key_id=args.key_id,
    )
    atomic_write_json(args.output, approval)
    print(json.dumps({"ok": True, "action_digest": approval["action_digest"], "output": args.output}))
    return 0


def handle_evaluate(args: argparse.Namespace) -> int:
    action = read_json(args.action)
    evidence = [read_json(path) for path in args.evidence]
    approval = read_json(args.approval) if args.approval else None
    decision = evaluate_action(
        action,
        evidence,
        read_json(args.policy),
        evidence_secret=read_secret(args.evidence_secret_env),
        approval=approval,
        approval_secret=read_secret(args.approval_secret_env) if approval else None,
    )
    signed = sign_document(
        {"kind": "proofrail.decision.v1", **decision.as_dict()},
        read_secret(args.decision_secret_env),
        args.decision_key_id,
    )
    if args.output:
        atomic_write_json(args.output, signed)
    print(json.dumps(signed, indent=2, sort_keys=True))
    return 0 if decision.allowed else 3


def handle_record(args: argparse.Namespace) -> int:
    action = read_json(args.action)
    decision_data = read_json(args.decision)
    from .core import GateDecision, verify_document

    if not verify_document(decision_data, read_secret(args.decision_secret_env)):
        raise ProofRailError("Decision signature is invalid")
    decision = GateDecision(
        decision=decision_data["decision"],
        action_digest=decision_data["action_digest"],
        reasons=tuple(decision_data.get("reasons", [])),
        evidence_ids=tuple(decision_data.get("evidence_ids", [])),
        approval_required=bool(decision_data.get("approval_required")),
    )
    receipt = Ledger(args.ledger).append(
        action=action,
        decision=decision,
        outcome=args.outcome,
        actor=args.actor,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def handle_verify(args: argparse.Namespace) -> int:
    result = Ledger(args.ledger).verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 4


def handle_ledger_export(args: argparse.Namespace) -> int:
    result = export_ledger(args.ledger, args.out)
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0


def handle_ledger_verify(args: argparse.Namespace) -> int:
    result = verify_ledger(args.ledger)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 4


def handle_checkpoint_create(args: argparse.Namespace) -> int:
    checkpoint = create_checkpoint(
        args.ledger,
        private_key=Ed25519PrivateKey.from_private_bytes(
            read_encoded_key(args.private_key_env)
        ),
        key_id=args.key_id,
    )
    atomic_write_json(args.out, checkpoint)
    print(
        json.dumps(
            {
                "ok": True,
                "checkpoint": args.out,
                "checkpoint_id": checkpoint["checkpoint_id"],
                "merkle_root": checkpoint["ledger"]["merkle_root"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def handle_checkpoint_verify(args: argparse.Namespace) -> int:
    checkpoint = read_json(args.checkpoint)
    result = verify_checkpoint(
        checkpoint,
        args.ledger,
        public_key=Ed25519PublicKey.from_public_bytes(
            read_encoded_key(args.public_key_env)
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 4


def handle_anchor_create(args: argparse.Namespace) -> int:
    configured = os.getenv(args.private_key_env)
    private_key = (
        Ed25519PrivateKey.from_private_bytes(read_encoded_key(args.private_key_env))
        if configured
        else Ed25519PrivateKey.generate()
    )
    public_key_out = Path(args.public_key_out or f"{args.out}.pub")
    public_key_out.parent.mkdir(parents=True, exist_ok=True)
    public_key_out.write_text(encode_public_key(private_key.public_key()) + "\n", encoding="utf-8")
    reference = os.path.relpath(public_key_out.resolve(), Path(args.out).resolve().parent)
    if ".." in Path(reference).parts:
        raise ProofRailError("Anchor public key must be stored beside or below the anchor")
    trust_checkpoint_hash = (
        _verified_record_hash(read_json(args.trust_checkpoint))
        if args.trust_checkpoint
        else hash_record({"kind": "proofrail.no-trust-checkpoint.v0.5.2"})
    )
    anchor = create_anchor(
        args.ledger,
        trust_checkpoint_hash=trust_checkpoint_hash,
        private_key=private_key,
        key_id=args.key_id,
        anchor_provider="local-file",
        anchor_reference=f"file:{reference}",
        trust_checkpoint_present=bool(args.trust_checkpoint),
    )
    atomic_write_json(args.out, anchor)
    print(
        json.dumps(
            {
                "ok": True,
                "anchor": args.out,
                "public_key": str(public_key_out),
                "ledger_merkle_root": anchor["ledger_merkle_root"],
                "trust_checkpoint_hash": anchor["trust_checkpoint_hash"],
                "trust_checkpoint_present": anchor["trust_checkpoint_present"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def handle_anchor_verify(args: argparse.Namespace) -> int:
    anchor = read_json(args.anchor)
    expected_trust_checkpoint_hash = (
        _verified_record_hash(read_json(args.trust_checkpoint))
        if args.trust_checkpoint
        else None
    )
    result = verify_anchor(
        anchor,
        args.ledger,
        public_key=resolve_file_anchor_public_key(anchor, anchor_path=args.anchor),
        expected_trust_checkpoint_hash=expected_trust_checkpoint_hash,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 4


def handle_reproduce(args: argparse.Namespace) -> int:
    from .reproduce import reproduce_artifact

    result = reproduce_artifact(args.artifact)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 4


def handle_github_demo(args: argparse.Namespace) -> int:
    from .demo import run_github_merge_authority_demo

    result = run_github_merge_authority_demo(Path(args.out_dir))
    print(result["transcript"])
    return 0 if result["valid"] else 4


def read_json(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProofRailError(f"Expected JSON object: {path}")
    return data


def read_secret(name: str) -> bytes:
    value = os.getenv(name)
    if not value:
        raise ProofRailError(f"Missing secret environment variable: {name}")
    return value.encode("utf-8")


def read_encoded_key(name: str) -> bytes:
    value = os.getenv(name)
    if not value:
        raise ProofRailError(f"Missing key environment variable: {name}")
    compact = value.strip()
    try:
        if len(compact) == 64:
            decoded = bytes.fromhex(compact)
        else:
            decoded = base64.urlsafe_b64decode(compact + "=" * (-len(compact) % 4))
    except (ValueError, TypeError) as exc:
        raise ProofRailError(f"Invalid encoded Ed25519 key in {name}") from exc
    if len(decoded) != 32:
        raise ProofRailError(f"Ed25519 key in {name} must decode to 32 bytes")
    return decoded


def _verified_record_hash(record: dict[str, Any]) -> str:
    recorded = record.get("record_hash")
    if not isinstance(recorded, str) or recorded != hash_record(record):
        raise ProofRailError("Trust checkpoint record hash is invalid")
    return recorded


if __name__ == "__main__":
    raise SystemExit(main())
