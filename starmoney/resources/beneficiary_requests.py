"""Beneficiary requests: a saved phone number whose holder has no StarMoney
account yet (B-27). Created through ``beneficiaries.create(phone=...)`` when
the server answers 202; this resource reads, cancels and marks the invite.
"""

from typing import Any

from starmoney.http_client import HTTPClient


class BeneficiaryRequestsResource:
    """Pending beneficiary requests (user-scoped: the saver's own rows)."""

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def get(self, user_id: str, request_id: str) -> dict[str, Any]:
        """
        Read one request.

        Returns:
            dict with status (pending | fulfilled | expired | cancelled), kind,
            beneficiary_request_id, name, phone_number, created_at, expires_at,
            client_reference, invited_at, beneficiary_id (once fulfilled).

        Raises:
            PaymentNotFoundError (404): not the caller's request.
        """
        response = await self.http.get(f"/beneficiary-requests/{request_id}", user_id=user_id)
        return response.json()

    async def cancel(self, user_id: str, request_id: str) -> dict[str, Any]:
        """
        Cancel a pending request (idempotent). No webhook fires.

        Returns:
            dict with beneficiary_request_id and status "cancelled".
        """
        response = await self.http.delete(f"/beneficiary-requests/{request_id}", user_id=user_id)
        return response.json()

    async def invite(self, user_id: str, request_id: str) -> dict[str, Any]:
        """
        Record that the saver chose to invite the number. The bank only stores
        ``invited_at``; the consumer sends the approved WhatsApp template from
        its own number, once. A second call returns the same ``invited_at``
        and nothing else happens.

        Returns:
            dict with invited_at.
        """
        response = await self.http.post(
            f"/beneficiary-requests/{request_id}/invite", user_id=user_id
        )
        return response.json()
