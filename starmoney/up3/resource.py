"""StarMoney SDK — UP3Resource.

Exposes UP3 mandate-building and verification as a resource on StarmoneyClient.
The signing primitives are vendored from app/protocols/up3/signing.py (identical
byte output, same HMAC-SHA256 / JCS algorithm).

The HMAC signature proves "this Mandate was produced by a process holding the
registered signing key for `issuer`" — the service's word. Since 0.3.44 (P19,
owner ruling 13 Nov 2026) the bank also requires, on every send, at least one
CUSTOMER-PRESENT proof it accepts inside the cart: `consent_evidence` is a
required argument of every cart builder here and `service_attestation` alone is
refused by the bank (422 `UP3_TYPE_NOT_ACCEPTED`). The only accepted type today
is `chat_session_pin_v1` — `{"type": "chat_session_pin_v1", "data":
{"verified_at", "attempt_count", "session_id_hash"}}`, the chat code the user
just typed (B-104: one code confirms exactly one send, so mint a fresh block per
cart). A new evidence type needs the owner's approval and a bank release; the
SDK does not pre-validate the type beyond refusing `service_attestation`.
The bank's rail-time authentication (via Dabsi) is unchanged and independent.

Secret loading: the UP3 HMAC secret is the same per-service secret as the JWT
secret in v0.1 (UP3 spec §10 FAQ). Pass `up3_secret` to `StarmoneyClient`; if
omitted, it defaults to `jwt_secret.encode()`.
"""

from __future__ import annotations

import base64
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .vendor.errors import UP3SignatureInvalid
from .vendor.signing import sign, verify

# ULID alphabet (Crockford base32, uppercase)
_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: The customer-present evidence type the bank accepts today (P19, 0.3.44).
CHAT_SESSION_PIN_V1 = "chat_session_pin_v1"


def _require_consent_evidence(consent_evidence: Any) -> dict[str, Any]:
    """P19: every cart carries a customer-present proof; refuse locally what the
    bank would refuse anyway (nothing is signed, nothing is posted)."""
    if not isinstance(consent_evidence, dict) or "type" not in consent_evidence:
        raise ValueError(
            "consent_evidence is required (P19, 0.3.44): every send carries the user's own "
            'proof, e.g. {"type": "chat_session_pin_v1", "data": {"verified_at": "<RFC 3339 Z>", '
            '"attempt_count": 1, "session_id_hash": "sha256:<base64url>"}} — the chat code the '
            "user just typed, one fresh block per cart (B-104)"
        )
    if consent_evidence.get("type") == "service_attestation":
        raise ValueError(
            "service_attestation is the service's own word and is no longer accepted as the "
            "cart's consent evidence (bank 422 UP3_TYPE_NOT_ACCEPTED since 0.3.44): pass the "
            "customer-present proof, chat_session_pin_v1 today"
        )
    if not isinstance(consent_evidence.get("data"), dict):
        raise ValueError("consent_evidence.data must be an object")
    return consent_evidence


def _generate_ulid() -> str:
    """Generate a ULID-like 26-character Crockford base32 string.

    Millisecond-resolution timestamp in the top 10 chars + 16 random chars.
    Not a strict ULID library dependency — keeps the SDK dep-free for this.
    """
    import os

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


