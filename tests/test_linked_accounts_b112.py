"""B-112 (service 0.3.51): several named linked accounts; the customer picks which pays.

Awa linked BDK «Salaire» (SN……0101, the default) then «Épargne» (SN……0202).
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney import (LinkIdRequiredError, LinkInUseError, LinkLimitReachedError,
                       LinkNotFoundError)
from starmoney.http_client import HTTPClient
from starmoney.resources.accounts import AccountsResource
from starmoney.resources.payments import PaymentsResource

EPARGNE = "22222222-2222-4222-8222-222222222222"


def _raised(status: int, body: dict):
    response = httpx.Response(
        status, json=body, request=httpx.Request("POST", "http://x/v1/accounts/rails/bdk")
    )
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


@pytest.mark.parametrize(
    "status, body, exc_cls, attr, value",
    [
        (409, {"error_code": "LINK_LIMIT_REACHED", "kind": "state", "limit": 5},
         LinkLimitReachedError, "limit", 5),
        (404, {"error_code": "LINK_NOT_FOUND", "kind": "not_found", "link_id": EPARGNE},
         LinkNotFoundError, "link_id", EPARGNE),
        (409, {"error_code": "LINK_ID_REQUIRED", "kind": "state", "rail_name": "bdk"},
         LinkIdRequiredError, "rail_name", "bdk"),
        (409, {"error_code": "LINK_IN_USE", "kind": "state", "link_id": EPARGNE,
               "deferred_transfer_ids": ["dt-2"]},
         LinkInUseError, "deferred_transfer_ids", ["dt-2"]),
    ],
)
def test_link_errors_map_to_their_typed_errors(status, body, exc_cls, attr, value):
    with pytest.raises(exc_cls) as exc_info:
        _raised(status, {**body, "message": "m"})
    assert exc_info.value.status_code == status
    assert exc_info.value.error_code == body["error_code"]
    assert getattr(exc_info.value, attr) == value


def _http(method: str, payload: dict):
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = payload
    setattr(http, method, AsyncMock(return_value=resp))
    return http


@pytest.mark.asyncio
async def test_link_rail_sends_the_nickname_only_when_given():
    http = _http("post", {"status": "linked"})
    accounts = AccountsResource(http)

    await accounts.link_rail("u1", "bdk", account_reference="SN29…0202", nickname="Épargne")
    assert http.post.await_args.kwargs["json"] == {
        "account_reference": "SN29…0202",
        "nickname": "Épargne",
    }

    await accounts.link_rail("u1", "bdk", account_reference="SN29…0202")
    assert http.post.await_args.kwargs["json"] == {"account_reference": "SN29…0202"}


@pytest.mark.asyncio
async def test_links_rename_and_unlink_call_the_per_link_routes():
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {}
    http.get = AsyncMock(return_value=resp)
    http.patch = AsyncMock(return_value=resp)
    http.delete = AsyncMock(return_value=resp)
    accounts = AccountsResource(http)

    await accounts.links("u1")
    assert http.get.await_args.args == ("/accounts/links",)

    await accounts.rename_link("u1", EPARGNE, None)
    assert http.patch.await_args.args == (f"/accounts/links/{EPARGNE}",)
    assert http.patch.await_args.kwargs["json"] == {"nickname": None}

    await accounts.unlink_link("u1", EPARGNE)
    assert http.delete.await_args.args == (f"/accounts/links/{EPARGNE}",)


@pytest.mark.asyncio
async def test_the_linked_balance_names_a_link_only_when_asked():
    http = _http("get", {"available_minor": 200_000})
    accounts = AccountsResource(http)

    await accounts.get_linked_balance("u1", link_id=EPARGNE)
    assert http.get.await_args.kwargs["params"] == {"link_id": EPARGNE}

    await accounts.get_linked_balance("u1")
    assert "params" not in http.get.await_args.kwargs


@pytest.mark.asyncio
async def test_a_quote_carries_the_picked_link():
    http = _http("post", {"funding_link_id": EPARGNE})
    payments = PaymentsResource(http)

    await payments.quote(
        "u1", beneficiary_type="iban", beneficiary_value="SN…", amount_minor=50_000,
        funding_link_id=EPARGNE,
    )
    assert http.post.await_args.kwargs["json"]["funding_link_id"] == EPARGNE

    await payments.quote("u1", beneficiary_type="iban", beneficiary_value="SN…", amount_minor=1)
    assert "funding_link_id" not in http.post.await_args.kwargs["json"]
