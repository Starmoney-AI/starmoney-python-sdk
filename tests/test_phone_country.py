"""B-45: 422 PHONE_COUNTRY_NOT_SUPPORTED maps to its own class, still an InvalidPhoneError."""

from __future__ import annotations

import pytest

from starmoney import InvalidPhoneError, PhoneCountryNotSupportedError
from starmoney.auth import AuthManager
from starmoney.http_client import HTTPClient


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def test_handle_error_maps_phone_country_not_supported():
    client = HTTPClient(
        base_url="http://test.local",
        auth=AuthManager("test-secret-at-least-32-characters-long!!"),
    )
    body = {
        "error_code": "PHONE_COUNTRY_NOT_SUPPORTED",
        "kind": "validation",
        "message": "recipient numbers from GB are not supported here (allowed: SN)",
        "detail": "recipient numbers from GB are not supported here (allowed: SN)",
        "errors": [
            {
                "field": "beneficiary.value",
                "rule": "phone.country_not_supported",
                "received": "+447911123456",
                "expected": "SN",
            }
        ],
    }
    with pytest.raises(PhoneCountryNotSupportedError) as ei:
        client._handle_error(_FakeResponse(422, body))
    err = ei.value
    assert isinstance(err, InvalidPhoneError)  # existing handlers keep catching it
    assert err.error_code == "PHONE_COUNTRY_NOT_SUPPORTED"
    assert err.errors[0]["expected"] == "SN"