def _derive_cart_id(issuer: str, seed: str) -> str:
    """Derive a caller-stable CartMandate id from an idempotency seed.

    A retry (timeout, no response, connection reset) that calls build_cart
    again with the SAME seed must regenerate the IDENTICAL cart.id, so the
    bank recognizes it as the same payment and answers with the stored outcome
    instead of executing a new one. This is a normative part of the v0.1 retry
    contract, not an implementation detail — other UP3 SDKs (TS, Java, ...)
    MUST reproduce this exact derivation byte-for-byte, or a retry through a
    different SDK would mint a different anchor and defeat the guarantee.

    Derivation (fixed, do not change without a protocol version bump):
        cart.id = "mnd_" + base32(sha256(b"up3.cart.id.v1|" + issuer + "|" + seed))[:26]

    RFC 4648 base32 (alphabet A-Z2-7, no padding) is a subset of
    [A-Z0-9], so the result satisfies ^mnd_[A-Z0-9]{26}$ by construction.
    `issuer` is included in the preimage for domain separation between
    issuers using the same seed value.

    Args:
        issuer: The signing issuer (domain-separates the derivation).
        seed: Caller-supplied idempotency seed (e.g. a consent_jti). Must be
              a non-empty, non-whitespace string.

    Raises:
        ValueError: seed is empty or whitespace-only.
    """
    if not seed or not seed.strip():
        raise ValueError("idempotency_seed must be a non-empty string")
    preimage = f"up3.cart.id.v1|{issuer}|{seed}".encode("utf-8")
    digest = hashlib.sha256(preimage).digest()
    b32 = base64.b32encode(digest).decode("ascii").rstrip("=")
    return f"mnd_{b32[:26].upper()}"


# The closed set of ``payload.execution_mode`` values (UP3 0.2-draft, B-40).
_EXECUTION_MODES = ("immediate", "deferred_held", "deferred_best_effort")


def _check_execution_mode(execution_mode: Optional[str]) -> None:
    if execution_mode is not None and execution_mode not in _EXECUTION_MODES:
        raise ValueError(f"execution_mode must be one of {_EXECUTION_MODES}, got {execution_mode!r}")


# "argument not passed" sentinel for build_cart_v02.beneficiary_name, whose
# meaningful default (the quote's display_name) may itself be None.
_UNSET: Any = object()


