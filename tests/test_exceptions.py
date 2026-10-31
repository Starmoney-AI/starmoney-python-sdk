"""Unit tests for the B-32 explainable-error attributes on SDK exceptions
(sdk/python/starmoney/exceptions.py, 0.2.1).

Every APIError/UP3Error (sub)class exposes `.error_code`, `.kind`, `.errors`
(always a list, never None), `.error_id` and `.message`, parsed from either
the flat envelope (current server) or the legacy nested `detail` dict (old
server). For this release only, the server's `detail` is itself an object
`{"message", "error_code", "errors"}` (a one-release compat shim — see
docs/ERRORS.md in starmoney-bank-service); `.message` prefers the top-level
`message` key and falls back to `detail.message`.
"""

from __future__ import annotations

import pytest

from starmoney.exceptions import (
    APIError,
    AuthenticationError,
    DuplicateResourceError,
    InvalidIBANError,
    InvalidPhoneError,
    PaymentNotFoundError,
    RateLimitError,
    ServerError,
    UP3Error,
    UP3Replay,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Flat envelope (current server shape, B-32)
# ---------------------------------------------------------------------------


def test_flat_envelope_parses_error_code_kind_errors_error_id_message():
    errors = [{"field": "iban", "rule": "iban.checksum", "expected": "mod-97 remainder 1", "received": "SN12X"}]
    body = {
        "error_code": "INVALID_IBAN",
        "kind": "validation",
        "message": "Invalid IBAN (iban.checksum)",
        "error_id": "corr-123",
        "errors": errors,
        # One-release legacy compat object — mirrors the top-level keys.
        "detail": {"message": "Invalid IBAN (iban.checksum)", "error_code": "INVALID_IBAN", "errors": errors},
    }
    err = InvalidIBANError(body["message"], body, 422)

    assert err.error_code == "INVALID_IBAN"
    assert err.kind == "validation"
    assert err.error_id == "corr-123"
    assert err.message == "Invalid IBAN (iban.checksum)"
    assert err.errors == errors
    # The rule is reachable at the documented path.
    assert err.errors[0]["rule"] == "iban.checksum"


def test_top_level_message_wins_over_detail_message():
    body = {
        "error_code": "INVALID_IBAN",
        "message": "top-level text",
        "detail": {"message": "stale detail text", "error_code": "INVALID_IBAN", "errors": []},
    }
    err = APIError(422, "constructor fallback", body)
    assert err.message == "top-level text"


def test_message_falls_back_to_detail_message_when_top_level_absent():
    body = {"detail": {"message": "only in detail", "error_code": "X", "errors": []}}
    err = APIError(422, "constructor fallback", body)
    assert err.message == "only in detail"


def test_message_falls_back_to_constructor_arg_when_envelope_has_none():
    err = APIError(500, "constructor fallback", {"error_code": "X"})
    assert err.message == "constructor fallback"


def test_errors_is_always_a_list_never_none_when_absent():
    err = APIError(404, "not found", {"error_code": "PAYMENT_NOT_FOUND", "kind": "state"})
    assert err.errors == []
    assert err.errors is not None


def test_errors_is_empty_list_with_no_response_data_at_all():
    err = APIError(500, "boom", None)
    assert err.errors == []
    assert err.error_code == ""
    assert err.error_id is None


# ---------------------------------------------------------------------------
# Legacy nested `detail` dict (old server shape, pre-B-32)
# ---------------------------------------------------------------------------


def test_legacy_nested_detail_dict_is_still_parsed():
    legacy_body = {
        "detail": {
            "error_code": "INVALID_PHONE",
            "kind": "validation",
            "message": "Invalid phone number",
            "errors": [{"field": "phone", "rule": "phone.normalisation", "received": "nope"}],
            "error_id": "corr-legacy",
        }
    }
    err = InvalidPhoneError(422, "Invalid phone number", legacy_body)

    assert err.error_code == "INVALID_PHONE"
    assert err.kind == "validation"
    assert err.error_id == "corr-legacy"
    assert err.message == "Invalid phone number"
    assert err.errors == [{"field": "phone", "rule": "phone.normalisation", "received": "nope"}]


def test_legacy_nested_detail_dict_with_no_errors_key_is_empty_list():
    legacy_body = {"detail": {"error_code": "DUPLICATE_BENEFICIARY", "message": "already exists"}}
    err = DuplicateResourceError(409, "already exists", legacy_body)
    assert err.errors == []
    assert err.error_code == "DUPLICATE_BENEFICIARY"


# ---------------------------------------------------------------------------
# Default `kind` by status when the server doesn't send one at all
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls,status_code,expected_kind",
    [
        (ValidationError, 400, "validation"),
        (AuthenticationError, 401, "validation"),
        (PaymentNotFoundError, 404, "state"),
        (DuplicateResourceError, 409, "state"),
        (RateLimitError, 429, "state"),
        (ServerError, 500, "technical"),
        (ServerError, 503, "technical"),
    ],
)
def test_default_kind_by_status_when_server_omits_kind(cls, status_code, expected_kind):
    err = cls(status_code, "message", {"error_code": "SOMETHING"})
    assert err.kind == expected_kind


# ---------------------------------------------------------------------------
# Every typed exception exposes the three B-32 attributes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        APIError,
        AuthenticationError,
        ValidationError,
        PaymentNotFoundError,
        DuplicateResourceError,
        RateLimitError,
        ServerError,
    ],
)
def test_every_api_error_subclass_exposes_the_three_attributes(cls):
    err = cls(422, "message", {"error_code": "X", "kind": "validation", "errors": []})
    assert hasattr(err, "error_code")
    assert hasattr(err, "kind")
    assert hasattr(err, "errors")
    assert hasattr(err, "message")
    assert hasattr(err, "error_id")
    assert err.errors == []


# ---------------------------------------------------------------------------
# UP3 errors carry the same attributes
# ---------------------------------------------------------------------------


def test_up3_error_defaults_error_code_to_its_own_code():
    err = UP3Replay("already seen")
    assert err.error_code == "UP3_REPLAY"
    assert err.errors == []
    assert err.kind in ("validation", "state", "technical")


def test_up3_error_prefers_the_server_envelopes_kind_when_present():
    err = UP3Replay("already seen", {"error_code": "UP3_REPLAY", "kind": "state", "error_id": "c1"})
    assert err.kind == "state"
    assert err.error_id == "c1"


def test_generic_up3_error_exposes_the_three_attributes():
    err = UP3Error("something new", {"kind": "validation"})
    assert err.error_code == "UP3_UNKNOWN"
    assert err.kind == "validation"
    assert err.errors == []
    assert err.message == "something new"


def test_up3_error_message_prefers_top_level_envelope_message():
    err = UP3Replay("constructor fallback", {"message": "server text", "error_code": "UP3_REPLAY"})
    assert err.message == "server text"
