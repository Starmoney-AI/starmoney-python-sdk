"""UP3 refusals surface as UP3 errors, never as "duplicates" (0.1.24).

Adita's P9 round (4 Oct 2026): a 409 UP3_MANDATE_REQUIRED came back as
DuplicateResourceError, whose name says "already exists". A caller mapping that
to "already done" would tell a customer their money left when nothing was sent.
"""

from unittest.mock import MagicMock

import httpx
import pytest

from starmoney.exceptions import (
    DuplicateResourceError,
    UP3Error,
    UP3CartAbandoned,
    UP3ExecutionModeMismatch,
    UP3Expired,
    UP3IssuerMismatch,
    UP3MandateRequired,
    UP3PayerMismatch,
    UP3Replay,
    UP3TypeNotAccepted,
    UP3TypeRequiredMissing,
)
from starmoney.http_client import HTTPClient


def _handle(status: int, body: dict) -> None:
    response = httpx.Response(status, json=body, request=httpx.Request("POST", "http://x/v1/payments"))
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


def test_mandate_required_409_is_a_up3_refusal_not_a_duplicate():
    body = {
        "detail": (
            "UP3_MANDATE_REQUIRED: the payment carries no Intent + Cart chain; "
            "every send needs a mandate with customer-present proof (P19)"
        ),
        "error_id": "69819c6e",
    }
    with pytest.raises(UP3MandateRequired) as exc_info:
        _handle(409, body)
    assert exc_info.value.code == "UP3_MANDATE_REQUIRED"
    assert not isinstance(exc_info.value, DuplicateResourceError)


@pytest.mark.parametrize(
    "status, code, cls",
    [
        (409, "UP3_PAYER_MISMATCH", UP3PayerMismatch),
        (409, "UP3_ISSUER_MISMATCH", UP3IssuerMismatch),
        (409, "UP3_REPLAY", UP3Replay),
        (409, "UP3_EXECUTION_MODE_MISMATCH", UP3ExecutionModeMismatch),
        (409, "UP3_CART_ABANDONED", UP3CartAbandoned),
        (410, "UP3_EXPIRED", UP3Expired),
        (422, "UP3_TYPE_REQUIRED_MISSING", UP3TypeRequiredMissing),
    ],
)
def test_known_up3_codes_map_to_their_class(status, code, cls):
    with pytest.raises(cls):
        _handle(status, {"detail": f"{code}: details"})


def test_an_unknown_up3_code_is_still_a_up3_error_with_the_code_set():
    with pytest.raises(UP3Error) as exc_info:
        _handle(409, {"detail": "UP3_FUTURE_CODE: a code a newer verifier adds"})
    assert exc_info.value.code == "UP3_FUTURE_CODE"
    assert not isinstance(exc_info.value, DuplicateResourceError)


def test_a_plain_409_is_still_a_duplicate():
    with pytest.raises(DuplicateResourceError):
        _handle(409, {"detail": "Payment with client_transaction_id x already exists"})


def test_type_not_accepted_422_b32_envelope_maps_to_its_class():
    """P19: a service_attestation (or any unaccepted evidence type) is refused with a B-32 envelope."""
    errors = [
        {
            "field": "payload.user_consent_evidence.type",
            "rule": "enum.invalid",
            "expected": "chat_session_pin_v1",
            "received": "service_attestation",
        }
    ]
    body = {
        "error_code": "UP3_TYPE_NOT_ACCEPTED",
        "kind": "validation",
        "message": "user_consent_evidence.type is not accepted",
        "error_id": "corr-p19",
        "errors": errors,
        "detail": {
            "message": "user_consent_evidence.type is not accepted",
            "error_code": "UP3_TYPE_NOT_ACCEPTED",
            "errors": errors,
        },
    }
    with pytest.raises(UP3TypeNotAccepted) as exc_info:
        _handle(422, body)
    assert exc_info.value.code == "UP3_TYPE_NOT_ACCEPTED"
    assert exc_info.value.error_code == "UP3_TYPE_NOT_ACCEPTED"
    assert exc_info.value.kind == "validation"
    assert exc_info.value.errors[0]["rule"] == "enum.invalid"
    assert exc_info.value.errors[0]["expected"] == "chat_session_pin_v1"
