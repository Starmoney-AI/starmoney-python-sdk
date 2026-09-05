"""SDK unit tests — BeneficiariesResource: full CRUD."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from starmoney.resources.beneficiaries import BeneficiariesResource


def _make_resource():
    http = MagicMock()
    return BeneficiariesResource(http), http


_BENE_RESPONSE = {
    "id": "bene-uuid-1",
    "name": "Fatou Ndiaye",
    "iban": "SN12K00100152000025690007542",
    "phone_number": None,
    "email": None,
    "bank_name": "BDK",
    "is_favorite": False,
    "is_active": True,
    "metadata": {},
    "created_at": "2026-06-01T10:00:00",
    "updated_at": None,
}


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_sends_required_fields():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _BENE_RESPONSE
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.create(
        user_id="user-1",
        name="Fatou Ndiaye",
        iban="SN12K00100152000025690007542",
    )

    called_json = http.post.call_args.kwargs["json"]
    assert called_json["name"] == "Fatou Ndiaye"
    assert called_json["iban"] == "SN12K00100152000025690007542"
    assert called_json["is_favorite"] is False
    assert result["id"] == "bene-uuid-1"


@pytest.mark.asyncio
async def test_create_includes_optional_fields():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _BENE_RESPONSE
    http.post = AsyncMock(return_value=mock_resp)

    await resource.create(
        user_id="user-1",
        name="Fatou Ndiaye",
        iban="SN12K00100152000025690007542",
        bank_name="BDK",
        phone_number="+221770000001",
        email="fatou@example.com",
        is_favorite=True,
        metadata={"note": "trusted"},
    )

    called_json = http.post.call_args.kwargs["json"]
    assert called_json["bank_name"] == "BDK"
    assert called_json["phone_number"] == "+221770000001"
    assert called_json["email"] == "fatou@example.com"
    assert called_json["is_favorite"] is True
    assert called_json["metadata"] == {"note": "trusted"}


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_passes_pagination_params():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "beneficiaries": [_BENE_RESPONSE],
        "total_count": 1,
        "page": 2,
        "page_size": 10,
        "has_next": False,
    }
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.list("user-1", page=2, page_size=10, include_inactive=True)

    params = http.get.call_args.kwargs["params"]
    assert params["page"] == 2
    assert params["page_size"] == 10
    assert params["include_inactive"] == "true"
    assert result["total_count"] == 1


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_calls_correct_path():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _BENE_RESPONSE
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.get("user-1", "bene-uuid-1")

    http.get.assert_called_once_with(
        "/beneficiaries/bene-uuid-1",
        user_id="user-1",
    )
    assert result["id"] == "bene-uuid-1"


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_only_sends_non_none_fields():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _BENE_RESPONSE
    http.put = AsyncMock(return_value=mock_resp)

    await resource.update("user-1", "bene-uuid-1", name="Nouveau Nom", is_favorite=True)

    called_json = http.put.call_args.kwargs["json"]
    assert called_json == {"name": "Nouveau Nom", "is_favorite": True}
    # iban not provided — must not appear
    assert "iban" not in called_json


@pytest.mark.asyncio
async def test_update_calls_put_endpoint():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _BENE_RESPONSE
    http.put = AsyncMock(return_value=mock_resp)

    await resource.update("user-1", "bene-uuid-1", bank_name="New Bank")

    http.put.assert_called_once()
    path = http.put.call_args.args[0]
    assert path == "/beneficiaries/bene-uuid-1"
    assert http.put.call_args.kwargs["user_id"] == "user-1"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_calls_delete_method():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"message": "Beneficiary deleted successfully"}
    http.delete = AsyncMock(return_value=mock_resp)

    result = await resource.delete("user-1", "bene-uuid-1")

    http.delete.assert_called_once_with(
        "/beneficiaries/bene-uuid-1",
        user_id="user-1",
    )
    assert result["message"] == "Beneficiary deleted successfully"


# ---------------------------------------------------------------------------
# toggle_favorite
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_favorite_uses_patch():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {**_BENE_RESPONSE, "is_favorite": True}
    http.request = AsyncMock(return_value=mock_resp)

    result = await resource.toggle_favorite("user-1", "bene-uuid-1", is_favorite=True)

    http.request.assert_called_once_with(
        "PATCH",
        "/beneficiaries/bene-uuid-1/favorite",
        json={"is_favorite": True},
        user_id="user-1",
    )
    assert result["is_favorite"] is True


# ---------------------------------------------------------------------------
# validate_iban
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_iban_sends_query_param():
    resource, http = _make_resource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "iban": "SN12K00100152000025690007542",
        "is_valid": True,
        "message": "IBAN format is valid",
    }
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.validate_iban("SN12K00100152000025690007542")

    http.get.assert_called_once_with(
        "/beneficiaries/validate/iban",
        params={"iban": "SN12K00100152000025690007542"},
    )
    assert result["is_valid"] is True


# ---------------------------------------------------------------------------
# IBAN validation: client-side fast-fail + server error-code mapping
# ---------------------------------------------------------------------------

from starmoney.auth import AuthManager
from starmoney.exceptions import DuplicateResourceError, InvalidIBANError
from starmoney.http_client import HTTPClient


class _FakeResponse:
    """Minimal stand-in for httpx.Response for _handle_error."""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def _client():
    return HTTPClient(
        base_url="http://test.local",
        auth=AuthManager("test-secret-at-least-32-characters-long!!"),
    )


@pytest.mark.asyncio
async def test_create_rejects_bad_checksum_client_side():
    """A well-formed but mod-97-invalid IBAN fails before any HTTP call."""
    resource, http = _make_resource()
    http.post = AsyncMock()

    # ...188 is one digit off from the valid ...189 — passes format, fails mod-97.
    with pytest.raises(InvalidIBANError):
        await resource.create(
            user_id="u1", name="Typo Payee", iban="FR7630006000011234567890188"
        )
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_create_rejects_malformed_iban_client_side():
    resource, http = _make_resource()
    http.post = AsyncMock()
    with pytest.raises(InvalidIBANError):
        await resource.create(user_id="u1", name="Bad", iban="NOT-AN-IBAN")
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_update_rejects_bad_iban_client_side():
    resource, http = _make_resource()
    http.put = AsyncMock()
    with pytest.raises(InvalidIBANError):
        await resource.update(
            user_id="u1", beneficiary_id="b1", iban="FR7630006000011234567890188"
        )
    http.put.assert_not_called()


def test_handle_error_maps_invalid_iban_error_code():
    """Server 422 with nested error_code INVALID_IBAN -> InvalidIBANError."""
    client = _client()
    resp = _FakeResponse(
        422,
        {"detail": {"message": "Invalid IBAN checksum (mod-97 failed)", "error_code": "INVALID_IBAN"}},
    )
    with pytest.raises(InvalidIBANError) as ei:
        client._handle_error(resp)
    # message is unwrapped from the nested detail object
    assert "mod-97" in str(ei.value)
    assert ei.value.status_code == 422


def test_handle_error_maps_duplicate_beneficiary_409():
    """Server 409 -> DuplicateResourceError, with the human message extracted."""
    client = _client()
    resp = _FakeResponse(
        409,
        {"detail": {"message": "Beneficiary with IBAN X already exists", "error_code": "DUPLICATE_BENEFICIARY"}},
    )
    with pytest.raises(DuplicateResourceError) as ei:
        client._handle_error(resp)
    assert "already exists" in str(ei.value)
