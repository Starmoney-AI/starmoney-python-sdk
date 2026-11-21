"""client.health.deep(): returns the body on 200 and on 503 (0.3.59)."""

import httpx
import pytest

from starmoney import StarmoneyClient
from starmoney.resources.health import _root_url

DOWN_BODY = {
    "status": "down",
    "checked_at": "2026-11-21T17:00:00.000000Z",
    "version": "0.3.59",
    "environment": "staging",
    "components": {
        "database": {"status": "up", "latency_ms": 2.1},
        "cache": {"status": "up", "latency_ms": 0.8},
        "viban_ledgers": {"status": "up", "latency_ms": 9.0},
        "bdk": {"status": "down", "latency_ms": None, "error_code": "timeout"},
        "worker": {"status": "up", "latency_ms": 1.0},
    },
}


def _client(handler):
    client = StarmoneyClient(
        jwt_secret="x" * 32, issuer="adita", base_url="http://bank.test/v1"
    )
    client._http_client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [200, 503])
async def test_deep_returns_the_body_on_200_and_503(code):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(code, json=DOWN_BODY if code == 503 else {**DOWN_BODY, "status": "up"})

    body = await _client(handler).health.deep()
    assert seen["url"] == "http://bank.test/health/deep"
    assert seen["auth"] is None
    assert body["components"]["bdk"]["error_code"] == "timeout"
    assert body["status"] == ("down" if code == 503 else "up")


@pytest.mark.asyncio
async def test_deep_raises_on_anything_else():
    with pytest.raises(httpx.HTTPStatusError):
        await _client(lambda r: httpx.Response(502, text="bad gateway")).health.deep()


def test_root_url_strips_v1_only():
    assert _root_url("https://stage.starmoney.dabsi.io/v1/") == "https://stage.starmoney.dabsi.io"
    assert _root_url("http://localhost:8000") == "http://localhost:8000"
