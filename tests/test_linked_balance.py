"""Linked BDK account balance (accounts.get_linked_balance) and its typed errors (B-92)."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney.exceptions import (
    BankUnavailableError,
    LinkedAccountReferenceMissingError,
    LinkedAccountRejectedError,
    ServerError,
)
from starmoney.http_client import HTTPClient
from starmoney.resources.accounts import AccountsResource


def _handle(status: int, body: dict) -> None:
    response = httpx.Response(
        status, json=body, request=httpx.Request("GET", "http://x/v1/accounts/rails/bdk/balance")
    )
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


@pytest.mark.asyncio
async def test_get_linked_balance_calls_the_rail_path():
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {"available_minor": 1_536_228, "balance_minor": 1_711_576}
    http.get = AsyncMock(return_value=resp)

    result = await AccountsResource(http).get_linked_balance("user-1")

    http.get.assert_awaited_once_with("/accounts/rails/bdk/balance", user_id="user-1")
    assert result["available_minor"] == 1_536_228


@pytest.mark.parametrize(
    "status,code,exc",
    [
        (409, "LINKED_ACCOUNT_REFERENCE_MISSING", LinkedAccountReferenceMissingError),
        (409, "LINKED_ACCOUNT_REJECTED", LinkedAccountRejectedError),
        (503, "BANK_UNAVAILABLE", BankUnavailableError),
    ],
)
def test_error_codes_raise_typed_errors(status, code, exc):
    with pytest.raises(exc):
        _handle(status, {"error_code": code, "kind": "state", "message": "m"})


def test_bank_unavailable_is_a_server_error():
    assert issubclass(BankUnavailableError, ServerError)
