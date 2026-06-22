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
    "iban": "SN12K00100152000025690000754",
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
        iban="SN12K00100152000025690000754",
    )

    called_json = http.post.call_args.kwargs["json"]
    assert called_json["name"] == "Fatou Ndiaye"
    assert called_json["iban"] == "SN12K00100152000025690000754"
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
        iban="SN12K00100152000025690000754",
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
        "iban": "SN12K00100152000025690000754",
        "is_valid": True,
        "message": "IBAN format is valid",
    }
    http.get = AsyncMock(return_value=mock_resp)

    result = await resource.validate_iban("SN12K00100152000025690000754")

    http.get.assert_called_once_with(
        "/beneficiaries/validate/iban",
        params={"iban": "SN12K00100152000025690000754"},
    )
    assert result["is_valid"] is True
