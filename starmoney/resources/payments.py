"""StarMoney SDK - Payments Resource"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from ..http_client import HTTPClient

if TYPE_CHECKING:
    from ..up3.resource import UP3Resource


class PaymentsResource:
    """
    Payments resource for sending and tracking payments.

    Handles:
    - Sending payments (with optional UP3 mandate chain)
    - Checking payment status
    - One-call send_with_mandates (builds Intent + Cart, submits, verifies)
    """

    def __init__(self, http_client: HTTPClient) -> None:
        self.http = http_client
        # Injected by StarmoneyClient after construction to avoid circular imports.
        self._up3: Optional["UP3Resource"] = None

    async def send(
        self,
        user_id: str,
        amount: Decimal | float | str,
        currency: str,
        beneficiary_iban: str,
        beneficiary_name: str,
        description: str,
        rail_name: Optional[str],
        client_transaction_id: str,
        metadata: Optional[dict[str, Any]] = None,
        intent_mandate: Optional[dict[str, Any]] = None,
        cart_mandate: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Send a payment, optionally with a UP3 mandate chain.

        Args:
            user_id: User ID sending the payment.
            amount: Payment amount (Decimal, float, or string).
            currency: Currency code (e.g., 'XOF').
            beneficiary_iban: Recipient's IBAN.
            beneficiary_name: Recipient's name.
            description: Payment description.
            rail_name: Optional routing hint (e.g. 'BDK', 'VIBAN'). Omit to let
                       StarMoney select the rail (ADR-001) — VIBAN when the sender
                       can fund from their vIBAN, else BDK.
            client_transaction_id: Idempotency key.
            metadata: Optional extra metadata dict.
            intent_mandate: Optional UP3 IntentMandate envelope (signed dict).
                            When omitted the legacy non-mandated flow runs.
            cart_mandate: Optional UP3 CartMandate envelope (signed dict).
                          Required if intent_mandate is provided.

        Returns:
            CreatePaymentAPIResponse dict including transaction_id,
            client_transaction_id, status, created_at, and optionally
            payment_mandate (revision-1 PaymentMandate signed by StarMoney).

        Raises:
            ValidationError (400/401/410/422): UP3 chain or schema error.
            DuplicateResourceError (409): UP3_REPLAY.
        """
        # Convert amount to string for API
        if isinstance(amount, Decimal):
            amount_str = str(amount)
        elif isinstance(amount, float):
            amount_str = f"{amount:.2f}"
        else:
            amount_str = str(amount)

        payload: dict[str, Any] = {
            "amount": amount_str,
            "currency": currency,
            "beneficiary_iban": beneficiary_iban,
            "beneficiary_name": beneficiary_name,
            "description": description,
            "client_transaction_id": client_transaction_id,
        }
        # ADR-001: rail_name is an optional routing hint. Omit it when not given;
        # StarMoney selects the rail server-side.
        if rail_name is not None:
            payload["rail_name"] = rail_name
        if metadata is not None:
            payload["metadata"] = metadata
        if intent_mandate is not None:
            payload["intent_mandate"] = intent_mandate
        if cart_mandate is not None:
            payload["cart_mandate"] = cart_mandate

        response = await self.http.post("/payments", json=payload, user_id=user_id)
        return response.json()

    async def get_status(self, user_id: str, client_transaction_id: str) -> dict[str, Any]:
        """
        Get payment status by client transaction ID.

        Args:
            user_id: User ID who created the payment.
            client_transaction_id: Client transaction ID from send().

        Returns:
            PaymentStatusAPIResponse dict with keys:
              client_transaction_id, status, last_updated, status_message,
              trigger_event, starmoney_transaction_id.
        """
        response = await self.http.get(
            f"/payments/status/{client_transaction_id}", user_id=user_id
        )
        return response.json()

    async def send_with_mandates(
        self,
        user_id: str,
        *,
        amount_minor: int,
        currency: str,
        beneficiary_iban: str,
        beneficiary_name: str,
        description: str,
        rail_name: Optional[str] = None,
        user_ref: str,
        client_transaction_id: Optional[str] = None,
        consent_token: Optional[dict[str, Any]] = None,
        fees_minor: Optional[dict[str, int]] = None,
        intent_ttl_minutes: int = 15,
        cart_ttl_minutes: int = 2,
    ) -> dict[str, Any]:
        """
        Build Intent + Cart mandates, submit the payment, and verify the
        returned PaymentMandate — all in one call.

        This is the method skills and chatbot flows should call. Internally it:
          1. Builds and signs an IntentMandate.
          2. Builds and signs a CartMandate referencing the intent.
          3. Calls POST /v1/payments with both envelopes attached.
          4. Verifies the PaymentMandate signature in the response.

        The UP3 resource must be initialised with a secret (up3_secret arg on
        StarmoneyClient) for signing to work. If up3_secret is not set,
        mandate envelopes are not built and the call falls back to the legacy
        non-mandated flow.

        Args:
            user_id: Authenticated sender user ID.
            amount_minor: Amount in smallest currency unit (XOF: no minor digits).
            currency: ISO 4217 currency code. v0.1 = 'XOF' only.
            beneficiary_iban: Resolved recipient IBAN.
            beneficiary_name: Recipient display name.
            description: Human-readable description of the payment intent.
            rail_name: Optional routing hint (ADR-001). Omit it — StarMoney
                       selects the rail (VIBAN when the sender can fund from their
                       vIBAN, else BDK; all settling over BDK RTGS today) and
                       stamps the executed rail onto the PaymentMandate. When
                       provided: 'BDK' is honored; 'VIBAN' is honored only if the
                       sender has a payable vIBAN, else the request is rejected
                       (400). The signed CartMandate no longer carries a rail.
            user_ref: Stable user identifier (e.g. 'whatsapp:+221771234567').
            client_transaction_id: Idempotency key. Defaults to the cart mandate
                                   id (recommended per UP3 spec).
            consent_token: Optional user-consent-evidence override. Defaults to
                           service_attestation (v0.1 guardrail). Do NOT pass a
                           user-evidence type here until v0.2.
            fees_minor: Fees dict for the CartMandate (e.g. {"orchestrator": 50}).
                        Defaults to empty dict.
            intent_ttl_minutes: IntentMandate TTL (default 15, max 60).
            cart_ttl_minutes: CartMandate TTL (default 2).

        Returns:
            Full CreatePaymentAPIResponse dict. The payment_mandate key carries
            the revision-1 PaymentMandate signed by StarMoney when the mandate
            chain was valid.

        Raises:
            RuntimeError: UP3 resource not configured with a secret.
            ValidationError / APIError: Any UP3 or payment error from the API.
        """
        if self._up3 is None:
            raise RuntimeError(
                "send_with_mandates requires the UP3 resource; "
                "initialise StarmoneyClient with up3_secret=..."
            )

        # Step 1 — build and sign IntentMandate.
        intent = self._up3.build_intent(
            user_ref=user_ref,
            description=description,
            max_amount_minor=amount_minor,
            currency=currency,
            beneficiary_hint=beneficiary_name,
            rail_hint=rail_name,
            ttl_minutes=intent_ttl_minutes,
        )

        # Step 2 — build and sign CartMandate.
        import datetime as _dt

        confirmed_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cart = self._up3.build_cart(
            intent,
            amount_minor=amount_minor,
            beneficiary_iban=beneficiary_iban,
            beneficiary_name=beneficiary_name,
            rail=rail_name,
            fees_minor=fees_minor or {},
            confirmed_at=confirmed_at,
            consent_evidence=consent_token,
            ttl_minutes=cart_ttl_minutes,
        )

        # Use cart.id as the idempotency key per UP3 spec recommendation.
        txn_id = client_transaction_id or cart["id"]

        # Step 3 — submit.
        response_data = await self.send(
            user_id=user_id,
            amount=str(amount_minor),
            currency=currency,
            beneficiary_iban=beneficiary_iban,
            beneficiary_name=beneficiary_name,
            description=description,
            rail_name=rail_name,
            client_transaction_id=txn_id,
            intent_mandate=intent,
            cart_mandate=cart,
        )

        # Step 4 — verify the returned PaymentMandate.
        payment_mandate = response_data.get("payment_mandate")
        if payment_mandate is not None:
            self._up3.verify_payment_mandate(payment_mandate)

        return response_data
