"""StarMoney SDK — UP3Resource.

Exposes UP3 mandate-building and verification as a resource on StarmoneyClient.
The signing primitives are vendored from app/protocols/up3/signing.py (identical
byte output, same HMAC-SHA256 / JCS algorithm).

UP3 v0.1 is SERVICE ATTESTATION — not user attestation. The HMAC signature
proves "this Mandate was produced by a process holding the registered signing
key for `issuer`". User consent lives at the bank's OTP step; both gates must
hold, but they are independent.

Guardrail: `consent_evidence` defaults to `{"type": "service_attestation",
"data": {}}`. The `consent_token_v1` user-evidence type is NOT shipped in v0.1
— attempting to pass it is caller error, not an SDK validation.

Secret loading: the UP3 HMAC secret is the same per-service secret as the JWT
secret in v0.1 (UP3 spec §10 FAQ). Pass `up3_secret` to `StarmoneyClient`; if
omitted, it defaults to `jwt_secret.encode()`.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .vendor.errors import UP3SignatureInvalid
from .vendor.signing import sign, verify

# ULID alphabet (Crockford base32, uppercase)
_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _generate_ulid() -> str:
    """Generate a ULID-like 26-character Crockford base32 string.

    Millisecond-resolution timestamp in the top 10 chars + 16 random chars.
    Not a strict ULID library dependency — keeps the SDK dep-free for this.
    """
    import os
    import struct

    ts_ms = int(time.time() * 1000)
    # Encode 48-bit timestamp into 10 chars
    ts_chars = ""
    t = ts_ms
    for _ in range(10):
        ts_chars = _ULID_ALPHABET[t & 0x1F] + ts_chars
        t >>= 5

    # 16 random chars
    rand_bytes = os.urandom(10)
    rand_int = int.from_bytes(rand_bytes, "big")
    rand_chars = ""
    for _ in range(16):
        rand_chars = _ULID_ALPHABET[rand_int & 0x1F] + rand_chars
        rand_int >>= 5

    return ts_chars + rand_chars


def _mandate_id() -> str:
    """Generate a mandate id matching ^mnd_[A-Z0-9]{26}$."""
    return f"mnd_{_generate_ulid()}"


def _now_z() -> str:
    """Current UTC time in RFC 3339 with mandatory Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _future_z(minutes: int) -> str:
    """UTC time N minutes from now with mandatory Z suffix."""
    dt = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class UP3Resource:
    """UP3 Mandate building + verification resource.

    Accessed as `client.up3`. Requires `up3_secret` to be set on the client.

    Methods:
        build_intent(...)   — Build and sign an IntentMandate dict.
        build_cart(...)     — Build and sign a CartMandate dict.
        verify_payment_mandate(envelope) -> bool — Verify a PaymentMandate.
    """

    def __init__(self, secret: bytes, issuer: str) -> None:
        """
        Args:
            secret: HMAC secret bytes for signing. In v0.1 this is the same
                    secret used for JWT (see UP3 spec §10 FAQ).
            issuer: Issuer identifier registered with StarMoney. Typically
                    the same value as the JWT issuer / service name.
        """
        if not isinstance(secret, (bytes, bytearray)):
            raise TypeError("UP3Resource secret must be bytes")
        self._secret = bytes(secret)
        self._issuer = issuer

    # ------------------------------------------------------------------
    # Public mandate builders
    # ------------------------------------------------------------------

    def build_intent(
        self,
        user_ref: str,
        description: str,
        max_amount_minor: int,
        currency: str = "XOF",
        beneficiary_hint: Optional[str] = None,
        rail_hint: Optional[str] = None,
        ttl_minutes: int = 15,
    ) -> dict[str, Any]:
        """Build and sign an IntentMandate envelope.

        The intent captures the user's payment wish ("send N XOF to Fatou").
        TTL is capped at 60 minutes per SPEC §3.1.

        Args:
            user_ref: Stable user identifier, opaque to StarMoney
                      (e.g. 'whatsapp:+221771234567').
            description: Human-readable echo of user wish (max 500 chars).
            max_amount_minor: Amount ceiling. Cart cannot exceed this.
            currency: ISO 4217. v0.1 only accepts 'XOF'.
            beneficiary_hint: Free-text hint, may be unresolved at intent time.
            rail_hint: Optional rail hint (usually null at intent time).
            ttl_minutes: Mandate lifetime in minutes (default 15, max 60).

        Returns:
            Signed IntentMandate envelope dict ready to pass to build_cart or
            POST /v1/payments as intent_mandate.
        """
        ttl = min(ttl_minutes, 60)
        mandate_id = _mandate_id()
        now = _now_z()
        expires = _future_z(ttl)

        envelope: dict[str, Any] = {
            "version": "0.1",
            "type": "intent",
            "id": mandate_id,
            "issued_at": now,
            "expires_at": expires,
            "issuer": self._issuer,
            "payload": {
                "user_ref": user_ref,
                "description": description,
                "max_amount_minor": max_amount_minor,
                "currency": currency,
                "beneficiary_hint": beneficiary_hint,
                "rail_hint": rail_hint,
            },
        }
        envelope["signature"] = sign(envelope, secret=self._secret)
        return envelope

    def build_cart(
        self,
        intent_mandate: dict[str, Any],
        *,
        amount_minor: int,
        beneficiary_iban: str,
        beneficiary_name: str,
        rail: Optional[str] = None,
        fees_minor: Optional[dict[str, int]] = None,
        confirmed_at: Optional[str] = None,
        consent_evidence: Optional[dict[str, Any]] = None,
        ttl_minutes: int = 2,
    ) -> dict[str, Any]:
        """Build and sign a CartMandate envelope.

        The cart captures the user's confirmation ("yes, send 5000 to Fatou Ndiaye
        at SN12K..."). Must reference the IntentMandate by id.

        v0.1 guardrail: consent_evidence defaults to service_attestation. Do NOT
        pass consent_token_v1 until v0.2 — the server rejects it with
        UP3_TYPE_NOT_ACCEPTED.

        Args:
            intent_mandate: The signed IntentMandate dict from build_intent().
            amount_minor: Exact amount (not ceiling). Must be <= intent.max_amount_minor.
            beneficiary_iban: Resolved recipient IBAN.
            beneficiary_name: Display name for receipts.
            rail: DEPRECATED / optional (ADR-001). Rail is orchestrator-owned and
                  selected server-side; omit it. When None it is left out of the
                  cart payload. Retained only for back-compat.
            fees_minor: Legged fee accounting dict (e.g. {"orchestrator": 50}).
                        Defaults to empty dict.
            confirmed_at: RFC 3339 Z-suffix timestamp of the user's tap.
                          Defaults to now.
            consent_evidence: user_consent_evidence dict. Defaults to
                              {"type": "service_attestation", "data": {}}.
            ttl_minutes: CartMandate lifetime in minutes (default 2).

        Returns:
            Signed CartMandate envelope dict ready to POST as cart_mandate.
        """
        if fees_minor is None:
            fees_minor = {}
        if confirmed_at is None:
            confirmed_at = _now_z()
        if consent_evidence is None:
            consent_evidence = {"type": "service_attestation", "data": {}}

        intent_id = intent_mandate["id"]
        intent_payload = intent_mandate["payload"]

        mandate_id = _mandate_id()
        now = _now_z()
        expires = _future_z(ttl_minutes)

        payload: dict[str, Any] = {
            "intent_mandate_id": intent_id,
            "user_ref": intent_payload["user_ref"],
            "amount_minor": amount_minor,
            "currency": intent_payload["currency"],
            "beneficiary_iban": beneficiary_iban,
            "beneficiary_name": beneficiary_name,
            "fees_minor": fees_minor,
            "confirmed_at": confirmed_at,
            "user_consent_evidence": consent_evidence,
        }
        # ADR-001: rail is orchestrator-owned. Only include it when the caller
        # supplies a hint; StarMoney selects and stamps the executed rail.
        if rail is not None:
            payload["rail"] = rail
        envelope: dict[str, Any] = {
            "version": "0.1",
            "type": "cart",
            "id": mandate_id,
            "issued_at": now,
            "expires_at": expires,
            "issuer": self._issuer,
            "payload": payload,
        }
        envelope["signature"] = sign(envelope, secret=self._secret)
        return envelope

    def verify_payment_mandate(self, envelope: dict[str, Any]) -> bool:
        """Verify the StarMoney signature on a PaymentMandate envelope.

        Uses the same secret (v0.1 per-service shared key) to verify.
        Returns True on a valid signature, False otherwise.

        The SDK does NOT raise on invalid signature by default — callers decide
        how to surface UP3_SIG_INVALID (log for audit, surface to user, etc.).

        Args:
            envelope: The full PaymentMandate dict including 'signature'.

        Returns:
            True if signature is valid, False otherwise.
        """
        return verify(envelope, secret=self._secret)

    def verify_payment_mandate_strict(self, envelope: dict[str, Any]) -> bool:
        """Like verify_payment_mandate but raises UP3SignatureInvalid on failure.

        Args:
            envelope: The full PaymentMandate dict.

        Returns:
            True on success.

        Raises:
            UP3SignatureInvalid: Signature did not verify.
        """
        result = verify(envelope, secret=self._secret)
        if not result:
            issuer = envelope.get("issuer", "unknown")
            raise UP3SignatureInvalid(
                f"PaymentMandate signature did not verify for issuer={issuer!r}"
            )
        return True
