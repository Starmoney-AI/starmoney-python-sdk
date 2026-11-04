"""SDK unit tests — PaymentsResource.get_mandates (bank B-37) / abandon_cart (bank B-35)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from starmoney.exceptions import PaymentNotFoundError, UP3Replay
from starmoney.http_client import HTTPClient
from starmoney.resources.payments import PaymentsResource

CART_ID = "mnd_01J9XK5W7G8YZQ4N3M2K1P0R5U"


def _http(body: dict) -> MagicMock:
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = body
    http.get = AsyncMock(return_value=resp)
    http.post = AsyncMock(return_value=resp)
    return http


@pytest.mark.asyncio
async def test_get_mandates_reads_the_cart_path_user_scoped():
    body = {
        "cart_id": CART_ID,
        "status": "stored",
        "intent": {"id": "mnd_i"},
        "cart": {"id": CART_ID},
        "payment_mandates": [{"revision": 1}, {"revision": 2}],
        "money_status": {"status": "completed"},
    }
    http = _http(body)

    result = await PaymentsResource(http).get_mandates("user-1", CART_ID)

    http.get.assert_called_once_with(f"/mandates/{CART_ID}", user_id="user-1")
    assert result["status"] == "stored"
    assert [p["revision"] for p in result["payment_mandates"]] == [1, 2]


@pytest.mark.asyncio
async def test_abandon_cart_posts_to_the_abandon_path():
    http = _http({"cart_id": CART_ID, "status": "abandoned", "abandoned_at": "2026-11-04T12:05:31Z"})

    result = await PaymentsResource(http).abandon_cart("user-1", CART_ID)

    http.post.assert_called_once_with(f"/payments/{CART_ID}/abandon", user_id="user-1")
    assert result["status"] == "abandoned"


def _handle(status: int, body: dict) -> None:
    response = httpx.Response(status, json=body, request=httpx.Request("GET", "http://x/v1/mandates/x"))
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


def test_an_unknown_cart_404_is_payment_not_found():
    with pytest.raises(PaymentNotFoundError):
        _handle(404, {"error_code": "RESOURCE_NOT_FOUND", "message": f"cart {CART_ID} not found"})


def test_abandoning_a_stored_cart_is_a_typed_up3_replay():
    with pytest.raises(UP3Replay):
        _handle(409, {"detail": f"UP3_REPLAY: cart id {CART_ID!r} was already received by the bank"})
