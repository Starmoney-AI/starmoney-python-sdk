"""StarMoney Python SDK - Custom Exceptions"""

from typing import Any, Optional


class StarmoneyError(Exception):
    """Base exception for all StarMoney SDK errors."""

    pass


class APIError(StarmoneyError):
    """
    Error from StarMoney API response.

    Attributes:
        status_code: HTTP status code
        message: Error message
        response_data: Full response data from API
    """

    def __init__(
        self, status_code: int, message: str, response_data: Optional[dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.message = message
        self.response_data = response_data or {}
        super().__init__(f"[{status_code}] {message}")


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
    """409 - Resource already exists (e.g., duplicate payment)."""

    pass


class RateLimitError(APIError):
    """429 - Too many requests."""

    pass


class ServerError(APIError):
    """500+ - Internal server error."""

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
    """Base class for all UP3 protocol errors surfaced by the SDK."""

    code: str = "UP3_UNKNOWN"

    def __init__(self, message: str = "", response_data: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.response_data = response_data or {}

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
    """UP3_REPLAY — Mandate id already seen within replay window (HTTP 409)."""

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


# Map error code strings -> exception classes for http_client error handling.
UP3_ERROR_CODE_MAP: dict[str, type[UP3Error]] = {
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
