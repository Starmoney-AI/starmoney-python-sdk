"""HMAC-SHA256 signing and verification for UP3 Mandates.

Vendored from app/protocols/up3/signing.py. Byte-identical implementation.
Algorithm per SPEC.md §4 (HS256-JCS):

    canonical = JCS(envelope without 'signature')
    mac       = HMAC-SHA256(canonical, secret)
    value     = base64url(mac)  # no padding

JCS canonicalization uses the `rfc8785` PyPI package (MIT licensed).

IMPORTANT: This module MUST NOT import from app/ or starmoney_bank_service/.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

import rfc8785


def canonicalize(envelope_without_signature: dict[str, Any]) -> bytes:
    """JCS-canonicalize the envelope minus its signature.

    The input MUST NOT contain a 'signature' key — caller is responsible for
    removing it before calling. We don't strip silently here because doing so
    would mask bugs where callers pass the wrong dict shape.
    """
    if "signature" in envelope_without_signature:
        raise ValueError(
            "envelope_without_signature must NOT contain 'signature' key. "
            "Delete the key entirely before calling canonicalize() — JCS "
            "produces different bytes for null vs empty vs absent."
        )
    out = rfc8785.dumps(envelope_without_signature)
    return out if isinstance(out, bytes) else out.encode("utf-8")


def _b64url_no_padding(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign(
    envelope_without_signature: dict[str, Any],
    *,
    secret: bytes,
    key_id: str | None = None,
) -> dict[str, str]:
    """Compute the signature dict for an envelope.

    Args:
        envelope_without_signature: Mandate envelope dict with NO 'signature' key.
        secret: The HMAC secret. Must be bytes.
        key_id: Optional override. Defaults to envelope['issuer'].

    Returns:
        Signature dict: {'alg': 'HS256-JCS', 'key_id': ..., 'value': ...}.
    """
    if not isinstance(secret, (bytes, bytearray)):
        raise TypeError(f"secret must be bytes, got {type(secret).__name__}")
    canonical = canonicalize(envelope_without_signature)
    mac = hmac.new(bytes(secret), canonical, hashlib.sha256).digest()
    return {
        "alg": "HS256-JCS",
        "key_id": key_id or str(envelope_without_signature.get("issuer", "")),
        "value": _b64url_no_padding(mac),
    }


def verify(envelope: dict[str, Any], *, secret: bytes) -> bool:
    """Verify the signature on a fully-formed envelope.

    Returns True iff the envelope carries a valid HS256-JCS signature for the
    given secret. Returns False on any failure. Constant-time comparison.
    """
    sig = envelope.get("signature")
    if not isinstance(sig, dict):
        return False
    if sig.get("alg") != "HS256-JCS":
        return False
    expected = sig.get("value")
    if not isinstance(expected, str):
        return False

    envelope_minus_sig = {k: v for k, v in envelope.items() if k != "signature"}
    try:
        canonical = canonicalize(envelope_minus_sig)
    except (TypeError, ValueError):
        return False

    if not isinstance(secret, (bytes, bytearray)):
        return False
    mac = hmac.new(bytes(secret), canonical, hashlib.sha256).digest()
    actual = _b64url_no_padding(mac)

    return hmac.compare_digest(expected, actual)


__all__ = ["canonicalize", "sign", "verify"]
