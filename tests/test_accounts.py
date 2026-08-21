"""SDK unit tests — AccountsResource: create (home-vIBAN merge), get_status,
submit_kyc, get/update profile."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from starmoney.resources.accounts import AccountsResource


def _make_resource():
    http = MagicMock()
    return AccountsResource(http), http


# ---------------------------------------------------------------------------
# create — opens the account AND provisions the home vIBAN inline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_forwards_tenant_and_returns_provisioned_state():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "user_id": "user-1",
        "account_state": "active_pre_kyc",
        "account_reference": "SN12K001",
        "message": "StarMoney account created and home vIBAN provisioned",
    }
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.create(
        first_name="Fatou",
        last_name="Ndiaye",
        email="fatou@example.com",
        phone_number="+221771234567",
        document_type="PASSPORT",
        document_number="AB123456",
        address="Dakar",
        viban_tenant_slug="solarbox",
    )

    http.post.assert_called_once()
    path = http.post.call_args.args[0]
    assert path == "/accounts"
    sent = http.post.call_args.kwargs["json"]
    # tenant slug is forwarded so the home vIBAN provisions in the right tenant
    assert sent["viban_tenant_slug"] == "solarbox"
    assert result["account_state"] == "active_pre_kyc"
    assert result["account_reference"] == "SN12K001"


@pytest.mark.asyncio
async def test_create_omits_tenant_when_not_provided():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"user_id": "user-2", "account_state": "captured"}
    http.post = AsyncMock(return_value=mock_resp)

    await resource.create(
        first_name="Awa",
        last_name="Sow",
        email="awa@example.com",
        phone_number="+221770000000",
        document_type="ID_CARD",
        document_number="CNI-1",
        address="Thiès",
    )

    sent = http.post.call_args.kwargs["json"]
    # no tenant → key absent (server resolves the sole configured tenant)
    assert "viban_tenant_slug" not in sent


# ---------------------------------------------------------------------------
# get_status — account-status enquiry (state, never balance)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_calls_correct_path_with_user_token():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "user_id": "user-1",
        "account_state": "active_pre_kyc",
        "is_provisioned": True,
        "kyc_verified": False,
        "kyc_required": True,
    }
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.get_status("user-1")

    http.get.assert_called_once_with("/accounts/status", user_id="user-1")
    assert result["account_state"] == "active_pre_kyc"
    assert result["kyc_required"] is True
    # positioning: status is state, never a balance
    assert "balance" not in result


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


@pytest.mark.asyncio
async def test_create_forwards_client_reference_when_provided():
    """ADR-004: client_reference is forwarded to the API so it can be echoed
    back on the account-lifecycle webhooks."""
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"user_id": "user-3", "account_state": "active_pre_kyc"}
    http.post = AsyncMock(return_value=mock_resp)

    await resource.create(
        first_name="Awa",
        last_name="Sow",
        email="awa@example.com",
        phone_number="+221770000000",
        document_type="ID_CARD",
        document_number="CNI-1",
        address="Thiès",
        client_reference="bot_557712",
    )

    sent = http.post.call_args.kwargs["json"]
    assert sent["client_reference"] == "bot_557712"


@pytest.mark.asyncio
async def test_create_omits_client_reference_when_not_provided():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"user_id": "user-4", "account_state": "captured"}
    http.post = AsyncMock(return_value=mock_resp)

    await resource.create(
        first_name="Awa",
        last_name="Sow",
        email="awa@example.com",
        phone_number="+221770000000",
        document_type="ID_CARD",
        document_number="CNI-1",
        address="Thiès",
    )

    sent = http.post.call_args.kwargs["json"]
    assert "client_reference" not in sent


# ---------------------------------------------------------------------------
# Version drift guard (adita report): __version__ must equal the packaged
# distribution version — never a separately-hardcoded string that can go stale.
# ---------------------------------------------------------------------------


def test_version_matches_distribution_metadata():
    from importlib.metadata import version as _pkg_version

    import starmoney

    assert starmoney.__version__ == _pkg_version("starmoney-python"), (
        "starmoney.__version__ drifted from the installed distribution version; "
        "it must derive from importlib.metadata, not a hardcoded dunder"
    )
    assert starmoney.__version__ != "0.0.0+source", (
        "package appears uninstalled in the test env; cannot validate version"
    )
