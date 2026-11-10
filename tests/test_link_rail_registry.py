"""Linking BDK from the bank's registry (link_rail / unlink_rail) and its typed errors (B-95)."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney import LinkableAccountNotFoundError, LinkVerificationFailedError
from starmoney.exceptions import BankUnavailableError, InvalidIBANError, PaymentNotFoundError
from starmoney.http_client import HTTPClient
from starmoney.resources.accounts import AccountsResource


def _handle(status: int, body: dict) -> None:
    response = httpx.Response(
        status, json=body, request=httpx.Request("POST", "http://x/v1/accounts/rails/bdk")
    )
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


@pytest.mark.asyncio
async def test_link_rail_sends_only_the_iban():
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"status": "linked", "rail_name": "bdk"}
    http.post = AsyncMock(return_value=resp)

    result = await AccountsResource(http).link_rail(
        "user-1", account_reference="SN40 K001 0010 1000 0000 0000 0101"
    )

    http.post.assert_awaited_once_with(
        "/accounts/rails/BDK",
        user_id="user-1",
        json={"account_reference": "SN40 K001 0010 1000 0000 0000 0101"},
    )
    assert result["status"] == "linked"


@pytest.mark.asyncio
async def test_unlink_rail_deletes_the_link():
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"rail_name": "bdk", "status": "unlinked"}
    http.delete = AsyncMock(return_value=resp)

    result = await AccountsResource(http).unlink_rail("user-1")

    http.delete.assert_awaited_once_with("/accounts/rails/BDK", user_id="user-1")
    assert result == {"rail_name": "bdk", "status": "unlinked"}


@pytest.mark.parametrize(
    "status,code,exc",
    [
        (404, "LINKABLE_ACCOUNT_NOT_FOUND", LinkableAccountNotFoundError),
        (409, "LINK_VERIFICATION_FAILED", LinkVerificationFailedError),
        (503, "BANK_UNAVAILABLE", BankUnavailableError),
        (404, "RAIL_NOT_LINKED", PaymentNotFoundError),
    ],
)
def test_link_error_codes_raise_typed_errors(status, code, exc):
    with pytest.raises(exc):
        _handle(status, {"error_code": code, "kind": "state", "message": "m", "rail_name": "bdk"})


def test_missing_iban_on_a_first_link_is_invalid_iban():
    body = {
        "error_code": "INVALID_IBAN",
        "kind": "validation",
        "message": "Invalid IBAN (field.required)",
        "errors": [{"field": "account_reference", "rule": "field.required", "received": None}],
    }
    with pytest.raises(InvalidIBANError):
        _handle(422, body)
