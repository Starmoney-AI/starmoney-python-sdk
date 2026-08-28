"""StarMoney SDK - Webhooks Resource"""

from typing import Any, Optional
from ..http_client import HTTPClient


class WebhooksResource:
    """
    Webhooks resource for managing event subscriptions.

    Handles:
    - Creating webhook subscriptions
    - Batch subscribing to multiple events
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def batch_subscribe(
        self,
        endpoint_url: str,
        webhook_secret: str,
        event_subscriptions: list[dict[str, Any]],
        retry_attempts: int = 3,
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        """
        Subscribe to multiple webhook events in one request.

        Args:
            endpoint_url: URL where webhooks will be delivered
            webhook_secret: Secret for HMAC signature validation
            event_subscriptions: List of event subscriptions
            retry_attempts: Number of retry attempts for failed deliveries
            timeout_seconds: Webhook delivery timeout

        Returns:
            Subscription confirmation data

        Example:
            ```python
            from starmoney.webhooks import WebhookEvent

            result = await client.webhooks.batch_subscribe(
                endpoint_url="https://yourapp.com/webhooks",
                webhook_secret="your-webhook-secret",
                event_subscriptions=[
                    {"event_type": WebhookEvent.PAYMENT_INITIATED, "subscribed_users": None},
                    {"event_type": WebhookEvent.PAYMENT_COMPLETED, "subscribed_users": None},
                    {"event_type": WebhookEvent.PAYMENT_FAILED, "subscribed_users": None},
                    # New (PR #101): "money is waiting for a recipient who has no
                    # account yet" / "you received money".
                    {"event_type": WebhookEvent.DEFERRED_TRANSFER_SENT, "subscribed_users": None},
                    {"event_type": WebhookEvent.PAYMENT_RECEIVED, "subscribed_users": None},
                ],
                retry_attempts=3,
                timeout_seconds=10
            )

            print(f"Subscribed to {result['total_created']} events")
            ```
        """
        payload = {
            "endpoint_url": endpoint_url,
            "webhook_secret": webhook_secret,
            "event_subscriptions": event_subscriptions,
            "retry_attempts": retry_attempts,
            "timeout_seconds": timeout_seconds,
        }

        response = await self.http.post("/webhook-subscriptions/batch", json=payload)
        return response.json()

    async def create_subscription(
        self,
        endpoint_url: str,
        webhook_secret: str,
        event_type: str,
        subscribed_users: Optional[list[str]] = None,
        retry_attempts: int = 3,
        timeout_seconds: int = 10,
    ) -> dict[str, Any]:
        """
        Subscribe to a single webhook event.

        Args:
            endpoint_url: URL where webhooks will be delivered
            webhook_secret: Secret for HMAC signature validation
            event_type: Event type to subscribe to — use a
                ``starmoney.webhooks.WebhookEvent`` constant (e.g.
                ``WebhookEvent.PAYMENT_COMPLETED``) instead of a raw string to
                avoid typos; a plain string like ``'payment.completed'`` also
                works since ``WebhookEvent`` members ARE strings.
            subscribed_users: Optional list of user IDs to filter events
            retry_attempts: Number of retry attempts for failed deliveries
            timeout_seconds: Webhook delivery timeout

        Returns:
            Subscription data

        Example:
            ```python
            from starmoney.webhooks import WebhookEvent

            # "money is waiting for a recipient who has no account yet" (PR #101)
            await client.webhooks.create_subscription(
                endpoint_url="https://yourapp.com/webhooks",
                webhook_secret="your-webhook-secret",
                event_type=WebhookEvent.DEFERRED_TRANSFER_SENT,
            )

            # "you received money" (PR #101)
            await client.webhooks.create_subscription(
                endpoint_url="https://yourapp.com/webhooks",
                webhook_secret="your-webhook-secret",
                event_type=WebhookEvent.PAYMENT_RECEIVED,
            )
            ```
        """
        payload = {
            "endpoint_url": endpoint_url,
            "webhook_secret": webhook_secret,
            "event_type": event_type,
            "subscribed_users": subscribed_users,
            "retry_attempts": retry_attempts,
            "timeout_seconds": timeout_seconds,
        }

        response = await self.http.post("/webhook-subscriptions", json=payload)
        return response.json()

    async def update_subscription(
        self,
        subscription_id: str,
        endpoint_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        is_active: Optional[bool] = None,
        event_types: Optional[list[str]] = None,
        user_filters: Optional[list[str]] = None,
        retry_attempts: Optional[int] = None,
        retry_delay_seconds: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Update an existing webhook subscription.

        Only the provided (non-None) fields will be sent in the update request.

        Args:
            subscription_id: ID of the subscription to update
            endpoint_url: New endpoint URL
            webhook_secret: New webhook secret
            is_active: Enable/disable subscription
            event_types: List of event types for the subscription
            user_filters: List of user ids to filter events
            retry_attempts: Max retry attempts
            retry_delay_seconds: Retry delay in seconds
            timeout_seconds: Delivery timeout in seconds

        Returns:
            Updated subscription data as returned by the API
        """
        payload: dict[str, Any] = {}
        if endpoint_url is not None:
            payload["endpoint_url"] = endpoint_url
        if webhook_secret is not None:
            payload["webhook_secret"] = webhook_secret
        if is_active is not None:
            payload["is_active"] = is_active
        if event_types is not None:
            payload["event_types"] = event_types
        if user_filters is not None:
            payload["user_filters"] = user_filters
        if retry_attempts is not None:
            payload["retry_attempts"] = retry_attempts
        if retry_delay_seconds is not None:
            payload["retry_delay_seconds"] = retry_delay_seconds
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds

        response = await self.http.put(f"/webhook-subscriptions/{subscription_id}", json=payload)
        return response.json()

    async def list_subscriptions(self, active_only: bool = True) -> dict[str, Any]:
        """
        List webhook subscriptions for the calling service.

        Args:
            active_only: if True, return only active subscriptions (default True)

        Returns:
            Parsed JSON response from the API. Typically a dict with keys
            `subscriptions` (list) and `total_count`, but some implementations
            may return a raw list — callers should handle both shapes.
        """
        params = {"active_only": str(active_only).lower()} if active_only is not None else {}
        response = await self.http.get("/webhook-subscriptions", params=params)
        return response.json()
