"""Offline verifier for an experimental ProofRail multi-operator witness bundle.

Never downloads trust keys or infers trusted roots from the bundle itself.
Exit 0 = cryptographically valid under caller-supplied trust assumptions.
Exit 4 = invalid bundle. Exit 2 = malformed arguments or inputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from .anchor import decode_public_key
from .core import ProofRailError
from .trust_exchange import verify_witness_exchange


def _json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("statement", "receipts", "ledger", "checkpoint",
                   "checkpoint-public-key", "trusted-witnesses", "expected"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--minimum-operators", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        statement = _json(args.statement)
        receipts = _json(args.receipts)
        checkpoint = _json(args.checkpoint)
        expected = _json(args.expected)
        if not isinstance(receipts, list):
            raise ProofRailError("receipts must be a list")
        for name, instance in (("statement", statement),):
            schema = json.loads(files("schemas").joinpath(
                "cross_domain_witness_statement.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(instance)
        receipt_schema = json.loads(files("schemas").joinpath(
            "cross_domain_witness_receipt.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(receipt_schema)
        for receipt in receipts:
            validator.validate(receipt)

        raw_witnesses = _json(args.trusted_witnesses)
        if not isinstance(raw_witnesses, dict):
            raise ProofRailError("trusted-witnesses must be a JSON object")
        witnesses = {}
        for signer_id, spec in raw_witnesses.items():
            if not isinstance(spec, dict):
                raise ProofRailError("witness roster entry must be an object")
            witnesses[signer_id] = {
                "operator_id": spec["operator_id"],
                "key_id": spec["key_id"],
                "public_key": decode_public_key(spec["public_key"]),
            }
        checkpoint_pub = decode_public_key(
            Path(args.checkpoint_public_key).read_text(encoding="utf-8").strip()
        )
        result = verify_witness_exchange(
            statement, receipts, ledger_path=args.ledger,
            signed_checkpoint=checkpoint, checkpoint_public_key=checkpoint_pub,
            trusted_witnesses=witnesses, expected=expected,
            minimum_distinct_operators=args.minimum_operators,
        )
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["valid"] else 4
    except (OSError, ValueError, KeyError, TypeError, ProofRailError,
            json.JSONDecodeError, Exception) as exc:
        # Include validation exceptions (jsonschema.ValidationError) without
        # dumping sensitive bundle material or writing back to any input file.
        print(json.dumps({"valid": False, "error": type(exc).__name__}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
