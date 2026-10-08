"""StarMoney Python SDK - Custom Exceptions"""

from typing import Any, Optional


def _default_kind_for_status(status_code: int) -> str:
    """Best-effort ``kind`` when the server's response doesn't carry one
    (legacy body, or a status this SDK doesn't recognise) — see B-32."""
    if status_code in (400, 422):
        return "validation"
    if status_code in (403, 404, 409, 429):
        return "state"
    if status_code >= 500:
        return "technical"
    return "validation"


def _parse_envelope(response_data: Optional[dict[str, Any]], status_code: int) -> dict[str, Any]:
    """Parse the B-32 error envelope into
    ``{error_code, kind, errors, error_id, message}``.

    Top-level keys are read first; a ``detail`` dict (either the current
    release's one-release legacy-compat object, or an old server's nested
    shape) is the fallback for every field — so this parses the flat shape,
    the transitional flat+``detail``-object shape, and the pre-B-32 nested
    shape with the same code. ``errors`` is always a list (never ``None``).
    """
    data = response_data or {}
    nested = data.get("detail") if isinstance(data.get("detail"), dict) else {}

    error_code = data.get("error_code") or nested.get("error_code") or ""
    kind = data.get("kind") or nested.get("kind") or _default_kind_for_status(status_code)
    errors = data.get("errors")
    if errors is None:
        errors = nested.get("errors")
    if not isinstance(errors, list):
        errors = []
    error_id = data.get("error_id") or nested.get("error_id")
    message = data.get("message") or nested.get("message")

    return {
        "error_code": error_code,
        "kind": kind,
        "errors": errors,
        "error_id": error_id,
        "message": message,
    }


class StarmoneyError(Exception):
    """Base exception for all StarMoney SDK errors."""

    pass


class APIError(StarmoneyError):
    """
    Error from StarMoney API response.

    Attributes:
        status_code: HTTP status code
        message: Developer-facing English — the envelope's top-level
            ``message`` when present, else its (deprecated, one-release)
            ``detail.message``, else the ``message`` the caller/http_client
            passed in (e.g. derived from response text on a transport error).
        response_data: Full response data from API
        error_code: Machine-readable code from the B-32 envelope ("" when
            the server didn't send one — e.g. a transport-level failure).
        kind: One of "validation" | "state" | "technical" (B-32). Parsed from
            the envelope when present, else a best-effort default by status.
        errors: Field-level detail list from the envelope. Never ``None`` —
            ``[]`` when there is none.
        error_id: The server's correlation id for this error, when present.
    """

    def __init__(self, status_code: int, message: str, response_data: Optional[dict[str, Any]] = None):
        self.status_code = status_code
        self.response_data = response_data or {}
        envelope = _parse_envelope(self.response_data, status_code)
        self.message: str = envelope["message"] or message
        self.error_code: str = envelope["error_code"]
        self.kind: str = envelope["kind"]
        self.errors: list[dict[str, Any]] = envelope["errors"]
        self.error_id: Optional[str] = envelope["error_id"]
        super().__init__(f"[{status_code}] {self.message}")


class AuthenticationError(APIError):
    """401 - Invalid or expired authentication credentials."""

    pass


class ValidationError(APIError):
    """400 - Invalid request data or parameters."""

    pass


class PaymentNotFoundError(APIError):
    """404 - Payment not found."""

    pass


class DuplicateResourceError(APIError):
    """409 - Resource already exists (e.g., duplicate payment or beneficiary).

    For beneficiaries the server returns ``error_code == "DUPLICATE_BENEFICIARY"``
    alongside the 409.
    """

    @property
    def existing_id(self) -> Optional[str]:
        """Id of the row that already exists, when the server names it:
        ``beneficiary_id`` (an active beneficiary with that IBAN) or
        ``beneficiary_request_id`` (a pending request for that number)."""
        d = self.response_data or {}
        legacy = d.get("detail") if isinstance(d.get("detail"), dict) else {}
        detail = {**legacy, **{k: v for k, v in d.items() if k != "detail"}}
        if not isinstance(detail, dict):
            return None
        return detail.get("beneficiary_id") or detail.get("beneficiary_request_id")

    pass


