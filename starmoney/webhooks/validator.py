"""
StarMoney SDK - Webhook Signature Validator

CRITICAL SECURITY: Validates HMAC-SHA256 signatures on incoming webhooks.
Must match the server implementation exactly to prevent signature bypass.
"""

import hmac
import hashlib
import json
from typing import Any

from ..exceptions import InvalidSignatureError


class WebhookValidator:
    """
    Validates webhook signatures from StarMoney API.

    Uses HMAC-SHA256 signature verification to ensure webhooks
    are authentic and haven't been tampered with.
    """

    def __init__(self, webhook_secret: str):
        """
        Initialize webhook validator.

        Args:
            webhook_secret: Secret key shared with StarMoney for signature validation
                           (same secret used when creating webhook subscription)
        """
        self.webhook_secret = webhook_secret

    def verify_signature(self, payload: bytes, signature_header: str) -> bool:
        """
        Verify HMAC-SHA256 signature on webhook payload.

        IMPORTANT: This matches the server's canonical JSON implementation:
        - Signature computed from: json.dumps(payload, sort_keys=True, separators=(",", ":"))
        - HTTP body contains: exact same bytes used for signature

        Args:
            payload: Raw webhook payload bytes (from request.body)
            signature_header: Value of X-Webhook-Signature header (format: "sha256=<hex>")

        Returns:
            True if signature is valid, False otherwise

        Example:
            ```python
            # In your webhook handler (FastAPI)
            @app.post("/webhooks")
            async def handle_webhook(request: Request):
                payload = await request.body()
                signature = request.headers.get("X-Webhook-Signature")

                validator = WebhookValidator(webhook_secret="your-secret")
                if not validator.verify_signature(payload, signature):
                    raise HTTPException(status_code=401, detail="Invalid signature")

                # Process webhook...
            ```
        """
        # Fail closed: an empty or unset secret would accept any body HMAC'd with
        # the empty key (found by adita, 4 Nov). No secret, no valid signature.
        if not self.webhook_secret or not signature_header:
            return False

        # Compute expected signature using HMAC-SHA256
        expected_signature = hmac.new(
            self.webhook_secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()

        # Extract signature from header (remove "sha256=" prefix if present)
        received_signature = signature_header.replace("sha256=", "")

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(received_signature, expected_signature)

    def parse_webhook(self, payload: bytes, signature_header: str) -> dict[str, Any]:
        """
        Parse and validate webhook in one step.

        Args:
            payload: Raw webhook payload bytes
            signature_header: Value of X-Webhook-Signature header

        Returns:
            Parsed webhook data as dictionary

        Raises:
            InvalidSignatureError: If signature validation fails

        Example:
            ```python
            validator = WebhookValidator(webhook_secret="your-secret")

            try:
                event = validator.parse_webhook(payload, signature)
                print(f"Event type: {event['event_type']}")
                print(f"Transaction ID: {event['data']['transaction_id']}")
            except InvalidSignatureError:
                # Log security incident
                logger.error("Invalid webhook signature received")
                raise
            ```
        """
        if not self.verify_signature(payload, signature_header):
            raise InvalidSignatureError("Webhook signature validation failed")

        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def generate_test_signature(webhook_secret: str, payload: dict[str, Any]) -> str:
        """
        Generate signature for testing webhook handlers.

        Useful for unit tests where you want to simulate valid webhooks.

        Args:
            webhook_secret: Webhook secret
            payload: Webhook payload dictionary

        Returns:
            Signature header value (format: "sha256=<hex>")

        Example:
            ```python
            # In your tests
            payload = {"event_type": "payment.completed", ...}
            signature = WebhookValidator.generate_test_signature(
                webhook_secret="test-secret",
                payload=payload
            )

            # Make test request with signature
            response = client.post(
                "/webhooks",
                json=payload,
                headers={"X-Webhook-Signature": signature}
            )
            ```
        """
        # Match server's canonical JSON format exactly
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

        signature = hmac.new(
            webhook_secret.encode("utf-8"), payload_json, hashlib.sha256
        ).hexdigest()

        return f"sha256={signature}"
