"""StarMoney SDK - Payments Resource"""

import uuid
from decimal import Decimal
from typing import Any, Optional
from ..http_client import HTTPClient


class PaymentsResource:
    """
    Payments resource for sending and tracking payments.

    Handles:
    - Sending payments with automatic idempotency
    - Checking payment status
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def send(
        self,
        user_id: str,
        amount: Decimal | float | str,
        currency: str,
        beneficiary_iban: str,
        beneficiary_name: str,
        description: str,
        rail_name: str,
        client_transaction_id: str,
        metadata: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
        """
        Send a payment.

        Args:
            user_id: User ID sending the payment
            amount: Payment amount (Decimal, float, or string)
            currency: Currency code (e.g., 'EUR', 'USD')
            beneficiary_iban: Recipient's IBAN
            beneficiary_name: Recipient's name
            description: Payment description
            rail_name: Payment rail to use
            client_transaction_id: Idempotency key. If not provided,
                                   a UUID will be automatically generated.

        Returns:
            Payment data including transaction_id and client_transaction_id

        Example:
            ```python
            payment = await client.payments.send(
                user_id=user_id,
                amount=100.00,
                currency="EUR",
                beneficiary_iban="FR1420041010050500013M02606",
                beneficiary_name="John Doe",
                description="Test payment",
                rail_name="BDK",
                client_transaction_id="ID548714"
            )

            # Track this payment
            client_txn_id = payment["client_transaction_id"]
            ```
        """
        # Convert amount to string for API
        if isinstance(amount, Decimal):
            amount_str = str(amount)
        elif isinstance(amount, float):
            amount_str = f"{amount:.2f}"
        else:
            amount_str = str(amount)

        payload = {
            "amount": amount_str,
            "currency": currency,
            "beneficiary_iban": beneficiary_iban,
            "beneficiary_name": beneficiary_name,
            "description": description,
            "rail_name": rail_name,
            "client_transaction_id": client_transaction_id,
            "metadata": metadata,
        }

        response = await self.http.post("/payments", json=payload, user_id=user_id)
        return response.json()

    async def get_status(self, user_id: str, client_transaction_id: str) -> dict[str, Any]:
        """
        Get payment status by client transaction ID.

        Args:
            user_id: User ID who created the payment
            client_transaction_id: Client transaction ID from send()

        Returns:
            Payment status data including status, amount, timestamps

        Example:
            ```python
            status = await client.payments.get_status(
                user_id=user_id,
                client_transaction_id="sdk-12345..."
            )

            print(f"Payment status: {status['status']}")
            # Status can be: PENDING, PROCESSING, ACCEPTED, COMPLETED, FAILED
            ```
        """
        response = await self.http.get(
            f"/payments/status/{client_transaction_id}", user_id=user_id
        )
        return response.json()
