#!/usr/bin/env python3
"""Cross-library COSE compatibility on a pinned, isolated legacy test stack.

This is a pycose 1.1.0 / cbor2 5.6.5 test of legacy -8 only. pycose
does not yet support RFC 9864's new Ed25519 -19 algorithm identifier.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pycose.keys.okp import OKPKey
from pycose.messages import Sign1Message

from proofrail.checkpoint import create_checkpoint
from proofrail.core import digest_ledger_entry
from proofrail.scitt_checkpoint import (
    COSE_ALG_ED25519,
    COSE_ALG_EDDSA_LEGACY,
    checkpoint_claim,
    sign_scitt_checkpoint_statement,
    verify_scitt_checkpoint_statement,
)


def main() -> int:
    with TemporaryDirectory() as directory:
        ledger = Path(directory) / "ledger.jsonl"
        entry = {
            "kind": "proofrail.fixture-ledger.v1",
            "sequence": 1,
            "previous_hash": "GENESIS",
            "action": "no-real-write",
        }
        entry["entry_hash"] = digest_ledger_entry(entry)
        ledger.write_text(json.dumps(entry, sort_keys=True) + "\n")
        issuer = Ed25519PrivateKey.generate()
        checkpoint_key = Ed25519PrivateKey.generate()
        signed_checkpoint = create_checkpoint(
            ledger, private_key=checkpoint_key, key_id="interop-checkpoint-key",
        )
        claim = checkpoint_claim(
            signed_checkpoint,
            authority_digest="a" * 64,
            consumption_digest="b" * 64,
            reconciliation_digest="c" * 64,
            previous_checkpoint_digest="GENESIS",
            sequence=1,
            domain="github:interop/fixture",
        )
        kwargs = {
            "issuer": "urn:proofrail:issuer:interop",
            "subject": "urn:proofrail:stream:interop",
            "key_id": b"interop-key",
        }
        legacy = sign_scitt_checkpoint_statement(
            claim, private_key=issuer,
            algorithm=COSE_ALG_EDDSA_LEGACY, **kwargs,
        )
        modern = sign_scitt_checkpoint_statement(
            claim, private_key=issuer, **kwargs,
        )
        assert cbor2.loads(modern).value[0] != cbor2.loads(legacy).value[0]
        assert cbor2.loads(cbor2.loads(modern).value[0])[1] == COSE_ALG_ED25519
        assert cbor2.loads(cbor2.loads(legacy).value[0])[1] == COSE_ALG_EDDSA_LEGACY

        public_raw = issuer.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )
        private_raw = issuer.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        key = OKPKey(crv="ED25519", x=public_raw, d=private_raw)

        # ProofRail => separately implemented pycose decoder + verifier.
        pycose_message = Sign1Message.decode(legacy)
        pycose_message.key = key
        assert pycose_message.verify_signature(), "pycose rejected ProofRail signature"

        # pycose => ProofRail verifier, including byte-for-byte issuer encoding.
        pycose_signed = pycose_message.encode(tag=True, sign=True)
        assert pycose_signed == legacy, "legacy COSE encodings unexpectedly differ"
        verified = verify_scitt_checkpoint_statement(
            pycose_signed,
            issuer_public_key=issuer.public_key(),
            expected_issuer=kwargs["issuer"],
            expected_subject=kwargs["subject"],
            expected_key_id=kwargs["key_id"],
            expected_claim=claim,
            checkpoint=signed_checkpoint,
            checkpoint_public_key=checkpoint_key.public_key(),
            ledger_path=str(ledger),
        )
        assert verified["valid"], verified
        assert verified["issuer_algorithm"] == COSE_ALG_EDDSA_LEGACY
        assert verified["transparency_receipt_verified"] is False

        # The new -19 default is locally verified, not pycose-supported yet.
        new_result = verify_scitt_checkpoint_statement(
            modern,
            issuer_public_key=issuer.public_key(),
            expected_issuer=kwargs["issuer"],
            expected_subject=kwargs["subject"],
            expected_key_id=kwargs["key_id"],
            expected_claim=claim,
            checkpoint=signed_checkpoint,
            checkpoint_public_key=checkpoint_key.public_key(),
            ledger_path=str(ledger),
            allow_legacy_eddsa=False,
        )
        assert new_result["valid"], new_result
        print("PASS: legacy -8 ProofRail <-> pycose; modern -19 ProofRail verifier")
        print("NOT TESTED: pycose -19, external SCITT receipts or registration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
