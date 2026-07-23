"""
StarMoney Python SDK - HTTP Client

Async HTTP client wrapper for StarMoney API with automatic authentication,
error handling, and correlation ID generation.
"""

import uuid
from typing import Any, Optional
import httpx

from .auth import AuthManager
from .exceptions import (
    AuthenticationError,
    ValidationError,
    PaymentNotFoundError,
    DuplicateResourceError,
    RateLimitError,
    ServerError,
    APIError,
    UP3_ERROR_CODE_MAP,
)


class HTTPClient:
    """
    Async HTTP client for StarMoney API.

    Handles:
    - Automatic JWT authentication
    - Correlation ID generation for tracing
    - Error response mapping to domain exceptions
    - Request/response logging
    """

    def __init__(
        self,
        base_url: str,
        auth: AuthManager,
        timeout: int = 30,
        follow_redirects: bool = True,
    ):
        """
        Initialize HTTP client.

        Args:
            base_url: Base URL for StarMoney API (e.g., 'http://localhost:8000/starmoney/v1')
            auth: Authentication manager for JWT tokens
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.timeout = timeout
        # Follow redirects by default so SDK consumers don't get 307 responses
        self.follow_redirects = follow_redirects
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "HTTPClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=self.follow_redirects
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=self.follow_redirects
            )
        return self._client

    def _add_headers(
        self, headers: Optional[dict[str, str]], user_id: Optional[str] = None
    ) -> dict[str, str]:
        """
        Add authentication and correlation ID headers.

        Args:
            headers: Existing headers (or None)
            user_id: Optional user ID for user-scoped auth

        Returns:
            Combined headers with auth and correlation ID
        """
        final_headers = headers.copy() if headers else {}

        # Add authentication
        auth_header = self.auth.get_auth_header(user_id)
        final_headers.update(auth_header)

        # Add correlation ID for request tracing
        if "X-Correlation-ID" not in final_headers:
            final_headers["X-Correlation-ID"] = str(uuid.uuid4())

        return final_headers

    def _handle_error(self, response: httpx.Response) -> None:
        """
        Map HTTP error responses to domain exceptions.

        Args:
            response: HTTP response object

        Raises:
            Appropriate APIError subclass based on status code
        """
        try:
            error_data = response.json()
            message = error_data.get("detail", response.text)
        except Exception:
            message = response.text or f"HTTP {response.status_code} error"
            error_data = {}

        # Check for UP3 error codes embedded in the detail string or error_code field.
        # The API returns UP3_* codes in either `detail` or an `error_code` field.
        up3_code = error_data.get("error_code") if isinstance(error_data, dict) else None
        if not up3_code and isinstance(message, str):
            # Scan the message for a UP3_* prefix (e.g. "UP3_SIG_INVALID: ...")
            for code in UP3_ERROR_CODE_MAP:
                if code in message:
                    up3_code = code
                    break
        if up3_code and up3_code in UP3_ERROR_CODE_MAP:
            exc_cls = UP3_ERROR_CODE_MAP[up3_code]
            raise exc_cls(message, error_data)

        # Map HTTP status codes to domain exceptions
        if response.status_code == 400:
            raise ValidationError(response.status_code, message, error_data)
        elif response.status_code == 401:
            raise AuthenticationError(response.status_code, message, error_data)
        elif response.status_code == 404:
            raise PaymentNotFoundError(response.status_code, message, error_data)
        elif response.status_code == 409:
            raise DuplicateResourceError(response.status_code, message, error_data)
        elif response.status_code == 410:
            # 410 Gone is the UP3_EXPIRED HTTP code
            raise APIError(response.status_code, message, error_data)
        elif response.status_code == 429:
            raise RateLimitError(response.status_code, message, error_data)
        elif response.status_code >= 500:
            raise ServerError(response.status_code, message, error_data)
        else:
            raise APIError(response.status_code, message, error_data)

    async def request(
        self,
        method: str,
        path: str,
        user_id: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make HTTP request to StarMoney API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., '/payments')
            user_id: Optional user ID for user-scoped authentication
            headers: Optional additional headers
            **kwargs: Additional arguments for httpx.request()

        Returns:
            HTTP response object

        Raises:
            APIError or subclass if request fails
        """
        client = self._get_client()
        url = f"{self.base_url}{path}"
        final_headers = self._add_headers(headers, user_id)

        response = await client.request(method, url, headers=final_headers, **kwargs)

        # Raise for error status codes
        if response.status_code >= 400:
            self._handle_error(response)

        return response

    async def get(self, path: str, user_id: Optional[str] = None, **kwargs: Any) -> httpx.Response:
        """Make GET request."""
        return await self.request("GET", path, user_id=user_id, **kwargs)

    async def post(
        self, path: str, user_id: Optional[str] = None, **kwargs: Any
    ) -> httpx.Response:
        """Make POST request."""
        return await self.request("POST", path, user_id=user_id, **kwargs)

    async def put(self, path: str, user_id: Optional[str] = None, **kwargs: Any) -> httpx.Response:
        """Make PUT request."""
        return await self.request("PUT", path, user_id=user_id, **kwargs)

    async def delete(
        self, path: str, user_id: Optional[str] = None, **kwargs: Any
    ) -> httpx.Response:
        """Make DELETE request."""
        return await self.request("DELETE", path, user_id=user_id, **kwargs)

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