class InvalidIBANError(APIError):
    """422 - IBAN failed validation (bad format/length or mod-97 checksum).

    Raised both client-side (fast-fail before the request, from
    ``beneficiaries.create``/``update``) and when the server responds with
    ``error_code == "INVALID_IBAN"``. Distinguishable from
    ``DuplicateResourceError`` (duplicate), ``AuthenticationError``
    (unauthorized), and a generic ``APIError``, so a caller can tell the user
    to correct the IBAN before anything is persisted.
    """

    def __init__(
        self,
        message: str = "Invalid IBAN",
        response_data: Optional[dict[str, Any]] = None,
        status_code: int = 422,
    ):
        super().__init__(status_code, message, response_data)


class PreKycCeilingExceededError(APIError):
    """403 - the send exceeds the PER-SEND ceiling of a holder the bank has not
    verified yet (``error_code == "PRE_KYC_CEILING_EXCEEDED"``)."""

    pass


class PreKycTotalCeilingExceededError(APIError):
    """403 - the send would take the holder's CUMULATIVE sends past the pre-KYC
    total ceiling (``error_code == "PRE_KYC_TOTAL_CEILING_EXCEEDED"``).

    Lifetime until the bank verifies the holder — there is no reset date.
    ``remaining_minor`` is what may still be sent (« envois possibles »): a
    count of the holder's own sends, NOT the money in their account.
    """

    @property
    def ceiling_minor(self) -> Optional[int]:
        return self.response_data.get("ceiling_minor")

    @property
    def consumed_minor(self) -> Optional[int]:
        return self.response_data.get("consumed_minor")

    @property
    def pending_minor(self) -> Optional[int]:
        return self.response_data.get("pending_minor")

    @property
    def remaining_minor(self) -> Optional[int]:
        return self.response_data.get("remaining_minor")


class SelfTransferNotAllowedError(APIError):
    """422 ``SELF_TRANSFER_NOT_ALLOWED`` — the number, handle or vIBAN is the
    caller's own (B-27 contract §1/§5). Raised by ``beneficiaries.create``,
    ``payments.*`` and ``deferred_transfers.send``. Exception on the server:
    the customer's own linked bank account, by IBAN."""


class InvalidPhoneError(APIError):
    """422 ``INVALID_PHONE`` — the phone number failed normalisation
    (libphonenumber). ``response_data["detail"]["errors"]`` names the field."""


class BeneficiaryAddLimitReachedError(APIError):
    """429 ``BENEFICIARY_ADD_LIMIT_REACHED`` — more than 20 phone/handle adds
    in the rolling 24 h (201 and 202 both count). ``retry_after_seconds`` says
    when the oldest add leaves the window."""

    @property
    def retry_after_seconds(self) -> Optional[int]:
        d = self.response_data or {}
        legacy = d.get("detail") if isinstance(d.get("detail"), dict) else {}
        detail = {**legacy, **{k: v for k, v in d.items() if k != "detail"}}
        if not isinstance(detail, dict):
            return None
        value = detail.get("retry_after_seconds")
        return int(value) if value is not None else None


class RateLimitError(APIError):
    """429 - Too many requests."""

    pass


class ServerError(APIError):
    """500+ - Internal server error."""

    pass


class NoVibanAccountError(APIError):
    """404 - the holder has no vIBAN (yet), so there is no balance to read
    (``error_code == "NO_VIBAN_ACCOUNT"``)."""

    pass


class AccountNotPayableError(APIError):
    """409 - the holder's vIBAN account is closed (``error_code == "ACCOUNT_NOT_PAYABLE"``)."""

    pass


