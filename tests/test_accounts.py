"""SDK unit tests — AccountsResource: provision_viban, submit_kyc, get/update profile."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from starmoney.resources.accounts import AccountsResource


def _make_resource():
    http = MagicMock()
    return AccountsResource(http), http


# ---------------------------------------------------------------------------
# provision_viban
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_viban_sends_correct_body():
    resource, http = _make_resource()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "account_reference": "SN12K001",
        "upstream_account_id": "uuid-1",
        "account_state": "active_pre_kyc",
        "correlation_id": "corr-1",
    }
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.provision_viban(
        viban_tenant_slug="solarbox",
        currency="XOF",
        holder_name="Fatou Ndiaye",
    )

    http.post.assert_called_once_with(
        "/accounts/provision-viban",
        json={
            "viban_tenant_slug": "solarbox",
            "currency": "XOF",
            "holder_name": "Fatou Ndiaye",
        },
        user_id=None,
    )
    assert result["account_state"] == "active_pre_kyc"
    assert result["account_reference"] == "SN12K001"


@pytest.mark.asyncio
async def test_provision_viban_defaults():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"account_state": "active_pre_kyc"}
    http.post = AsyncMock(return_value=mock_resp)

    await resource.provision_viban(viban_tenant_slug="bdk", user_id="test-user")

    called_json = http.post.call_args.kwargs["json"]
    assert called_json["currency"] == "XOF"
    assert called_json["holder_name"] == "Customer"
    assert called_json["viban_tenant_slug"] == "bdk"


# ---------------------------------------------------------------------------
# submit_kyc
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_kyc_sends_correct_body():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "user_id": "user-1",
        "account_state": "kyc_pending",
        "message": "KYC attestation submitted; awaiting bank adjudication.",
    }
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.submit_kyc(
        user_id="user-1",
        attester="agent-007",
        document_refs={"passport_hash": "abc123"},
        idempotency_key="idem-1",
    )

    http.post.assert_called_once_with(
        "/accounts/user-1/kyc/submit",
        json={
            "attester": "agent-007",
            "document_refs": {"passport_hash": "abc123"},
            "idempotency_key": "idem-1",
        },
    )
    assert result["account_state"] == "kyc_pending"


@pytest.mark.asyncio
async def test_submit_kyc_includes_attested_at_when_provided():
    from datetime import datetime, timezone

    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"account_state": "kyc_pending"}
    http.post = AsyncMock(return_value=mock_resp)

    attested = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    await resource.submit_kyc(
        user_id="user-2",
        attester="agent-1",
        document_refs={"doc": "ref"},
        idempotency_key="key-2",
        attested_at=attested,
    )

    called_json = http.post.call_args.kwargs["json"]
    assert "attested_at" in called_json
    assert "2026-06-01" in called_json["attested_at"]


# ---------------------------------------------------------------------------
# get_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_profile_calls_correct_path():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"user_id": "user-1", "first_name": "Fatou"}
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.get_profile("user-1")

    http.get.assert_called_once_with("/accounts/profile", user_id="user-1")
    assert result["user_id"] == "user-1"


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_profile_only_sends_provided_fields():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"user_id": "user-1"}
    http.put = AsyncMock(return_value=mock_resp)

    await resource.update_profile("user-1", email="new@example.com", first_name="Jean")

    called_json = http.put.call_args.kwargs["json"]
    assert called_json == {"email": "new@example.com", "first_name": "Jean"}
    # phone_number not provided — must NOT appear
    assert "phone_number" not in called_json


@pytest.mark.asyncio
async def test_update_profile_calls_put_endpoint():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    http.put = AsyncMock(return_value=mock_resp)

    await resource.update_profile("user-1", address="123 Rue de Dakar")

    http.put.assert_called_once()
    path = http.put.call_args.args[0]
    assert path == "/accounts/profile"
    assert http.put.call_args.kwargs["user_id"] == "user-1"
