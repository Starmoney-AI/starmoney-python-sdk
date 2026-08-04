"""SDK unit tests — DeferredTransfersResource."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from starmoney.resources.deferred_transfers import DeferredTransfersResource


def _make_resource():
    http = MagicMock()
    return DeferredTransfersResource(http), http


_DT_RESPONSE = {
    "id": "dt-uuid-1",
    "client_transaction_id": "ctxn-1",
    "sender_user_id": "user-1",
    "recipient_handle": "+221770000001",
    "amount_minor": 5000,
    "currency": "XOF",
    "branch": "hold_backed",
    "status": "reserved",
    "expires_at": "2026-06-21T10:00:00Z",
    "created_at": "2026-06-21T09:00:00Z",
    "updated_at": "2026-06-21T09:00:00Z",
}


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_branch_a_body():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _DT_RESPONSE
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.send(
        client_transaction_id="ctxn-1",
        recipient_handle="+221770000001",
        amount_minor=5000,
        currency="XOF",
        funding_source="viban_hold",
    )

    http.post.assert_called_once_with(
        "/deferred-transfers/send",
        json={
            "client_transaction_id": "ctxn-1",
            "recipient_handle": "+221770000001",
            "amount_minor": 5000,
            "currency": "XOF",
            "funding_source": "viban_hold",
        },
    )
    assert result["status"] == "reserved"
    assert result["branch"] == "hold_backed"


@pytest.mark.asyncio
async def test_send_branch_b_includes_linked_account():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {**_DT_RESPONSE, "branch": "deferred_pull", "status": "armed"}
    http.post = AsyncMock(return_value=mock_resp)

    await resource.send(
        client_transaction_id="ctxn-2",
        recipient_handle="+221770000002",
        amount_minor=10000,
        funding_source="external_pull",
        linked_external_account_id="ext-acct-1",
    )

    called_json = http.post.call_args.kwargs["json"]
    assert called_json["funding_source"] == "external_pull"
    assert called_json["linked_external_account_id"] == "ext-acct-1"


@pytest.mark.asyncio
async def test_send_defaults():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _DT_RESPONSE
    http.post = AsyncMock(return_value=mock_resp)

    await resource.send(
        client_transaction_id="ctxn-3",
        recipient_handle="+221770000003",
        amount_minor=1000,
    )

    called_json = http.post.call_args.kwargs["json"]
    # defaults
    assert called_json["currency"] == "XOF"
    assert called_json["funding_source"] == "viban_hold"
    assert "linked_external_account_id" not in called_json


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_calls_correct_path():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _DT_RESPONSE
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.get("dt-uuid-1")

    http.get.assert_called_once_with("/deferred-transfers/dt-uuid-1")
    assert result["id"] == "dt-uuid-1"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


_LIST_RESPONSE = {
    "user_id": "user-1",
    "limit": 20,
    "offset": 0,
    "deferred_transfers": [
        {
            "deferred_transfer_id": "dt-uuid-1",
            "recipient_handle": "+2217xxxxxx01",
            "amount_minor": 5000,
            "currency": "XOF",
            "status": "reserved",
            "created_at": "2026-08-04T09:00:00Z",
            "expires_at": "2026-08-11T09:00:00Z",
        }
    ],
}


@pytest.mark.asyncio
async def test_list_default_params_and_user_scoped():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _LIST_RESPONSE
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.list(user_id="user-1")

    http.get.assert_called_once_with(
        "/deferred-transfers",
        user_id="user-1",
        params={"limit": 20, "offset": 0},
    )
    # No status param unless supplied (API defaults to the cancellable set).
    assert "status" not in http.get.call_args.kwargs["params"]
    assert result["deferred_transfers"][0]["deferred_transfer_id"] == "dt-uuid-1"
    # Handle is masked in the response the SDK returns to the caller.
    assert "x" in result["deferred_transfers"][0]["recipient_handle"]


@pytest.mark.asyncio
async def test_list_forwards_status_filter_and_pagination():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _LIST_RESPONSE
    http.get = AsyncMock(return_value=mock_resp)

    await resource.list(
        user_id="user-1",
        status="reserved,armed",
        limit=50,
        offset=100,
    )

    http.get.assert_called_once_with(
        "/deferred-transfers",
        user_id="user-1",
        params={"limit": 50, "offset": 100, "status": "reserved,armed"},
    )


# ---------------------------------------------------------------------------
# claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_sends_correct_body():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {**_DT_RESPONSE, "status": "settled"}
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.claim(
        deferred_transfer_id="dt-uuid-1",
        viban_tenant_slug="solarbox",
        holder_name="Fatou Ndiaye",
        recipient_user_id="user-2",
    )

    http.post.assert_called_once_with(
        "/deferred-transfers/dt-uuid-1/claim",
        json={
            "holder_name": "Fatou Ndiaye",
            "viban_tenant_slug": "solarbox",
            "recipient_user_id": "user-2",
        },
    )
    assert result["status"] == "settled"


@pytest.mark.asyncio
async def test_claim_omits_recipient_user_id_when_none():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _DT_RESPONSE
    http.post = AsyncMock(return_value=mock_resp)

    await resource.claim(
        deferred_transfer_id="dt-uuid-1",
        viban_tenant_slug="solarbox",
        holder_name="Fatou",
    )

    called_json = http.post.call_args.kwargs["json"]
    assert "recipient_user_id" not in called_json


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_calls_correct_path_with_user_id():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {**_DT_RESPONSE, "status": "cancelled"}
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.cancel(
        deferred_transfer_id="dt-uuid-1",
        user_id="user-1",
    )

    http.post.assert_called_once_with(
        "/deferred-transfers/dt-uuid-1/cancel",
        user_id="user-1",
    )
    assert result["status"] == "cancelled"
