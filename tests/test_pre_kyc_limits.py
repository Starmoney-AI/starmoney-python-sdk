"""Pre-KYC send limits surface: typed 403s, accounts.get_limits, payment IBAN fast-fail."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney.exceptions import (
    InvalidIBANError,
    PreKycCeilingExceededError,
    PreKycTotalCeilingExceededError,
)
from starmoney.http_client import HTTPClient
from starmoney.resources.accounts import AccountsResource
from starmoney.resources.payments import PaymentsResource


def _error(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "http://x/v1/payments"))


def _handle(response: httpx.Response) -> None:
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


def test_total_ceiling_refusal_is_typed_and_carries_the_figures():
    with pytest.raises(PreKycTotalCeilingExceededError) as err:
        _handle(
            _error(
                403,
                {
                    "error_code": "PRE_KYC_TOTAL_CEILING_EXCEEDED",
                    "detail": "send 50000 exceeds the remaining pre-KYC send allowance 40000",
                    "ceiling_minor": 200000,
                    "consumed_minor": 100000,
                    "pending_minor": 60000,
                    "remaining_minor": 40000,
                },
            )
        )
    exc = err.value
    assert exc.status_code == 403
    assert (exc.ceiling_minor, exc.consumed_minor, exc.pending_minor, exc.remaining_minor) == (
        200000, 100000, 60000, 40000,
    )


def test_per_send_refusal_is_a_distinct_type():
    with pytest.raises(PreKycCeilingExceededError) as err:
        _handle(_error(403, {"error_code": "PRE_KYC_CEILING_EXCEEDED", "detail": "too much"}))
    assert not isinstance(err.value, PreKycTotalCeilingExceededError)


@pytest.mark.asyncio
async def test_get_limits_returns_the_status_limits_and_empty_when_verified():
    http = MagicMock()
    limits = [{"kind": "pre_kyc_total_sends", "remaining_minor": 40000}]
    http.get = AsyncMock(return_value=MagicMock(json=lambda: {"account_state": "kyc_pending", "limits": limits}))
    assert await AccountsResource(http).get_limits("user-1") == limits

    http.get = AsyncMock(return_value=MagicMock(json=lambda: {"account_state": "verified"}))
    assert await AccountsResource(http).get_limits("user-1") == []


@pytest.mark.asyncio
async def test_payment_to_a_mistyped_iban_fails_before_the_request():
    http = MagicMock()
    http.post = AsyncMock()
    with pytest.raises(InvalidIBANError):
        await PaymentsResource(http).send(
            user_id="user-1", amount="5000", currency="XOF",
            beneficiary_iban="SN12K00100152000025690007541",  # one digit off a valid IBAN
            beneficiary_name="Awa", description="test", rail_name=None,
            client_transaction_id="ctid-1",
        )
    http.post.assert_not_awaited()
