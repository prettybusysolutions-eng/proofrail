#!/usr/bin/env python3
"""Build a Rekor v2 hashedrekord request OFFLINE; never submit or sign data.

Inputs are a previously signed COSE_Sign1 statement, an Ed25519 signature
made OVER THOSE EXACT COSE BYTES (detached, not the COSE issuer signature),
and the signing key's DER SubjectPublicKeyInfo public-key bytes.

A request file is NOT a Rekor log receipt. This script cannot make network
requests, upload data, or perform a release; external publication requires
a separate consciously authorized operation and its own verified log proof.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from proofrail.core import ProofRailError

MAX_STATEMENT_BYTES = 1_000_000
MAX_PUBKEY_DER_BYTES = 2048


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def build_rekor_v2_request(
    statement_bytes: bytes,
    detached_signature: bytes,
    public_key_der: bytes,
) -> dict:
    """Encode the documented Rekor v2 hashedRekordRequestV002 shape.

    The public key is Ed25519 DER SPKI, not a raw 32-byte key. This produces
    no inclusion proof, signed checkpoint, timestamp, or authenticated latest.
    """
    if (type(statement_bytes) is not bytes
        or not 1 <= len(statement_bytes) <= MAX_STATEMENT_BYTES):
        raise ProofRailError("signed_statement_invalid_size")
    if type(detached_signature) is not bytes or len(detached_signature) != 64:
        raise ProofRailError("rekor_detached_signature_invalid_size")
    if (type(public_key_der) is not bytes
        or not 1 <= len(public_key_der) <= MAX_PUBKEY_DER_BYTES):
        raise ProofRailError("public_key_der_invalid_size")

    try:
        parsed = cbor2.loads(statement_bytes)
        if not isinstance(parsed, cbor2.CBORTag) or parsed.tag != 18:
            raise ProofRailError("artifact_not_tagged_cose_sign1")
        if not isinstance(parsed.value, (list, tuple)) or len(parsed.value) != 4:
            raise ProofRailError("artifact_cose_structure_invalid")
        protected, _, payload, cose_signature = parsed.value
        if not isinstance(protected, bytes) or not isinstance(payload, bytes):
            raise ProofRailError("artifact_cose_fields_invalid")
        if type(cose_signature) is not bytes or not cose_signature:
            raise ProofRailError("artifact_cose_signature_missing")
        pubkey = serialization.load_der_public_key(public_key_der)
        if not isinstance(pubkey, Ed25519PublicKey):
            raise ProofRailError("rekor_public_key_must_be_ed25519")
        if pubkey.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ) != public_key_der:
            raise ProofRailError("rekor_public_key_der_not_canonical")
        pubkey.verify(detached_signature, statement_bytes)
    except InvalidSignature as exc:
        raise ProofRailError("rekor_detached_signature_invalid") from exc
    except (ValueError, TypeError, cbor2.CBORDecodeError) as exc:
        raise ProofRailError("rekor_input_encoding_invalid") from exc

    return {
        "hashedRekordRequestV002": {
            "digest": _b64(hashlib.sha256(statement_bytes).digest()),
            "signature": {
                "content": _b64(detached_signature),
                "verifier": {
                    "publicKey": {"rawBytes": _b64(public_key_der)},
                    "keyDetails": "PKIX_ED25519",
                },
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--detached-signature", type=Path, required=True)
    parser.add_argument("--public-key-spki-der", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        statement = args.statement.read_bytes()
        signature = args.detached_signature.read_bytes()
        pubkey_der = args.public_key_spki_der.read_bytes()
        request = build_rekor_v2_request(statement, signature, pubkey_der)
        # Nothing is uploaded, networked, signed, or submitted.
        args.out_dir.mkdir(parents=True, exist_ok=False)
        request_path = args.out_dir / "rekor-v2-request.json"
        request_path.write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        metadata = {
            "kind": "proofrail.rekor-v2-dry-run.v0",
            "api_method": "POST",
            "api_path": "/api/v2/log/entries",
            "api_log_instance": "UNSELECTED_REQUIRES_TRUSTED_SIGSTORE_CONFIG",
            "submitted": False,
            "log_receipt_verified": False,
            "external_retention_verified": False,
            "artifact_sha256": hashlib.sha256(statement).hexdigest(),
            "record_kind": "hashedrekord",
            "record_version": "0.0.2",
            "public_payload_in_request": False,
            "warning": (
                "Public registration is permanent. Publishing this request "
                "reveals the signature and public key, and a digest that may "
                "correlate with public artifacts. A response is not verified "
                "without Rekor v2 inclusion and checkpoint verification."
            ),
        }
        (args.out_dir / "dry-run-metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "dry_run": True, "submitted": False,
            "request_path": str(request_path),
            "artifact_sha256": metadata["artifact_sha256"],
        }, sort_keys=True))
        return 0
    except (OSError, ProofRailError) as exc:
        print(json.dumps({
            "dry_run": True, "submitted": False,
            "error": str(exc),
        }), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
