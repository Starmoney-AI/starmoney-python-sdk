"""Bank health (0.3.59): the deep check, one status per component.

``GET /health/deep`` is all-or-nothing: ``status`` is ``"up"`` only when every
component is up. The bank answers 200 when up and 503 when down with the same
body; ``deep()`` returns that body in both cases and never raises on 503.
Unauthenticated, cached 15 s by the bank. Contract: docs/HEALTH.md.
"""

from typing import Dict, Literal, Optional, TypedDict

import httpx

from ..http_client import HTTPClient

HealthStatus = Literal["up", "down"]
HealthErrorCode = Literal["timeout", "unreachable", "error", "stale", "not_configured"]
COMPONENTS = ("database", "cache", "viban_ledgers", "bdk", "worker")


class _ComponentRequired(TypedDict):
    status: HealthStatus
    latency_ms: Optional[float]


class ComponentHealth(_ComponentRequired, total=False):
    """``error_code`` is present only when ``status`` is ``"down"``."""

    error_code: HealthErrorCode


class DeepHealth(TypedDict):
    status: HealthStatus
    checked_at: str  # ISO 8601 UTC, e.g. "2026-11-21T17:00:00.123456Z"
    version: str
    environment: str
    # Keys: database, cache, viban_ledgers, bdk, worker.
    components: Dict[str, ComponentHealth]


class DeepHealthForced(DeepHealth, total=False):
    """Stage only: ``forced`` is ``True`` during an operator's forced-down drill."""

    forced: bool


def _root_url(base_url: str) -> str:
    """The health routes sit at the service root, not under ``/v1``."""
    base = base_url.rstrip("/")
    return base[: -len("/v1")] if base.endswith("/v1") else base


class HealthResource:
    """Bank health checks (no authentication)."""

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def deep(self) -> DeepHealthForced:
        """``GET /health/deep``: the body on 200 and on 503 alike.

        Raises ``httpx.HTTPError`` only when the bank cannot be reached or
        answers something other than 200/503 (treat that as the bank down).
        """
        response = await self.http._get_client().get(f"{_root_url(self.http.base_url)}/health/deep")
        if response.status_code not in (200, 503):
            raise httpx.HTTPStatusError(
                f"unexpected status {response.status_code} from /health/deep",
                request=response.request,
                response=response,
            )
        return response.json()
