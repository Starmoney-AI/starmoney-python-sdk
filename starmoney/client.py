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


class StarmoneyClient:
    """
    StarMoney API Client - Ultra-light async implementation.

    Provides access to:
    - Accounts: Create accounts, link payment rails
    - Beneficiaries: Manage payment beneficiaries
    - Payments: Send payments, check status
    - Webhooks: Subscribe to payment events

    Example:
        ```python
        from starmoney import StarmoneyClient

        async def main():
            async with StarmoneyClient(
                jwt_secret="your-jwt-secret",
                issuer="your-service-name",
                base_url="https://api.starmoney.com/v1"
            ) as client:
                # Create account
                account = await client.accounts.create(
                    first_name="John",
                    last_name="Doe",
                    email="john@example.com",
                    phone_number="+1234567890",
                    document_type="PASSPORT",
                    document_number="AB123456",
                    address="123 Main St"
                )

                user_id = account["user_id"]

                # Link payment rail
                await client.accounts.link_rail(user_id, rail_name="BDK")

                # Send payment
                payment = await client.payments.send(
                    user_id=user_id,
                    amount=100.00,
                    currency="EUR",
                    beneficiary_iban="FR1420041010050500013M02606",
                    beneficiary_name="Jane Smith",
                    description="Test payment"
                )

                # Check status
                status = await client.payments.get_status(
                    user_id=user_id,
                    client_transaction_id=payment["client_transaction_id"]
                )

                print(f"Payment status: {status['status']}")
        ```
    """

    def __init__(
        self,
        jwt_secret: str,
        issuer: str = "starmoney-sdk",
        base_url: str = "http://localhost:8000/starmoney/v1",
        timeout: int = 30,
    ):
        """
        Initialize StarMoney API client.

        Args:
            jwt_secret: JWT secret key for authentication
                       (must match server configuration)
            issuer: Issuer identifier for JWT claims
                   (must be registered with StarMoney)
            base_url: Base URL for StarMoney API
                     Default: http://localhost:8000/starmoney/v1 (local dev)
                     Production: https://api.starmoney.com/v1
            timeout: Request timeout in seconds (default: 30)
        """
        self.jwt_secret = jwt_secret
        self.issuer = issuer
        self.base_url = base_url
        self.timeout = timeout

        # Initialize auth manager
        self._auth = AuthManager(jwt_secret=jwt_secret, issuer=issuer)

        # Initialize HTTP client
        self._http_client = HTTPClient(base_url=base_url, auth=self._auth, timeout=timeout)

        # Initialize resources
        self._accounts: Optional[AccountsResource] = None
        self._beneficiaries: Optional[BeneficiariesResource] = None
        self._deferred_transfers: Optional[DeferredTransfersResource] = None
        self._payments: Optional[PaymentsResource] = None
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
    def deferred_transfers(self) -> DeferredTransfersResource:
        """Access deferred-transfers resource (send-to-handle flows)."""
        if self._deferred_transfers is None:
            self._deferred_transfers = DeferredTransfersResource(self._http_client)
        return self._deferred_transfers

    @property
    def payments(self) -> PaymentsResource:
        """Access payments resource."""
        if self._payments is None:
            self._payments = PaymentsResource(self._http_client)
        return self._payments

    @property
    def webhooks(self) -> WebhooksResource:
        """Access webhooks resource."""
        if self._webhooks is None:
            self._webhooks = WebhooksResource(self._http_client)
        return self._webhooks

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
