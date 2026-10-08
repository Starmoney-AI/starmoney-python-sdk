"""Unit tests for the B-32 explainable-error attributes on SDK exceptions
(sdk/python/starmoney/exceptions.py, 0.1.26).

Every APIError/UP3Error (sub)class exposes `.error_code`, `.kind`, `.errors`
(always a list, never None) and `.error_id`, parsed from either the flat
envelope (current server) or the legacy nested `detail` dict (old server).
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


def test_flat_envelope_parses_error_code_kind_errors_error_id():
    body = {
        "error_code": "INVALID_IBAN",
        "kind": "validation",
        "detail": "Invalid IBAN (iban.checksum)",
        "error_id": "corr-123",
        "errors": [{"field": "iban", "rule": "iban.checksum", "expected": "mod-97 remainder 1", "received": "SN12X"}],
    }
    err = InvalidIBANError(body["detail"], body, 422)

    assert err.error_code == "INVALID_IBAN"
    assert err.kind == "validation"
    assert err.error_id == "corr-123"
    assert err.errors == [
        {"field": "iban", "rule": "iban.checksum", "expected": "mod-97 remainder 1", "received": "SN12X"}
    ]
    # The rule is reachable at the documented path.
    assert err.errors[0]["rule"] == "iban.checksum"


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