class LedgerUnavailableError(ServerError):
    """503 - the vIBAN ledger could not be read (``error_code == "LEDGER_UNAVAILABLE"``).
    Transient: retry later."""

    pass


class InvalidSignatureError(StarmoneyError):
    """Webhook signature validation failed."""

    pass


# ---------------------------------------------------------------------------
# UP3 protocol errors — 13 stable codes from SPEC.md §6.1
# These are raised by the SDK's UP3 resource and by the HTTP client when the
# API response body contains a UP3_* error code.
#
# HTTP -> UP3 code mapping (per docs/up3-chatbot-integration.md §5.3):
#   400 -> UP3_SCHEMA_INVALID
#   401 -> UP3_SIG_INVALID, UP3_KEY_NOT_REGISTERED
#   409 -> UP3_REPLAY
#   410 -> UP3_EXPIRED
#   422 -> all other UP3 codes
# ---------------------------------------------------------------------------


class UP3Error(StarmoneyError):
    """Base class for all UP3 protocol errors surfaced by the SDK.

    Carries the same B-32 attributes as ``APIError`` (``error_code``,
    ``kind``, ``errors``, ``error_id``) so callers can branch on them
    uniformly regardless of whether the server refused with a UP3_* code or
    any other domain error. ``error_code`` defaults to ``self.code`` (the
    UP3-specific identifier, e.g. ``"UP3_SIG_INVALID"``) when the response
    doesn't carry its own — which is the common case, since the server's
    UP3Error.error_code IS ``exc.code``.
    """

    code: str = "UP3_UNKNOWN"

    def __init__(self, message: str = "", response_data: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.response_data = response_data or {}
        envelope = _parse_envelope(self.response_data, 422)
        self.message: str = envelope["message"] or message
        self.error_code: str = envelope["error_code"] or self.code
        self.kind: str = envelope["kind"]
        self.errors: list[dict[str, Any]] = envelope["errors"]
        self.error_id: Optional[str] = envelope["error_id"]

    def __str__(self) -> str:
        return f"{self.code}: {self.message}" if self.message else self.code


class UP3SignatureInvalid(UP3Error):
    """UP3_SIG_INVALID — Mandate signature did not verify (HTTP 401)."""

    code = "UP3_SIG_INVALID"


class UP3KeyNotRegistered(UP3Error):
    """UP3_KEY_NOT_REGISTERED — Unknown issuer (HTTP 401)."""

    code = "UP3_KEY_NOT_REGISTERED"


class UP3ChainBroken(UP3Error):
    """UP3_CHAIN_BROKEN — Intent/Cart references inconsistent (HTTP 422)."""

    code = "UP3_CHAIN_BROKEN"


class UP3Expired(UP3Error):
    """UP3_EXPIRED — Mandate expired (HTTP 410)."""

    code = "UP3_EXPIRED"


class UP3Replay(UP3Error):
    """UP3_REPLAY — a cart id was reused with different content, or by a different
    user/service (HTTP 409).

    A same-seed retry with the same content is NOT an error: the API answers
    HTTP 200 with the original payment and its stored PaymentMandate at the
    latest revision (ADR-005).
    """

    code = "UP3_REPLAY"


class UP3AmountExceedsIntent(UP3Error):
    """UP3_AMOUNT_EXCEEDS_INTENT — cart.amount_minor > intent.max_amount_minor (HTTP 422)."""

    code = "UP3_AMOUNT_EXCEEDS_INTENT"


class UP3SchemaInvalid(UP3Error):
    """UP3_SCHEMA_INVALID — Envelope failed JSON schema (HTTP 400)."""

    code = "UP3_SCHEMA_INVALID"


class UP3TypeNotAccepted(UP3Error):
    """UP3_TYPE_NOT_ACCEPTED — consent_evidence.type not in allowlist (HTTP 422)."""

    code = "UP3_TYPE_NOT_ACCEPTED"


class UP3RevisionFieldDrift(UP3Error):
    """UP3_REVISION_FIELD_DRIFT — PaymentMandate revision changed immutable field (HTTP 422)."""

    code = "UP3_REVISION_FIELD_DRIFT"


class UP3StatusInvalid(UP3Error):
    """UP3_STATUS_INVALID — PaymentMandate status outside closed enum (HTTP 422)."""

    code = "UP3_STATUS_INVALID"


class UP3BeneficiaryDrift(UP3Error):
    """UP3_BENEFICIARY_DRIFT — payment.beneficiary_iban != cart.beneficiary_iban (HTTP 422)."""

    code = "UP3_BENEFICIARY_DRIFT"


class UP3RailDrift(UP3Error):
    """UP3_RAIL_DRIFT — payment.rail != cart.rail (HTTP 422)."""

    code = "UP3_RAIL_DRIFT"


class UP3RevisionRegression(UP3Error):
    """UP3_REVISION_REGRESSION — revision != prior+1 or prior was terminal (HTTP 422)."""

    code = "UP3_REVISION_REGRESSION"


class UP3MandateRequired(UP3Error):
    """UP3_MANDATE_REQUIRED — the verifier's policy flags your issuer as
    mandate-required and this payment carried no Intent + Cart chain (HTTP 409).

    A refusal: nothing was sent, nothing was written. It is NOT a duplicate.
    (0.2-draft staging profile P9.)
    """

    code = "UP3_MANDATE_REQUIRED"


class UP3PayerMismatch(UP3Error):
    """UP3_PAYER_MISMATCH — cart.user_ref does not resolve to the authenticated
    payer (HTTP 409). A refusal, nothing written. (Profile P2.)"""

    code = "UP3_PAYER_MISMATCH"


class UP3IssuerMismatch(UP3Error):
    """UP3_ISSUER_MISMATCH — cart.issuer is not the authenticated caller
    (HTTP 409). A refusal, nothing written. (Profile P3.)"""

    code = "UP3_ISSUER_MISMATCH"


class UP3TypeRequiredMissing(UP3Error):
    """UP3_TYPE_REQUIRED_MISSING — the verifier requires a consent-evidence type
    for your issuer and the cart carries a different, merely accepted, one
    (HTTP 422). (Profile P10.)"""

    code = "UP3_TYPE_REQUIRED_MISSING"


# Map error code strings -> exception classes for http_client error handling.
UP3_ERROR_CODE_MAP: dict[str, type[UP3Error]] = {
    "UP3_MANDATE_REQUIRED": UP3MandateRequired,
    "UP3_PAYER_MISMATCH": UP3PayerMismatch,
    "UP3_ISSUER_MISMATCH": UP3IssuerMismatch,
    "UP3_TYPE_REQUIRED_MISSING": UP3TypeRequiredMissing,
    "UP3_SIG_INVALID": UP3SignatureInvalid,
    "UP3_KEY_NOT_REGISTERED": UP3KeyNotRegistered,
    "UP3_CHAIN_BROKEN": UP3ChainBroken,
    "UP3_EXPIRED": UP3Expired,
    "UP3_REPLAY": UP3Replay,
    "UP3_AMOUNT_EXCEEDS_INTENT": UP3AmountExceedsIntent,
    "UP3_SCHEMA_INVALID": UP3SchemaInvalid,
    "UP3_TYPE_NOT_ACCEPTED": UP3TypeNotAccepted,
    "UP3_REVISION_FIELD_DRIFT": UP3RevisionFieldDrift,
    "UP3_STATUS_INVALID": UP3StatusInvalid,
    "UP3_BENEFICIARY_DRIFT": UP3BeneficiaryDrift,
    "UP3_RAIL_DRIFT": UP3RailDrift,
    "UP3_REVISION_REGRESSION": UP3RevisionRegression,
}
