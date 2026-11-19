"""Pre-KYC send limits surface: typed 403s, accounts.get_limits, payment IBAN fast-fail."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney.exceptions import (
    InvalidIBANError,
    PreKycCeilingExceededError,
    PreKycMonthlyCeilingExceededError,
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


def test_monthly_ceiling_refusal_is_typed_carries_resets_on_and_is_still_a_total_error():
    """B-114 (0.3.53): Moussa sent 150 000 F on 3 Nov; on 20 Nov a 60 000 F send is refused."""
    with pytest.raises(PreKycMonthlyCeilingExceededError) as err:
        _handle(
            _error(
                403,
                {
                    "error_code": "PRE_KYC_MONTHLY_CEILING_EXCEEDED",
                    "detail": "send 60000 exceeds the remaining pre-KYC send allowance 50000",
                    "ceiling_minor": 200000,
                    "consumed_minor": 150000,
                    "pending_minor": 0,
                    "remaining_minor": 50000,
                    "resets_on": "2026-12-01",
                },
            )
        )
    exc = err.value
    assert exc.status_code == 403
    assert (exc.ceiling_minor, exc.consumed_minor, exc.pending_minor, exc.remaining_minor) == (
        200000, 150000, 0, 50000,
    )
    assert exc.resets_on == "2026-12-01"
    # a handler written for the lifetime refusal still catches it
    assert isinstance(exc, PreKycTotalCeilingExceededError)


def test_monthly_ceiling_error_is_exported_from_the_package():
    import starmoney

    assert starmoney.PreKycMonthlyCeilingExceededError is PreKycMonthlyCeilingExceededError
    assert "PreKycMonthlyCeilingExceededError" in starmoney.__all__


def test_the_lifetime_refusal_has_no_resets_on_and_is_not_a_monthly_error():
    with pytest.raises(PreKycTotalCeilingExceededError) as err:
        _handle(_error(403, {"error_code": "PRE_KYC_TOTAL_CEILING_EXCEEDED", "detail": "x"}))
    assert not isinstance(err.value, PreKycMonthlyCeilingExceededError)


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
async def test_get_limits_passes_the_monthly_item_with_its_reset_day_through():
    http = MagicMock()
    item = {
        "kind": "pre_kyc_monthly_sends", "direction": "outbound", "period": "calendar_month",
        "ceiling_minor": 200000, "consumed_minor": 150000, "pending_minor": 0,
        "remaining_minor": 50000, "resets_on": "2026-12-01", "enforced": True,
    }
    http.get = AsyncMock(return_value=MagicMock(json=lambda: {"account_state": "active_pre_kyc", "limits": [item]}))
    assert await AccountsResource(http).get_limits("user-1") == [item]


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


def test_recipient_with_no_account_refusal_carries_the_published_cap():
    """B-118 (0.3.56): Awa sends 250 000 F to Sandrine, who has no account yet."""
    from starmoney import RecipientLimitReachedError

    with pytest.raises(RecipientLimitReachedError) as err:
        _handle(
            _error(
                403,
                {
                    "error_code": "RECIPIENT_LIMIT_REACHED",
                    "detail": "the recipient has no account yet: a new customer cannot receive "
                    "more than the limit until they open and verify their account",
                    "recipient_status": "no_account",
                    "ceiling_minor": 200000,
                    "currency": "XOF",
                    "lifts_on": "kyc_verified",
                },
            )
        )
    assert (err.value.recipient_status, err.value.ceiling_minor) == ("no_account", 200000)


def test_recipient_with_an_account_refusal_carries_no_figure():
    from starmoney import RecipientLimitReachedError

    with pytest.raises(RecipientLimitReachedError) as err:
        _handle(
            _error(
                403,
                {
                    "error_code": "RECIPIENT_LIMIT_REACHED",
                    "detail": "the recipient has reached the limit of their account",
                },
            )
        )
    assert (err.value.recipient_status, err.value.ceiling_minor) == (None, None)
