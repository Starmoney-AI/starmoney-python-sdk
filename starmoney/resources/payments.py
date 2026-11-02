"""StarMoney SDK - Payments Resource"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from .._iban import is_valid_iban
from ..exceptions import InvalidIBANError
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
        amount: Decimal | float | str | None = None,
        currency: str = "XOF",
        beneficiary_iban: Optional[str] = None,
        beneficiary_name: Optional[str] = None,
        description: Optional[str] = None,
        rail_name: Optional[str] = None,
        client_transaction_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        client_reference: Optional[str] = None,
        intent_mandate: Optional[dict[str, Any]] = None,
        cart_mandate: Optional[dict[str, Any]] = None,
        *,
        quote_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a payment, optionally with a UP3 mandate chain.

        Two ways to name the instruction (transfer routes, 0.3.0):
          - **confirm a quote**: ``quote_id`` from :meth:`quote`; amount,
            currency and the recipient come from the quote (the resolved IBAN
            never travels through the client). ``beneficiary_name`` and
            ``description`` are optional. amount / beneficiary_iban MAY be
            given and must then equal the quote (422 QUOTE_MISMATCH).
          - **legacy**: amount + beneficiary_iban + beneficiary_name +
            description, unchanged.

        Args:
            user_id: User ID sending the payment.
            amount: Payment amount (Decimal, float, or string). Required
                without ``quote_id``.
            currency: Currency code (e.g., 'XOF').
            beneficiary_iban: Recipient's IBAN. Required without ``quote_id``.
            beneficiary_name: Recipient's name. Required without ``quote_id``.
            description: Payment description. Required without ``quote_id``.
            quote_id: The quote to confirm (``quote["quote"]["id"]`` from
                :meth:`quote`). Consumed once; a retry with the same
                ``client_transaction_id`` answers the stored outcome (200).
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
            client_transaction_id, customer_reference (since 0.2.3), status,
            created_at, and optionally
            payment_mandate (revision-1 PaymentMandate signed by StarMoney).
            A quote-confirmed send also carries ``quote_id``, ``settlement_rail``,
            ``fees_minor {orchestrator, bank}``, ``fee_total_minor``,
            ``total_debit_minor`` and ``fee_grid_version`` (null on a legacy send).
            A same-cart retry answering ``already_failed`` carries ``funds``
            (:data:`starmoney.FundsOutcome`, since 0.3.2): ``not_debited`` or
            ``debited_under_review`` or, once the bank has returned the principal
            and ``payment.reversed`` was sent, ``returned``. Otherwise the
            same answer as that payment's ``payment.failed``. Null on every other status.

        Raises:
            InvalidIBANError (422): beneficiary_iban failed format or mod-97 —
                raised client-side before the request, and by the server.
            ValueError: neither quote_id nor the full legacy instruction given.
            With quote_id (B-32 envelopes): 404 QUOTE_NOT_FOUND, 409
                QUOTE_CONSUMED (carries the consuming ``transaction_id`` +
                ``customer_reference``), 410 QUOTE_EXPIRED (re-quote), 422
                QUOTE_MISMATCH (``errors[]`` names the field), 409 RAIL_CHANGED
                (re-quote), 402 INSUFFICIENT_FUNDS (``required_minor``),
                404 NO_VIBAN_ACCOUNT.
            PreKycCeilingExceededError (403): over the per-send pre-KYC ceiling.
            PreKycTotalCeilingExceededError (403): over the cumulative pre-KYC
                send ceiling; carries ceiling / consumed / pending / remaining.
            ValidationError (400/401/410/422): UP3 chain or schema error.
            UP3Replay (409): a cart id reused with different content or by a
                different owner. A same-cart.id retry with the same content is
                not an error — it returns the stored outcome (HTTP 200).
            DuplicateResourceError (409): non-mandated duplicate client_transaction_id.
        """
        if client_transaction_id is None:
            raise ValueError("client_transaction_id is required (idempotency key)")
        # A 0.2 cart signs the quote: the chain is the instruction (P17).
        quoted_cart = (cart_mandate or {}).get("version") == "0.2"
        if quote_id is None and not quoted_cart:
            missing = [
                name
                for name, value in (
                    ("amount", amount),
                    ("beneficiary_iban", beneficiary_iban),
                    ("beneficiary_name", beneficiary_name),
                    ("description", description),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"Without quote_id these are required: {', '.join(missing)} "
                    "(preview with client.payments.quote(...) and pass quote_id, "
                    "or send the full instruction)"
                )
        if beneficiary_iban is not None and not is_valid_iban(beneficiary_iban):
            raise InvalidIBANError(f"Invalid IBAN: {beneficiary_iban!r} failed mod-97 validation")

        payload: dict[str, Any] = {
            "currency": currency,
            "client_transaction_id": client_transaction_id,
        }
        if amount is not None:
            # Convert amount to string for API
            if isinstance(amount, Decimal):
                payload["amount"] = str(amount)
            elif isinstance(amount, float):
                payload["amount"] = f"{amount:.2f}"
            else:
                payload["amount"] = str(amount)
        if beneficiary_iban is not None:
            payload["beneficiary_iban"] = beneficiary_iban
        if beneficiary_name is not None:
            payload["beneficiary_name"] = beneficiary_name
        if description is not None:
            payload["description"] = description
        if quote_id is not None:
            payload["quote_id"] = quote_id
        # ADR-001: rail_name is an optional routing hint. Omit it when not given;
        # StarMoney selects the rail server-side.
        if rail_name is not None:
            payload["rail_name"] = rail_name
        if metadata is not None:
            payload["metadata"] = metadata
        if client_reference is not None:
            payload["client_reference"] = client_reference
        if intent_mandate is not None:
            payload["intent_mandate"] = intent_mandate
        if cart_mandate is not None:
            payload["cart_mandate"] = cart_mandate

        response = await self.http.post("/payments", json=payload, user_id=user_id)
        return response.json()

    async def quote(
        self,
        user_id: str,
        *,
        beneficiary_type: str,
        beneficiary_value: str,
        amount_minor: int,
        currency: str = "XOF",
    ) -> dict[str, Any]:
        """
        Preview one transfer before the PIN (transfer routes, PR-A):
        ``POST /v1/payments/quotes``. Resolves the recipient, picks the
        settlement rail, prices the fee and returns a quote the confirm
        consumes once. Moves no money.

        Args:
            user_id: The sender.
            beneficiary_type: ``"iban"`` (any IBAN), ``"msisdn"`` (phone, E.164
                or local) or ``"beneficiary"`` (a saved beneficiary id).
                ``"alias"`` is refused until W-124 ships.
            beneficiary_value: The identifier as the customer named it.
            amount_minor: Amount in minor units (XOF has none: 1 F = 1).
            currency: ISO 4217, default XOF.

        Returns:
            PaymentQuoteResponse dict: ``quote {id, digest, digest_alg,
            expires_at}``, ``outcome`` (credit | external), ``rail``
            (bdk.internal | bdk.rtgs), ``rail_kind``, ``bank``, ``display_name``
            + ``display_name_verified``, ``beneficiary {type, value}``,
            ``amount_minor``, ``currency``, ``fees_minor {orchestrator, bank}``,
            ``fee_total_minor``, ``total_debit_minor``, ``fee_collection``,
            ``fee_grid_version``, ``send_remaining_minor``. The resolved IBAN is
            never returned.

        Raises (B-32 envelopes, see docs/ERRORS.md):
            ValidationError 422 INVALID_IBAN / INVALID_PHONE /
                SELF_TRANSFER_NOT_ALLOWED / BENEFICIARY_TYPE_UNSUPPORTED;
            422 RECIPIENT_HAS_NO_ACCOUNT — the number has no creditable
                account; the body carries ``recipient_status`` and
                ``deferred_quote`` for ``POST /v1/deferred-transfers``;
            404 BENEFICIARY_NOT_FOUND; 409 RECIPIENT_NOT_CREDITABLE /
                BENEFICIARY_ACCOUNT_CLOSED; 429 IDENTIFIER_LOOKUP_LIMIT_REACHED
                (``retry_after_seconds``); 403 PRE_KYC_*_CEILING_EXCEEDED.
        """
        payload: dict[str, Any] = {
            "beneficiary": {"type": beneficiary_type, "value": beneficiary_value},
            "amount_minor": int(amount_minor),
            "currency": currency,
        }
        response = await self.http.post("/payments/quotes", json=payload, user_id=user_id)
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
              trigger_event, starmoney_transaction_id, customer_reference
              (since 0.2.3), and ``funds`` (since 0.3.2) on a failed or
              cancelled payment: ``not_debited`` (BDK never accepted; any hold
              released) or ``debited_under_review`` (BDK had accepted, the
              money is not back yet) or ``returned`` (the bank returned the
              principal; ``payment.reversed`` was sent). The bank decides;
              otherwise the same answer as the payment's ``payment.failed``.
              Null otherwise.
        """
        response = await self.http.get(f"/payments/status/{client_transaction_id}", user_id=user_id)
        return response.json()

    async def send_with_mandates(
        self,
        user_id: str,
        *,
        amount_minor: Optional[int] = None,
        currency: Optional[str] = None,
        beneficiary_iban: Optional[str] = None,
        beneficiary_name: Optional[str] = None,
        description: Optional[str] = None,
        rail_name: Optional[str] = None,
        user_ref: str,
        client_transaction_id: Optional[str] = None,
        client_reference: Optional[str] = None,
        consent_token: Optional[dict[str, Any]] = None,
        fees_minor: Optional[dict[str, int]] = None,
        intent_ttl_minutes: int = 15,
        cart_ttl_minutes: int = 2,
        idempotency_seed: Optional[str] = None,
        confirmed_at: Optional[str] = None,
        quote_id: Optional[str] = None,
        quote: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Build Intent + Cart mandates and submit the payment — all in one call.

        Two ways to name the instruction (transfer routes, 0.3.0):

        - **``quote=``** (preferred): pass the whole ``client.payments.quote(...)``
          response. The SDK builds a **0.2 cart that signs the quote**
          (``beneficiary {type, value}``, ``quote {id, digest, digest_alg}``,
          the quoted fee legs — UP3 0.2-draft P17) and posts the chain with
          **no instruction fields** in the body: the cart *is* the quote, the
          bank binds it to the quote it stored and confirms the rail and fee it
          previewed. ``amount_minor`` / ``currency`` / ``beneficiary_iban`` /
          ``beneficiary_name`` are read from the quote (do not pass them).
          ``description`` is optional (it becomes the motif after the
          ``sm_reference``). The cart's ``expires_at`` never passes the
          quote's (P12).
        - **legacy**: ``amount_minor``, ``currency``, ``beneficiary_iban``,
          ``beneficiary_name``, ``description`` → a 0.1 cart (IBAN by value).
          ``quote_id`` beside them confirms a quote with a 0.1 cart (the body
          fields must equal the quote's, else QUOTE_MISMATCH); kept for
          callers that have not moved to ``quote=``.

        This is the method skills and chatbot flows should call. Internally it:
          1. Builds and signs an IntentMandate.
          2. Builds and signs a CartMandate referencing the intent.
          3. Calls POST /v1/payments with both envelopes attached.

        The returned PaymentMandate is NOT verified here (0.1.22). The bank signs
        it with its own key, which this client does not hold; a check against
        the client's secret could only ever fail, and a key that could verify
        it could also forge it. Verification of PaymentMandates becomes possible
        once the bank signs them with an asymmetric key (UP3 0.2-draft).

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
            consent_token: The user_consent_evidence the cart carries. Defaults
                to service_attestation (the client's word). A chat surface should
                pass chat_session_pin_v1 {verified_at, attempt_count,
                session_id_hash}: the bank accepts it per issuer
                (UP3_ACCEPTED_EVIDENCE_TYPES) and measures consent freshness
                from verified_at against confirmed_at (300 s window).
                attempt_count is a lower bound (wrong codes typed inside a PIN
                Flow never reach the session).
            fees_minor: Fees dict for the CartMandate (e.g. {"orchestrator": 50}).
                        Defaults to empty dict.
            intent_ttl_minutes: IntentMandate TTL (default 15, max 60).
            cart_ttl_minutes: CartMandate TTL (default 2).
            idempotency_seed: Opaque, caller-stable seed (e.g. a consent_jti)
                the cart.id is derived from. RETRY CONTRACT: pass the SAME seed
                when retrying the SAME authorization after a timeout / network
                failure — the bank answers with the STORED outcome (HTTP 200:
                the original transaction_id and its PaymentMandate at the latest
                revision; response `status` is already_in_progress,
                already_completed or already_failed) instead of posting a second
                debit. A NEW seed is required for every distinct authorization
                and after any failed payment (the old seed keeps returning the
                stored failure). Reusing a seed with a different amount or
                beneficiary is rejected as UP3_REPLAY (409). See
                UP3Resource.build_cart. Omit for the legacy behaviour (fresh
                random id every call, no retry-safety).
            confirmed_at: RFC 3339 Z timestamp of the moment the user actually
                confirmed these terms (the Flow submit or button tap), e.g.
                '2026-10-03T14:23:14Z'. Signed into the cart; the bank measures
                its consent-freshness window from it. Defaults to now, which is
                only right when the call is made at the tap itself.

        Returns:
            Full CreatePaymentAPIResponse dict. The payment_mandate key carries
            the revision-1 PaymentMandate signed by StarMoney when the mandate
            chain was valid. Since 0.1.23 the dict also carries intent_mandate
            and cart_mandate: the exact signed envelopes this call posted.
            Since 0.2.3 it carries customer_reference, the reference to show
            the customer (a replay returns the original payment's).

        Raises:
            RuntimeError: UP3 resource not configured with a secret.
            ValidationError / APIError: Any UP3 or payment error from the API.
        """
        if self._up3 is None:
            raise RuntimeError(
                "send_with_mandates requires the UP3 resource; " "initialise StarmoneyClient with up3_secret=..."
            )

        if quote is not None:
            return await self._send_with_quoted_cart(
                user_id=user_id,
                quote=quote,
                description=description,
                beneficiary_name=beneficiary_name,
                user_ref=user_ref,
                client_transaction_id=client_transaction_id,
                client_reference=client_reference,
                consent_token=consent_token,
                intent_ttl_minutes=intent_ttl_minutes,
                cart_ttl_minutes=cart_ttl_minutes,
                idempotency_seed=idempotency_seed,
                confirmed_at=confirmed_at,
                quote_id=quote_id,
                rail_name=rail_name,
            )

        missing = [
            name
            for name, value in (
                ("amount_minor", amount_minor),
                ("currency", currency),
                ("beneficiary_iban", beneficiary_iban),
                ("beneficiary_name", beneficiary_name),
                ("description", description),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "send_with_mandates without quote= needs the full instruction: missing "
                + ", ".join(missing)
                + " (or pass quote=<the payments.quote(...) response> and let the 0.2 cart sign it)"
            )
        assert amount_minor is not None and currency is not None  # for type-checkers
        assert beneficiary_iban is not None and beneficiary_name is not None and description is not None

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
        if confirmed_at is None:
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
            idempotency_seed=idempotency_seed,
        )

        # Fail fast, locally: a caller-supplied client_transaction_id that
        # disagrees with the (derived-or-random) cart.id is rejected by the
        # server as UP3_SCHEMA_INVALID (cart.id is the sole idempotency
        # anchor in v0.1). Catch it here instead of round-tripping.
        if client_transaction_id is not None and client_transaction_id != cart["id"]:
            raise ValueError(
                f"client_transaction_id={client_transaction_id!r} does not match "
                f"cart.id={cart['id']!r}; cart.id is the canonical idempotency "
                f"anchor in v0.1 — omit client_transaction_id and let it default "
                f"to cart.id, or pass idempotency_seed instead of a raw "
                f"client_transaction_id."
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
            client_reference=client_reference,
            intent_mandate=intent,
            cart_mandate=cart,
            quote_id=quote_id,
        )

        # 0.1.23: hand back the exact signed envelopes that were posted, so the
        # caller's record holds the cart it signed (confirmed_at, evidence),
        # not just its id. Extra keys; nothing in the bank's response moves.
        return {**response_data, "intent_mandate": intent, "cart_mandate": cart}

    async def _send_with_quoted_cart(
        self,
        *,
        user_id: str,
        quote: dict[str, Any],
        description: Optional[str],
        beneficiary_name: Optional[str],
        user_ref: str,
        client_transaction_id: Optional[str],
        client_reference: Optional[str],
        consent_token: Optional[dict[str, Any]],
        intent_ttl_minutes: int,
        cart_ttl_minutes: int,
        idempotency_seed: Optional[str],
        confirmed_at: Optional[str],
        quote_id: Optional[str],
        rail_name: Optional[str],
    ) -> dict[str, Any]:
        """``send_with_mandates(quote=...)``: the 0.2 cart signs the quote, the body
        carries the chain and nothing else about the instruction."""
        assert self._up3 is not None
        ref = quote.get("quote") or {}
        if quote_id is not None and quote_id != ref.get("id"):
            raise ValueError(
                f"quote_id={quote_id!r} is not the quote passed as quote= ({ref.get('id')!r}); "
                "pass one or the other"
            )
        if rail_name is not None:
            raise ValueError(
                "rail_name cannot be combined with quote=: the quote fixed the settlement rail "
                "(ADR-001, the bank picks it)"
            )
        amount_minor = int(quote["amount_minor"])
        shown_name = quote.get("display_name")
        if beneficiary_name is None:
            beneficiary_name = shown_name
        intent_description = description or f"send {amount_minor} {quote.get('currency', 'XOF')}"

        intent = self._up3.build_intent(
            user_ref=user_ref,
            description=intent_description,
            max_amount_minor=amount_minor,
            currency=quote.get("currency", "XOF"),
            beneficiary_hint=beneficiary_name or quote.get("beneficiary", {}).get("value"),
            ttl_minutes=intent_ttl_minutes,
        )
        cart = self._up3.build_cart_v02(
            intent,
            quote=quote,
            beneficiary_name=beneficiary_name,
            confirmed_at=confirmed_at,
            consent_evidence=consent_token,
            ttl_minutes=cart_ttl_minutes,
            idempotency_seed=idempotency_seed,
        )
        if client_transaction_id is not None and client_transaction_id != cart["id"]:
            raise ValueError(
                f"client_transaction_id={client_transaction_id!r} does not match "
                f"cart.id={cart['id']!r}; omit it (it defaults to cart.id) or pass idempotency_seed."
            )
        response_data = await self.send(
            user_id=user_id,
            currency=quote.get("currency", "XOF"),
            description=description,
            client_transaction_id=cart["id"],
            client_reference=client_reference,
            intent_mandate=intent,
            cart_mandate=cart,
        )
        return {**response_data, "intent_mandate": intent, "cart_mandate": cart}

    def cart_id_for(self, idempotency_seed: str) -> str:
        """The cart.id (and client_transaction_id) a send_with_mandates call
        with this idempotency_seed uses, without building anything.

        A timed-out send_with_mandates returns nothing, yet the bank may have
        executed it (a 201 is written before the rail is called). Compute the
        id from the seed you used and ask ``get_status(user_id, cart_id)``:
        found means the payment is in flight; not found after a short wait
        means nothing was captured and a fresh consent may be offered.

        Raises:
            RuntimeError: UP3 resource not configured.
        """
        if self._up3 is None:
            raise RuntimeError("cart_id_for requires the UP3 resource; initialise StarmoneyClient with up3_secret=...")
        return self._up3.cart_id_for(idempotency_seed)
