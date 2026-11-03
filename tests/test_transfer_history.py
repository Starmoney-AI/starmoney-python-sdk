"""accounts.get_transfer_history: the merged in + out list (B-59)."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from starmoney import TransferHistoryPage, TransferHistoryRow
from starmoney.resources.accounts import AccountsResource


def _resource(body: dict) -> tuple[AccountsResource, AsyncMock]:
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = body
    http.get = AsyncMock(return_value=resp)
    return AccountsResource(http), http.get


@pytest.mark.asyncio
async def test_defaults_keep_the_old_call_shape():
    res, get = _resource(
        {"user_id": "u", "transfers": [], "limit": 20, "offset": 0, "next_cursor": None}
    )
    page = await res.get_transfer_history("u")
    get.assert_awaited_once_with(
        "/accounts/transfers", params={"limit": 20, "offset": 0}, user_id="u"
    )
    assert page["next_cursor"] is None


@pytest.mark.asyncio
async def test_cursor_and_date_range_are_sent_as_the_wire_names():
    res, get = _resource(
        {"user_id": "u", "transfers": [], "limit": 5, "offset": 0, "next_cursor": None}
    )
    await res.get_transfer_history(
        "u", limit=5, cursor="abc", from_date=date(2026, 10, 1), to_date="2026-10-31"
    )
    assert get.await_args.kwargs["params"] == {
        "limit": 5,
        "offset": 0,
        "cursor": "abc",
        "from": "2026-10-01",
        "to": "2026-10-31",
    }


@pytest.mark.asyncio
async def test_both_directions_come_back_as_returned():
    in_row: TransferHistoryRow = {
        "id": "e1",
        "direction": "in",
        "amount_minor": 5000,
        "currency": "XOF",
        "status": "completed",
        "date": "2026-11-02T09:30:00+00:00",
        "account_reference": "SN08K00100152000025690007542",
        "account_label": "Compte StarMoney",
        "counterparty_name": "Awa",
        "counterparty_iban": None,
        "motif": "SM-7KQ4X-9TDB2 loyer",
        "sm_reference": "SM-7KQ4X-9TDB2",
        "customer_reference": "SM-7KQ4X-9TDB2",
    }
    body: TransferHistoryPage = {
        "user_id": "u",
        "transfers": [in_row],
        "limit": 20,
        "offset": 0,
        "next_cursor": "next",
    }
    res, _ = _resource(body)
    page = await res.get_transfer_history("u")
    assert page["transfers"][0]["direction"] == "in"
    assert page["next_cursor"] == "next"
    assert "balance" not in page["transfers"][0]
