"""
StarMoney Python SDK

Official async Python client for StarMoney Bank API.

Quick Start:
    ```python
    from starmoney import StarmoneyClient

    async with StarmoneyClient(
        jwt_secret="your-secret",
        issuer="your-service",
        up3_secret="your-up3-secret",  # same as jwt_secret in v0.1
    ) as client:
        # Open a StarMoney account (home vIBAN provisioned inline by create)
        account = await client.accounts.create(
            ..., viban_tenant_slug="solarbox",
        )
        if account["account_state"] == "active_pre_kyc":
            viban = account["account_reference"]

        # Send payment with UP3 mandate chain
        result = await client.payments.send_with_mandates(
            user_id=user_id,
            amount_minor=5000,
            currency="XOF",
            beneficiary_iban="SN12K00100152000025690000754",
            beneficiary_name="Fatou Ndiaye",
            description="send 5000 XOF to Fatou",
            rail_name="BDK",
            user_ref="whatsapp:+221771234567",
        )

        # Deferred transfer
        dt = await client.deferred_transfers.send(
            client_transaction_id="dt-abc-123",
            recipient_handle="+221770000000",
            amount_minor=10000,
        )
    ```

Webhook Validation:
    ```python
    from starmoney.webhooks import WebhookValidator

    validator = WebhookValidator(webhook_secret="your-secret")
    event = validator.parse_webhook(payload, signature)
    ```
"""

from .client import StarmoneyClient
from .exceptions import (
    APIError,
    AuthenticationError,
    DuplicateResourceError,
    InvalidSignatureError,
    PaymentNotFoundError,
    RateLimitError,
    ServerError,
    StarmoneyError,
    ValidationError,
    # UP3 typed exceptions
    UP3Error,
    UP3AmountExceedsIntent,
    UP3BeneficiaryDrift,
    UP3ChainBroken,
    UP3Expired,
    UP3KeyNotRegistered,
    UP3RailDrift,
    UP3Replay,
    UP3RevisionFieldDrift,
    UP3RevisionRegression,
    UP3SchemaInvalid,
    UP3SignatureInvalid,
    UP3StatusInvalid,
    UP3TypeNotAccepted,
)
from .webhooks.validator import WebhookValidator

__version__ = "0.1.6"
__all__ = [
    "StarmoneyClient",
    "WebhookValidator",
    # Base exceptions
    "StarmoneyError",
    "APIError",
    "AuthenticationError",
    "ValidationError",
    "PaymentNotFoundError",
    "DuplicateResourceError",
    "RateLimitError",
    "ServerError",
    "InvalidSignatureError",
    # UP3 exceptions
    "UP3Error",
    "UP3AmountExceedsIntent",
    "UP3BeneficiaryDrift",
    "UP3ChainBroken",
    "UP3Expired",
    "UP3KeyNotRegistered",
    "UP3RailDrift",
    "UP3Replay",
    "UP3RevisionFieldDrift",
    "UP3RevisionRegression",
    "UP3SchemaInvalid",
    "UP3SignatureInvalid",
    "UP3StatusInvalid",
    "UP3TypeNotAccepted",
]
