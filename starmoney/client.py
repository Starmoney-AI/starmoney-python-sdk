"""
StarMoney Python SDK - Main Client

Official async Python client for StarMoney Bank API.
"""

from typing import Optional

from .auth import AuthManager
from .http_client import HTTPClient
from .resources.accounts import AccountsResource
from .resources.beneficiaries import BeneficiariesResource
from .resources.deferred_transfers import DeferredTransfersResource
from .resources.payments import PaymentsResource
from .resources.webhooks import WebhooksResource
from .up3.resource import UP3Resource


class StarmoneyClient:
    """
    StarMoney API Client - Ultra-light async implementation.

    Provides access to:
    - Accounts: Create accounts, provision vIBAN, submit KYC, manage profile
    - Beneficiaries: Full CRUD for payment beneficiaries
    - Payments: Send payments (with optional UP3 mandate chain), check status
    - DeferredTransfers: Send/get/claim/cancel deferred transfers (flow 01)
    - Webhooks: Subscribe to payment events
    - UP3: Build + verify UP3 mandate envelopes (requires up3_secret)

    Example:
        ```python
        from starmoney import StarmoneyClient

        async def main():
            async with StarmoneyClient(
                jwt_secret="your-jwt-secret",
                issuer="your-service-name",
                base_url="https://api.starmoney.com/v1"
            ) as client:
                # Open a StarMoney account — the home vIBAN is provisioned
                # inline by create (not a separate consumer call).
                account = await client.accounts.create(
                    first_name="John",
                    last_name="Doe",
                    email="john@example.com",
                    phone_number="+221771234567",
                    document_type="PASSPORT",
                    document_number="AB123456",
                    address="123 Main St",
                    viban_tenant_slug="solarbox",
                )
                user_id = account["user_id"]
                if account["account_state"] == "active_pre_kyc":
                    viban = account["account_reference"]

                # Send payment with UP3 mandates
                result = await client.payments.send_with_mandates(
                    user_id=user_id,
                    amount_minor=5000,
                    currency="XOF",
                    beneficiary_iban="SN12K00100152000025690000754",
                    beneficiary_name="Fatou Ndiaye",
                    description="send 5000 XOF to Fatou",
                    user_ref="whatsapp:+221771234567",
                    # rail selected server-side (ADR-001) — no rail_name needed.
                )
        ```
    """

    def __init__(
        self,
        jwt_secret: str,
        issuer: str = "starmoney-sdk",
        base_url: str = "http://localhost:8000/starmoney/v1",
        timeout: int = 30,
        up3_secret: Optional[str] = None,
    ):
        """
        Initialize StarMoney API client.

        Args:
            jwt_secret: JWT secret key for authentication
                       (must match server configuration).
            issuer: Issuer identifier for JWT claims
                   (must be registered with StarMoney).
            base_url: Base URL for StarMoney API.
                     Default: http://localhost:8000/starmoney/v1 (local dev).
                     Production: https://api.starmoney.com/v1
            timeout: Request timeout in seconds (default: 30).
            up3_secret: HMAC secret for UP3 mandate signing. In v0.1 this may
                       be the same value as jwt_secret (see UP3 spec §10 FAQ).
                       When omitted, jwt_secret is used. Required for
                       payments.send_with_mandates() and client.up3.
        """
        self.jwt_secret = jwt_secret
        self.issuer = issuer
        self.base_url = base_url
        self.timeout = timeout

        # Resolve the UP3 signing secret: caller may supply a distinct value
        # in v0.1; falls back to the JWT secret per spec §10 FAQ.
        _up3_secret_bytes = (up3_secret or jwt_secret).encode("utf-8")

        # Initialize auth manager
        self._auth = AuthManager(jwt_secret=jwt_secret, issuer=issuer)

        # Initialize HTTP client
        self._http_client = HTTPClient(base_url=base_url, auth=self._auth, timeout=timeout)

        # Initialize UP3 resource (always present; signing is available immediately)
        self._up3_resource = UP3Resource(secret=_up3_secret_bytes, issuer=issuer)

        # Initialize resources (lazy — created on first access)
        self._accounts: Optional[AccountsResource] = None
        self._beneficiaries: Optional[BeneficiariesResource] = None
        self._payments: Optional[PaymentsResource] = None
        self._deferred_transfers: Optional[DeferredTransfersResource] = None
        self._webhooks: Optional[WebhooksResource] = None

    @property
    def accounts(self) -> AccountsResource:
        """Access accounts resource."""
        if self._accounts is None:
            self._accounts = AccountsResource(self._http_client)
        return self._accounts

    @property
    def beneficiaries(self) -> BeneficiariesResource:
        """Access beneficiaries resource."""
        if self._beneficiaries is None:
            self._beneficiaries = BeneficiariesResource(self._http_client)
        return self._beneficiaries

    @property
    def payments(self) -> PaymentsResource:
        """Access payments resource."""
        if self._payments is None:
            self._payments = PaymentsResource(self._http_client)
            # Wire UP3 resource so send_with_mandates works.
            self._payments._up3 = self._up3_resource
        return self._payments

    @property
    def deferred_transfers(self) -> DeferredTransfersResource:
        """Access deferred transfers resource (flow 01)."""
        if self._deferred_transfers is None:
            self._deferred_transfers = DeferredTransfersResource(self._http_client)
        return self._deferred_transfers

    @property
    def webhooks(self) -> WebhooksResource:
        """Access webhooks resource."""
        if self._webhooks is None:
            self._webhooks = WebhooksResource(self._http_client)
        return self._webhooks

    @property
    def up3(self) -> UP3Resource:
        """Access UP3 mandate-building and verification resource."""
        return self._up3_resource

    async def __aenter__(self) -> "StarmoneyClient":
        """Async context manager entry."""
        await self._http_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self._http_client.__aexit__(exc_type, exc_val, exc_tb)

    async def close(self) -> None:
        """Close the client and release resources."""
        await self._http_client.close()