def _to_z(value: str) -> str:
    """Normalise an RFC 3339 timestamp to the envelope's second-precision UTC Z
    form (the bank returns ``expires_at`` with microseconds and ``+00:00``)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        build_cart(...)     — Build and sign a 0.1 CartMandate dict (IBAN by value).
        build_cart_v02(...) — Build and sign a 0.2 CartMandate that signs a quote
                              from ``client.payments.quote(...)`` (transfer routes).
        build_deferred_cart_v02(...) — Build and sign a 0.2 CartMandate that consents
                              to a deferred transfer (the hold from a
                              ``RECIPIENT_HAS_NO_ACCOUNT`` refusal's deferred_quote).
        cart_id_for(seed)   — The cart.id a seed derives to (retry / status lookup).
        verify_payment_mandate(envelope, orchestrator_secret=...) -> bool —
            Verify a PaymentMandate with the ORCHESTRATOR's key (not the
            client's own secret; see the method's note).
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
        consent_evidence: dict[str, Any],
        rail: Optional[str] = None,
        fees_minor: Optional[dict[str, int]] = None,
        confirmed_at: Optional[str] = None,
        ttl_minutes: int = 2,
        idempotency_seed: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build and sign a CartMandate envelope.

        The cart captures the user's confirmation ("yes, send 5000 to Fatou Ndiaye
        at SN12K..."). Must reference the IntentMandate by id.

        P19 (0.3.44): ``consent_evidence`` is required and must be a
        customer-present proof the bank accepts — ``chat_session_pin_v1`` today.
        ``service_attestation`` is refused here (ValueError) as the bank would
        (422 ``UP3_TYPE_NOT_ACCEPTED``).

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
            consent_evidence: user_consent_evidence dict, REQUIRED:
                {"type": "chat_session_pin_v1", "data": {"verified_at":
                "<RFC 3339 Z>", "attempt_count": 1, "session_id_hash":
                "sha256:<base64url>"}} — the code the user just typed, checked
                within 300 s of confirmed_at. One fresh block per cart (B-104:
                a reused act is 409 UP3_EVIDENCE_REUSED).
            ttl_minutes: CartMandate lifetime in minutes (default 2).
            idempotency_seed: Opaque, caller-stable input the cart.id is
                derived from (e.g. a consent_jti) — NOT the id itself. Pass
                the SAME seed on a transport-level retry (timeout, no
                response, connection reset) of the SAME authorization, so the
                retry regenerates the identical cart.id and the bank answers
                it with the stored outcome (HTTP 200, the original payment)
                instead of posting a second payment.

                Use a NEW seed for every distinct authorization, and whenever
                the user re-confirms after a FAILED/CANCELLED payment — that
                is a new payment, not a retry, and must get a fresh cart. A
                fresh cart could otherwise be produced without touching this
                parameter (the default: random id per call); the seed exists
                only to make a genuine retry collapse onto the same anchor.
                Reusing a seed across two different payments (different
                amount/beneficiary) is safe but the second is rejected as
                UP3_REPLAY (409) — a key reused with new content is a
                conflict, never resolved silently.

                Omit for the legacy behavior: a fresh random id every call
                (no retry-safety).

        Returns:
            Signed CartMandate envelope dict ready to POST as cart_mandate.
        """
        consent_evidence = _require_consent_evidence(consent_evidence)
        if fees_minor is None:
            fees_minor = {}
        if confirmed_at is None:
            confirmed_at = _now_z()

        intent_id = intent_mandate["id"]
        intent_payload = intent_mandate["payload"]

        mandate_id = _derive_cart_id(self._issuer, idempotency_seed) if idempotency_seed is not None else _mandate_id()
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

    def build_cart_v02(
        self,
        intent_mandate: dict[str, Any],
        *,
        quote: dict[str, Any],
        consent_evidence: dict[str, Any],
        beneficiary_name: Optional[str] = _UNSET,  # type: ignore[assignment]
        confirmed_at: Optional[str] = None,
        ttl_minutes: int = 2,
        idempotency_seed: Optional[str] = None,
        execution_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build and sign a **0.2** CartMandate that signs a quote (transfer routes, 0.3.0).

        UP3 0.2-draft P17: the cart no longer carries the recipient's IBAN by
        value nor a rail. It carries the identifier **as the customer saw it**
        (``beneficiary {type, value}``), the display name the preview showed,
        the quote's ``{id, digest, digest_alg}`` and its fee legs — everything
        copied from the ``POST /v1/payments/quotes`` answer, so the bank can
        bind the cart to the quote it stored (digest compared, never
        recomputed) and refuse any drift (``UP3_QUOTE_DRIFT`` /
        ``UP3_FEE_DRIFT``). No ``quote_id`` travels in the request body: the
        cart **is** the quote.

        P12: a cart may not outlive its quote. ``expires_at`` is the earlier of
        ``now + ttl_minutes`` and ``quote.expires_at``; a cart built from an
        already-expired quote is refused by the bank as ``UP3_EXPIRED`` —
        preview again.

        Args:
            intent_mandate: The signed IntentMandate from :meth:`build_intent`
                (``max_amount_minor`` must cover ``quote["amount_minor"]``).
            quote: The **whole** ``client.payments.quote(...)`` response dict
                (``PaymentQuoteResponse``): ``quote {id, digest, digest_alg,
                expires_at}``, ``beneficiary {type, value}``, ``display_name``,
                ``amount_minor``, ``currency``, ``fees_minor``. A quote whose
                ``outcome`` is ``deferred`` cannot be confirmed here (the hold
                goes through ``deferred_transfers.send``).
            beneficiary_name: The name the customer saw. Defaults to the
                quote's ``display_name`` (which may be ``None``); pass a value
                only to shorten it the way your screen did.
            confirmed_at: RFC 3339 Z timestamp of the user's tap. Defaults to now.
            consent_evidence: ``user_consent_evidence``, REQUIRED (P19): the
                customer-present proof, ``chat_session_pin_v1`` today, a fresh
                block per cart. Same contract as :meth:`build_cart`.
            ttl_minutes: Cart lifetime (default 2), clamped to the quote's.
            idempotency_seed: Same contract as :meth:`build_cart` — the SAME
                seed on a transport retry of the SAME authorization derives
                the same ``cart.id`` and the bank answers the stored outcome.
            execution_mode: Optional ``payload.execution_mode`` (B-40):
                ``"immediate"`` | ``"deferred_held"`` | ``"deferred_best_effort"``.
                Omit it and the bank infers it from the quote (this cart
                signs a credit / external quote: ``immediate``). A mode that
                contradicts the quote is refused ``UP3_EXECUTION_MODE_MISMATCH``.

        Returns:
            Signed ``version: "0.2"`` CartMandate envelope, ready to POST as
            ``cart_mandate`` with no instruction fields in the body.

        Raises:
            ValueError: the quote dict lacks the keys a 0.2 cart signs, or is
                a ``deferred`` quote, or ``consent_evidence`` is missing /
                ``service_attestation`` (P19).
        """
        _check_execution_mode(execution_mode)
        consent_evidence = _require_consent_evidence(consent_evidence)
        try:
            ref = quote["quote"]
            quote_id, digest, digest_alg = ref["id"], ref["digest"], ref["digest_alg"]
            beneficiary = quote["beneficiary"]
            amount_minor = int(quote["amount_minor"])
            currency = quote["currency"]
            fees_minor = dict(quote["fees_minor"])
        except (KeyError, TypeError) as exc:
            raise ValueError(
                "build_cart_v02 needs the whole POST /v1/payments/quotes response "
                "(quote {id, digest, digest_alg}, beneficiary {type, value}, amount_minor, "
                f"currency, fees_minor); missing {exc!r}"
            ) from exc
        if quote.get("outcome") == "deferred":
            raise ValueError(
                "a deferred quote (recipient has no account yet) is confirmed with "
                "deferred_transfers.send, not a 0.2 cart"
            )
        if beneficiary_name is _UNSET:
            beneficiary_name = quote.get("display_name")
        if confirmed_at is None:
            confirmed_at = _now_z()

        intent_id = intent_mandate["id"]
        intent_payload = intent_mandate["payload"]
        mandate_id = _derive_cart_id(self._issuer, idempotency_seed) if idempotency_seed is not None else _mandate_id()
        now = _now_z()
        expires = _future_z(ttl_minutes)
        quote_expires = ref.get("expires_at")
        if isinstance(quote_expires, str) and quote_expires:
            expires = min(expires, _to_z(quote_expires))  # P12: never past the quote

        payload: dict[str, Any] = {
            "intent_mandate_id": intent_id,
            "user_ref": intent_payload["user_ref"],
            "amount_minor": amount_minor,
            "currency": currency,
            "beneficiary": {"type": beneficiary["type"], "value": beneficiary["value"]},
            "beneficiary_name": beneficiary_name,
            "quote": {"id": quote_id, "digest": digest, "digest_alg": digest_alg},
            "fees_minor": fees_minor,
            "confirmed_at": confirmed_at,
            "user_consent_evidence": consent_evidence,
        }
        if execution_mode is not None:
            payload["execution_mode"] = execution_mode
        envelope: dict[str, Any] = {
            "version": "0.2",
            "type": "cart",
            "id": mandate_id,
            "issued_at": now,
            "expires_at": expires,
            "issuer": self._issuer,
            "payload": payload,
        }
        envelope["signature"] = sign(envelope, secret=self._secret)
        return envelope

    def build_deferred_cart_v02(
        self,
        intent_mandate: dict[str, Any],
        *,
        refusal: dict[str, Any],
        beneficiary_value: str,
        amount_minor: int,
        consent_evidence: dict[str, Any],
        currency: str = "XOF",
        execute_before: Optional[str] = None,
        hold_days: int = 7,
        confirmed_at: Optional[str] = None,
        ttl_minutes: int = 2,
        idempotency_seed: Optional[str] = None,
        execution_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build and sign a **0.2** CartMandate that consents to a DEFERRED
        transfer — the hold from the quote (bank PR-D, B-67).

        When ``payments.quote(...)`` answers **422 ``RECIPIENT_HAS_NO_ACCOUNT``**
        for a phone nobody holds yet, the refusal carries ``deferred_quote``:
        the quote of the hold the sender may place instead (``bdk.internal``; the
        money moves inside BDK when the recipient opens their account). Since
        0.3.23 it carries the fee legs as the quote priced them (1 %): the hold
        reserves amount + fee, booked when the transfer is executed. This cart
        signs that quote, the phone **as the customer
        typed it**, the amount, and an **execution window**
        (``execute_before``, UP3 0.2-draft R1–R4): the latest moment the bank
        may still execute the consented transfer — the hold runs until then
        (at most the bank's 7-day ceiling) and lapses unclaimed after it.

        Args:
            intent_mandate: The signed IntentMandate from :meth:`build_intent`
                (``max_amount_minor`` must cover ``amount_minor``).
            refusal: The whole 422 body (``error_code`` =
                ``RECIPIENT_HAS_NO_ACCOUNT`` with ``deferred_quote``) **or** its
                ``deferred_quote`` dict (``id``, ``digest``, ``digest_alg``,
                ``expires_at``, ``fees_minor``). A refusal without a deferred
                quote (the recipient is mid-onboarding) cannot be consented.
            beneficiary_value: The phone the customer typed (E.164) — the
                deferred quote names no payee; the bank compares it with the
                phone it quoted.
            amount_minor: The amount quoted (the refusal does not repeat it).
            currency: ``XOF``.
            execute_before: RFC 3339 Z timestamp — the end of the execution
                window. Defaults to ``confirmed_at + hold_days`` days.
            hold_days: Default window length when ``execute_before`` is not
                given (1–7; the bank caps the hold at 7 days).
            confirmed_at: RFC 3339 Z timestamp of the user's tap. Defaults to now.
            consent_evidence: ``user_consent_evidence``, REQUIRED (P19): the
                customer-present proof, ``chat_session_pin_v1`` today, a fresh
                block per cart. Same contract as :meth:`build_cart`.
            ttl_minutes: Cart lifetime (default 2), clamped to the quote's (P12).
            idempotency_seed: Same contract as :meth:`build_cart`: the SAME seed
                on a retry derives the same ``cart.id``, which is the
                ``client_transaction_id`` of the hold — the bank answers the
                stored deferred transfer.
            execution_mode: Optional ``payload.execution_mode`` (B-40).
                Omit it for the hold on the sender's StarMoney account (the
                bank reads ``deferred_held`` from the deferred quote). Pass
                ``"deferred_best_effort"`` to consent instead to the pull from
                the sender's **BDK account** when the recipient opens an
                account: nothing is held, the bank may refuse at that moment
                (short balance), and the transfer then ends ``failed`` with
                nothing taken. The mode is signed with the cart; post it with
                ``funding_source`` omitted (or ``"external_pull"``). Never
                inferred by the bank — it is only ever consented to here.

        Returns:
            Signed ``version: "0.2"`` CartMandate envelope with
            ``payload.execute_before``, ready to POST as ``cart_mandate`` on
            ``POST /v1/deferred-transfers/send`` with no instruction fields.

        Raises:
            ValueError: no deferred quote in the refusal, a non-E.164 phone, a
                non-positive amount, ``hold_days`` outside 1–7, or
                ``consent_evidence`` missing / ``service_attestation`` (P19).
        """
        _check_execution_mode(execution_mode)
        consent_evidence = _require_consent_evidence(consent_evidence)
        dq = refusal.get("deferred_quote") if "deferred_quote" in refusal else refusal
        if not isinstance(dq, dict) or "digest" not in dq:
            raise ValueError(
                "build_deferred_cart_v02 needs the RECIPIENT_HAS_NO_ACCOUNT refusal that carries "
                "deferred_quote {id, digest, digest_alg, expires_at, fees_minor} — a refusal "
                "without one (recipient mid-onboarding) cannot be consented; ask again later"
            )
        try:
            quote_id, digest, digest_alg = dq["id"], dq["digest"], dq["digest_alg"]
            fees_minor = dict(dq["fees_minor"])
        except (KeyError, TypeError) as exc:
            raise ValueError(f"deferred_quote lacks {exc!r}") from exc
        if not isinstance(beneficiary_value, str) or not beneficiary_value.startswith("+"):
            raise ValueError("beneficiary_value must be the recipient's phone in E.164 form (+221…)")
        amount_minor = int(amount_minor)
        if amount_minor <= 0:
            raise ValueError("amount_minor must be > 0")
        if not 1 <= int(hold_days) <= 7:
            raise ValueError("hold_days must be between 1 and 7 (the bank caps the hold at 7 days)")
        if confirmed_at is None:
            confirmed_at = _now_z()
        if execute_before is None:
            anchor = datetime.strptime(confirmed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            execute_before = (anchor + timedelta(days=int(hold_days))).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            execute_before = _to_z(execute_before)

        intent_id = intent_mandate["id"]
        intent_payload = intent_mandate["payload"]
        mandate_id = _derive_cart_id(self._issuer, idempotency_seed) if idempotency_seed is not None else _mandate_id()
        now = _now_z()
        expires = _future_z(ttl_minutes)
        quote_expires = dq.get("expires_at")
        if isinstance(quote_expires, str) and quote_expires:
            expires = min(expires, _to_z(quote_expires))  # P12: never past the quote

        payload: dict[str, Any] = {
            "intent_mandate_id": intent_id,
            "user_ref": intent_payload["user_ref"],
            "amount_minor": amount_minor,
            "currency": currency,
            "beneficiary": {"type": "msisdn", "value": beneficiary_value},
            "beneficiary_name": None,  # nobody holds the number yet: no name was shown
            "quote": {"id": quote_id, "digest": digest, "digest_alg": digest_alg},
            "fees_minor": fees_minor,
            "execute_before": execute_before,
            "confirmed_at": confirmed_at,
            "user_consent_evidence": consent_evidence,
        }
        if execution_mode is not None:
            payload["execution_mode"] = execution_mode
        envelope: dict[str, Any] = {
            "version": "0.2",
            "type": "cart",
            "id": mandate_id,
            "issued_at": now,
            "expires_at": expires,
            "issuer": self._issuer,
            "payload": payload,
        }
        envelope["signature"] = sign(envelope, secret=self._secret)
        return envelope

    def cart_id_for(self, idempotency_seed: str) -> str:
        """The cart.id that ``build_cart(..., idempotency_seed=seed)`` derives.

        Same derivation as the build (``_derive_cart_id``), for callers that
        need the id without rebuilding the cart: a status lookup after a
        timeout, a log line before the send.

        Raises:
            ValueError: seed is empty or whitespace-only.
        """
        return _derive_cart_id(self._issuer, idempotency_seed)

    def verify_payment_mandate(self, envelope: dict[str, Any], *, orchestrator_secret: Optional[bytes] = None) -> bool:
        """Verify the Orchestrator's signature on a PaymentMandate envelope.

        A PaymentMandate is signed by the ORCHESTRATOR (StarMoney) with its own
        key, not by this client. Pass that key as ``orchestrator_secret`` to
        verify. Without it the check runs against this client's own secret,
        which is NOT the signing key in production and will return False; that
        default exists only for sandboxes where both sides share one secret.
        Note that any party holding an HMAC key that verifies can also forge;
        real third-party verification arrives with asymmetric PaymentMandate
        signatures (UP3 0.2-draft).

        The SDK does NOT raise on invalid signature by default — callers decide
        how to surface UP3_SIG_INVALID (log for audit, surface to user, etc.).

        Args:
            envelope: The full PaymentMandate dict including 'signature'.
            orchestrator_secret: The Orchestrator's HMAC key, if you hold it.

        Returns:
            True if signature is valid, False otherwise.
        """
        return verify(envelope, secret=orchestrator_secret or self._secret)

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
            raise UP3SignatureInvalid(f"PaymentMandate signature did not verify for issuer={issuer!r}")
        return True
