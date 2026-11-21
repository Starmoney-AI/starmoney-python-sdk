"""Per-turn correlation id: starmoney.correlation_id + HTTPClient._add_headers."""

import asyncio
import uuid

import httpx
import pytest

import starmoney
from starmoney.auth import AuthManager
from starmoney.http_client import HTTPClient


def _client(seen: list[str]) -> HTTPClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["X-Correlation-ID"])
        return httpx.Response(200, json={})

    http = HTTPClient("http://x/v1", AuthManager(jwt_secret="s" * 32, issuer="svc"))
    http._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return http


@pytest.mark.asyncio
async def test_unset_mints_a_fresh_uuid4_per_request():
    seen: list[str] = []
    http = _client(seen)
    await http.get("/a")
    await http.get("/b")
    assert len(set(seen)) == 2
    for value in seen:
        assert str(uuid.UUID(value, version=4)) == value


@pytest.mark.asyncio
async def test_set_value_is_sent_on_every_call_in_the_block_then_cleared():
    seen: list[str] = []
    http = _client(seen)
    with starmoney.correlation_id("turn-123"):
        await http.get("/a")
        await http.post("/b", json={})
    await http.get("/c")
    assert seen[:2] == ["turn-123", "turn-123"]
    assert seen[2] != "turn-123"


@pytest.mark.asyncio
async def test_explicit_header_wins_over_context():
    seen: list[str] = []
    http = _client(seen)
    with starmoney.correlation_id("turn-123"):
        await http.get("/a", headers={"X-Correlation-ID": "explicit-1"})
        await http.get("/b", headers={"x-correlation-id": "explicit-2"})
    assert seen == ["explicit-1", "explicit-2"]


@pytest.mark.asyncio
async def test_nesting_inner_wins_and_outer_is_restored():
    seen: list[str] = []
    http = _client(seen)
    with starmoney.correlation_id("outer"):
        await http.get("/1")
        with starmoney.correlation_id("inner"):
            await http.get("/2")
        await http.get("/3")
    assert seen == ["outer", "inner", "outer"]


@pytest.mark.asyncio
async def test_concurrent_tasks_never_mix_ids():
    seen: dict[str, list[str]] = {"a": [], "b": []}
    clients = {k: _client(seen[k]) for k in seen}

    async def turn(name: str) -> None:
        with starmoney.correlation_id(f"turn-{name}"):
            for _ in range(3):
                await clients[name].get("/x")
                await asyncio.sleep(0)

    await asyncio.gather(turn("a"), turn("b"))
    assert seen["a"] == ["turn-a"] * 3
    assert seen["b"] == ["turn-b"] * 3


@pytest.mark.parametrize("bad", ["", "x" * 129, "has space", "naïve", "a/b", "line\nbreak"])
def test_invalid_value_raises_value_error_without_echoing_it(bad):
    with pytest.raises(ValueError) as exc:
        with starmoney.correlation_id(bad):
            pass
    assert bad not in str(exc.value) or bad == ""


def test_boundary_value_and_allowed_characters_accepted():
    with starmoney.correlation_id("x" * 128):
        pass
    with starmoney.correlation_id("Az09._:-"):
        pass


def test_exported():
    assert "correlation_id" in starmoney.__all__
