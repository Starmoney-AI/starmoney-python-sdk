"""vIBAN balance read (accounts.get_balance), its typed errors, and AccountState."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney import AccountState
from starmoney.exceptions import (
    AccountNotPayableError,
    LedgerUnavailableError,
    NoVibanAccountError,
    ServerError,
)
from starmoney.http_client import HTTPClient
from starmoney.resources.accounts import AccountsResource


def _handle(status: int, body: dict) -> None:
    response = httpx.Response(
        status, json=body, request=httpx.Request("GET", "http://x/v1/accounts/balance")
    )
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


@pytest.mark.asyncio
async def test_get_balance_calls_the_user_scoped_path_and_returns_whole_francs():
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "available_minor": 3_000,
        "reserved_minor": 2_000,
        "balance_minor": 5_000,
        "currency": "XOF",
        "as_of": "2026-09-27T10:00:00+00:00",
    }
    http.get = AsyncMock(return_value=resp)

    result = await AccountsResource(http).get_balance("user-1")

    http.get.assert_called_once_with("/accounts/balance", user_id="user-1")
    assert result["balance_minor"] == 5_000


@pytest.mark.parametrize(
    "status, code, exc_type",
    [
        (404, "NO_VIBAN_ACCOUNT", NoVibanAccountError),
        (409, "ACCOUNT_NOT_PAYABLE", AccountNotPayableError),
        (503, "LEDGER_UNAVAILABLE", LedgerUnavailableError),
    ],
)
def test_balance_errors_are_typed(status, code, exc_type):
    with pytest.raises(exc_type) as err:
        _handle(status, {"error_code": code, "detail": "x"})
    assert err.value.status_code == status


def test_ledger_unavailable_is_still_a_server_error():
    assert issubclass(LedgerUnavailableError, ServerError)


def test_account_state_is_the_closed_server_set():
    assert [s.value for s in AccountState] == [
        "captured", "active_pre_kyc", "kyc_pending", "verified", "closed",
    ]
    assert AccountState("kyc_pending").has_viban
    assert not AccountState.CAPTURED.has_viban
    assert not AccountState.CLOSED.has_viban
