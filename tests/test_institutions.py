"""B-101: the institution catalogue on the rails listing and INSTITUTION_ALREADY_LINKED."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney import InstitutionAlreadyLinkedError
from starmoney.http_client import HTTPClient
from starmoney.resources.accounts import AccountsResource


def test_institution_already_linked_maps_to_its_typed_error():
    """Fatou links BDK ··0013 while ··0090 is linked → 409, typed error with the masked IBAN."""
    body = {
        "error_code": "INSTITUTION_ALREADY_LINKED",
        "kind": "state",
        "message": "An account is already linked on bdk",
        "rail_name": "bdk",
        "institution_code": "bdk",
        "linked_account_reference_masked": "SN……0090",
    }
    response = httpx.Response(
        409, json=body, request=httpx.Request("POST", "http://x/v1/accounts/rails/bdk")
    )
    with pytest.raises(InstitutionAlreadyLinkedError) as exc_info:
        HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)

    err = exc_info.value
    assert err.status_code == 409
    assert err.error_code == "INSTITUTION_ALREADY_LINKED"
    assert err.kind == "state"
    assert err.institution_code == "bdk"
    assert err.linked_account_reference_masked == "SN……0090"


@pytest.mark.asyncio
async def test_listing_returns_institutions_and_new_row_fields_unchanged():
    """The SDK hands back the listing as the bank sent it, institutions included."""
    payload = {
        "user_id": "u1",
        "available_rails": [
            {
                "rail_name": "bdk",
                "institution_code": "bdk",
                "linked_at": "2026-11-12T09:30:00",
                "has_credentials": True,
            }
        ],
        "institutions": [
            {
                "code": "bdk",
                "display_name": "BDK",
                "country": "SN",
                "status": "available",
                "link_method": "phone_iban_registry",
            }
        ],
    }
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = payload
    http.get = AsyncMock(return_value=resp)

    result = await AccountsResource(http).get_user_available_rails("u1")

    assert result["institutions"][0]["code"] == "bdk"
    assert result["available_rails"][0]["linked_at"] == "2026-11-12T09:30:00"
