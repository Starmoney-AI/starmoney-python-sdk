"""StarMoney SDK - Deferred Transfers Resource

Mirrors POST /v1/deferred-transfers/send, GET /v1/deferred-transfers (list),
GET /v1/deferred-transfers/{id}, POST /v1/deferred-transfers/{id}/claim,
POST /v1/deferred-transfers/{id}/cancel.
"""

from typing import TYPE_CHECKING, Any, Literal, Optional, TypedDict

from ..http_client import HTTPClient

if TYPE_CHECKING:  # pragma: no cover
    from ..up3.resource import UP3Resource

DeferredFundingSource = Literal["viban_hold", "external_pull"]


class _DeferredTransferAccountFields(TypedDict):
    """Fields shared by a list row and the single read (B-56)."""

    funding_source: DeferredFundingSource  # same words as the send request
    sender_account_reference: Optional[str]  # null for external_pull
    # The recipient's account, in full (as on deferred_transfer.settled); null until
    # claimed. Mask it for display.
    recipient_account_reference: Optional[str]
    # B-54: the recipient's first name once they have an account (the name
    # deferred_transfer.settled carries); null before. Always sent; read with
    # ``.get()`` against a bank older than B-54.
    recipient_display_name: Optional[str]
    # B-54: the sender's own wording for the send (max 30 characters); null when
    # none. Always sent; read with ``.get()`` against a bank older than this field.
    description: Optional[str]


class DeferredTransferListItem(_DeferredTransferAccountFields):
    """One row of ``deferred_transfers.list(...)["deferred_transfers"]``."""

    deferred_transfer_id: str
    sm_reference: str
    customer_reference: str  # deprecated, dropped in 0.4.0
    client_transaction_id: str
    recipient_handle: str  # MASKED
    amount_minor: int
    currency: str
    status: str
    created_at: str
    expires_at: Optional[str]


class DeferredTransferRead(_DeferredTransferAccountFields):
    """Account fields added to ``deferred_transfers.get(...)`` (B-56, and the
    recipient's first name, B-54); the other keys of the response are unchanged.

    Since 0.3.23 (B-98) the fee line also names the pricing ``segment`` and the
    ``funding_rail`` (``"viban"`` | ``"bdk"``); both are null on a transfer sent
    without a quote. Always sent; read with ``.get()`` against an older bank."""

    segment: Optional[str]
    funding_rail: Optional[str]


class DeferredTransfersResource:
    """
    Deferred Transfers resource (flow 01).

    A deferred transfer lets a sender push funds to a recipient who does not
    yet have a StarMoney account. The send-half places a hold on the sender's
    vIBAN (Branch A) or defers the pull (Branch B); the claim-half settles
    once the recipient onboards.

    All methods are async and mirror the endpoint contracts exactly.
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client
        # Wired by StarMoneyClient.deferred_transfers (PR-D, send_with_mandates).
        self._up3: Optional["UP3Resource"] = None

    async def send(
        self,
        client_transaction_id: Optional[str] = None,
        recipient_handle: Optional[str] = None,
        amount_minor: Optional[int] = None,
        currency: Literal["XOF"] = "XOF",
        funding_source: Optional[Literal["viban_hold", "external_pull"]] = None,
        linked_external_account_id: Optional[str] = None,
        client_reference: Optional[str] = None,
        user_id: Optional[str] = None,
        *,
        description: Optional[str] = None,
        quote_id: Optional[str] = None,
        intent_mandate: Optional[dict[str, Any]] = None,
        cart_mandate: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create a deferred-trigger transfer (send-half).

        Three ways to name the instruction:

        - **``quote_id=``** (PR-D, B-67): the ``deferred_quote.id`` carried on a
          ``RECIPIENT_HAS_NO_ACCOUNT`` refusal of ``payments.quote(...)``. The
          quote IS the instruction — the phone, the amount and the currency
          are taken from it, ``funding_source`` defaults to ``viban_hold``;
          repeating them is allowed only if they match (``QUOTE_MISMATCH``
          otherwise). The quote is spent by the hold (``QUOTE_CONSUMED`` names
          the hold's ``sm_reference`` on a second use).
        - **``intent_mandate=`` + ``cart_mandate=``** (UP3): a 0.2 cart from
          :meth:`UP3Resource.build_deferred_cart_v02` carries the quote and the
          execution window; ``client_transaction_id`` defaults to ``cart.id``.
          Prefer :meth:`send_with_mandates`, which builds the chain for you.
        - the full instruction (``recipient_handle``, ``amount_minor``,
          ``funding_source``) — the pre-0.3.1 shape, unchanged.

        Branch A (funding_source='viban_hold'): the sender's vIBAN account is
        resolved server-side from their stored rail credentials and a hold is
        placed. No account field from the caller.

        Branch B (funding_source='external_pull'): funds are pulled from a
        linked external account at claim time. linked_external_account_id is
        required.

        Idempotent on client_transaction_id.

        Args:
            client_transaction_id: Idempotency key. Same value always returns
                                   the same DeferredTransfer.
            recipient_handle: Recipient phone number, E.164 (e.g. '+221771234567').
                              A deferred transfer takes a phone only: an IBAN or
                              any other handle is refused with 422 INVALID_PHONE
                              before any hold is placed.
            amount_minor: Instruction amount in the smallest currency unit (> 0).
            currency: Currency code. Only 'XOF' is accepted.
            funding_source: 'viban_hold' (Branch A, default) or 'external_pull'
                            (Branch B).
            linked_external_account_id: Branch B only. Required when
                                        funding_source='external_pull'.
            description: The sender's own wording for the transfer (max 30
                         characters, e.g. 'loyer'). Optional with any of the
                         three shapes (a quote or a cart carries no wording).
                         Stored with the transfer, echoed on
                         ``deferred_transfer.sent`` / ``.settled`` and read back
                         as ``description``. Sent only when given.

        Returns:
            DeferredTransferResponse dict with keys:
              id, sm_reference (customer_reference until 0.4.0),
              client_transaction_id, sender_user_id, recipient_handle,
              amount_minor, currency, branch, status, expires_at, created_at,
              updated_at, description (the sender's wording, null when none),
              and the fee line of a quoted hold (``quote_id``,
              ``settlement_rail``, ``fees_minor``, ``fee_total_minor``,
              ``total_debit_minor``, ``fee_grid_version``, ``segment``,
              ``funding_rail`` — null on a legacy send). Since 0.3.23 the
              deferred transfer carries the 1 %: a vIBAN-funded hold reserves
              amount + fee (``total_debit_minor``), released whole on cancel or
              expiry and booked when the transfer is executed; a send from a
              linked BDK account accrues it (``total_debit_minor`` = amount).

        Raises:
            ValidationError (422): Invalid request (e.g. missing
                linked_external_account_id for Branch B, amount <= 0).
            APIError (503): vIBAN ledger service unavailable.
        """
        if (intent_mandate is None) != (cart_mandate is None):
            raise ValueError("intent_mandate and cart_mandate travel together")
        if cart_mandate is not None:
            cart_id = cart_mandate.get("id")
            if client_transaction_id is None:
                client_transaction_id = cart_id
            elif client_transaction_id != cart_id:
                raise ValueError(
                    f"client_transaction_id={client_transaction_id!r} does not match "
                    f"cart.id={cart_id!r}; omit it (it defaults to cart.id)"
                )
            signed = ((cart_mandate.get("payload") or {}).get("quote") or {}).get("id")
            if quote_id is None:
                quote_id = signed
            elif signed is not None and quote_id != signed:
                raise ValueError(f"quote_id={quote_id!r} is not the quote the cart signs ({signed!r})")
        if client_transaction_id is None:
            raise ValueError("client_transaction_id is required (or a cart whose id it is)")
        if quote_id is None:
            missing = [
                name
                for name, value in (
                    ("recipient_handle", recipient_handle),
                    ("amount_minor", amount_minor),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} required without quote_id (pass the deferred_quote.id "
                    "of the RECIPIENT_HAS_NO_ACCOUNT refusal, or the full instruction)"
                )
            if funding_source is None:
                funding_source = "viban_hold"

        payload: dict[str, Any] = {"client_transaction_id": client_transaction_id, "currency": currency}
        if recipient_handle is not None:
            payload["recipient_handle"] = recipient_handle
        if amount_minor is not None:
            payload["amount_minor"] = amount_minor
        if funding_source is not None:
            payload["funding_source"] = funding_source
        if quote_id is not None:
            payload["quote_id"] = quote_id
        if intent_mandate is not None:
            payload["intent_mandate"] = intent_mandate
            payload["cart_mandate"] = cart_mandate
        if linked_external_account_id is not None:
            payload["linked_external_account_id"] = linked_external_account_id
        if client_reference is not None:
            payload["client_reference"] = client_reference
        if description is not None:
            payload["description"] = description

        # The sender is the JWT sub claim: pass user_id so the request is signed
        # for that user (0.1.22; before, callers had to post raw HTTP for it).
        if user_id is not None:
            response = await self.http.post(
                "/deferred-transfers/send", user_id=user_id, json=payload
            )
        else:
            response = await self.http.post("/deferred-transfers/send", json=payload)
        return response.json()

    async def send_with_mandates(
        self,
        user_id: str,
        *,
        user_ref: str,
        refusal: dict[str, Any],
        beneficiary_value: str,
        amount_minor: int,
        currency: Literal["XOF"] = "XOF",
        execute_before: Optional[str] = None,
        hold_days: int = 7,
        description: Optional[str] = None,
        client_reference: Optional[str] = None,
        consent_token: Optional[dict[str, Any]] = None,
        intent_ttl_minutes: int = 15,
        cart_ttl_minutes: int = 2,
        idempotency_seed: Optional[str] = None,
        confirmed_at: Optional[str] = None,
    ) -> dict[str, Any]:
        """The hold from the quote, under a UP3 chain (bank PR-D, B-67).

        ``payments.quote(...)`` refused the phone with ``RECIPIENT_HAS_NO_ACCOUNT``
        and a ``deferred_quote``; the customer confirmed «hold 20 000 F for
        +221 78 … until they open an account». This builds the intent and a
        **0.2 cart that signs the deferred quote** (the phone as typed, the
        amount, the fee legs as the quote priced them, and an execution window,
        R1–R4) and posts the chain to ``POST /v1/deferred-transfers/send`` with nothing
        else about the instruction. The bank verifies the consent BEFORE
        placing the hold, spends the quote with the row, and answers the
        deferred transfer with its fee line and ``sm_reference``. No
        PaymentMandate is issued at this step: the instruction does not exist
        until the recipient's account does (claim → settle).

        A transport retry with the same ``idempotency_seed`` derives the same
        ``cart.id`` and gets the same deferred transfer back.

        Args:
            user_id: The sender (JWT ``sub``).
            user_ref: The sender's channel identity (``whatsapp:+221…``).
            refusal: The 422 body of ``payments.quote(...)`` (or its
                ``deferred_quote``). Raise locally when it carries none.
            beneficiary_value: The phone the customer typed (E.164).
            amount_minor: The amount quoted.
            execute_before / hold_days: The execution window; default 7 days
                from the tap. See :meth:`UP3Resource.build_deferred_cart_v02`.
            description: The sender's wording (max 30 characters, e.g. ``"loyer"``).
                Sent in the request body (the signed cart carries no wording) and
                also used as the intent's human echo, as in ``payments.send_with_mandates``;
                the bank refuses one over 30 characters with 422.
            consent_token: ``user_consent_evidence`` (the ConsentToken).
            idempotency_seed: The retry anchor (e.g. the consent jti).

        Returns:
            The ``DeferredTransferResponse`` dict plus the ``intent_mandate``
            and ``cart_mandate`` that were posted.

        Raises:
            ValueError: no deferred quote, or ``hold_days`` outside 1–7.
            APIError subclasses with the B-32 envelope — ``QUOTE_MISMATCH``,
            ``UP3_QUOTE_DRIFT`` / ``UP3_REPLAY`` / ``UP3_EXPIRED`` (quote
            state), ``UP3_EXECUTION_WINDOW_INVALID`` (R1–R4),
            ``UP3_EXECUTION_MODE_MISMATCH`` (the cart's ``execution_mode`` contradicts
            the quote or ``funding_source``; a ``deferred_best_effort`` cart is the
            pull from the sender's BDK account).
        """
        if self._up3 is None:
            raise RuntimeError(
                "UP3 resource not wired — use StarMoneyClient.deferred_transfers (the client sets "
                "it) or assign resource._up3 = client.up3"
            )
        intent = self._up3.build_intent(
            user_ref=user_ref,
            description=description or f"hold {int(amount_minor)} {currency} for {beneficiary_value}",
            max_amount_minor=int(amount_minor),
            currency=currency,
            beneficiary_hint=beneficiary_value,
            ttl_minutes=intent_ttl_minutes,
        )
        cart = self._up3.build_deferred_cart_v02(
            intent,
            refusal=refusal,
            beneficiary_value=beneficiary_value,
            amount_minor=int(amount_minor),
            currency=currency,
            execute_before=execute_before,
            hold_days=hold_days,
            confirmed_at=confirmed_at,
            consent_evidence=consent_token,
            ttl_minutes=cart_ttl_minutes,
            idempotency_seed=idempotency_seed,
        )
        response_data = await self.send(
            user_id=user_id,
            currency=currency,
            client_reference=client_reference,
            description=description,
            intent_mandate=intent,
            cart_mandate=cart,
        )
        return {**response_data, "intent_mandate": intent, "cart_mandate": cart}

    async def list(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        client_transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        List the caller's deferred transfers (sender-scoped) — for a cancel pick-list.

        Returns only transfers the caller SENT (JWT sub == sender_user_id), so a
        caller can never enumerate another user's transfers (same ownership rule
        as cancel). Use this to render a "what can I cancel?" pick-list, then call
        cancel() with the chosen deferred_transfer_id.

        Args:
            user_id: The authenticated sender's user ID (drives the JWT sub claim).
            status: Optional comma-separated status filter (e.g. "reserved,armed").
                    When omitted, the API defaults to the cancellable set
                    (reserved, armed). Valid values: reserved, armed, claimed,
                    claimed_pending_kyc, settling, settled, expired, released, cancelled, failed.
            limit: Max transfers to return (default 20, capped at 100 server-side).
            offset: Number of transfers to skip (pagination).
            client_transaction_id: (0.3.0, B-71) only the transfer YOU sent under
                    this idempotency key — e.g. to find a deferred transfer's
                    ``deferred_transfer_id`` / ``sm_reference`` from the id your
                    flow kept. When given and ``status`` is omitted, every status
                    is searched (settled, expired… too), not just the cancellable
                    set. Still sender-scoped: another sender's id never matches.

        Returns:
            Dict with keys:
              user_id, limit, offset, deferred_transfers (list). Each item has:
              deferred_transfer_id, sm_reference (customer_reference until 0.4.0),
              client_transaction_id,
              recipient_handle (MASKED, e.g. '+2217xxxxxx99'),
              amount_minor, currency, status, created_at, expires_at,
              funding_source ('viban_hold' | 'external_pull'),
              sender_account_reference (null for external_pull),
              recipient_account_reference (full, null until claimed; mask it),
              recipient_display_name (the recipient's first name once they have
              an account, else null), description (the sender's wording, null
              when none).
              See :class:`DeferredTransferListItem`.

        Raises:
            ValidationError (422): Unknown status token in the filter.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        if client_transaction_id is not None:
            params["client_transaction_id"] = client_transaction_id

        response = await self.http.get("/deferred-transfers", user_id=user_id, params=params)
        return response.json()

    async def get(self, deferred_transfer_id: str) -> dict[str, Any]:
        """
        Read current status of a deferred transfer by its UUID.

        Args:
            deferred_transfer_id: UUID of the deferred transfer.

        Returns:
            DeferredTransferResponse dict, with ``funding_source``,
            ``sender_account_reference`` and ``recipient_account_reference``
            (:class:`DeferredTransferRead`).

        Raises:
            PaymentNotFoundError (404): Transfer not found.
        """
        response = await self.http.get(f"/deferred-transfers/{deferred_transfer_id}")
        return response.json()

    async def claim(
        self,
        deferred_transfer_id: str,
        viban_tenant_slug: str,
        holder_name: str,
        recipient_user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Claim a RESERVED deferred transfer and settle if within pre-KYC ceiling.

        This is a service-authenticated call (relayed from the onboarding service
        carrying the recipient's details).

        Branch A (hold_backed): onboard recipient vIBAN -> ceiling check ->
          - <= ceiling: RESERVED -> CLAIMED -> SETTLED
          - > ceiling: RESERVED -> CLAIMED -> CLAIMED_PENDING_KYC (hold stays active)

        Branch B (external_pull): not yet implemented; returns 501.

        Idempotent: if the transfer is already CLAIMED/SETTLED/CLAIMED_PENDING_KYC,
        returns the current state without re-emitting.

        Args:
            deferred_transfer_id: UUID of the deferred transfer to claim.
            viban_tenant_slug: vIBAN-ledgers tenant slug for the recipient's
                               new account.
            holder_name: Full name of the recipient (passed to Eucalyptus for
                         provisioning).
            recipient_user_id: The recipient's StarMoney user_id. REQUIRED for
                               Branch A — omitting it returns 422. Optional only
                               because Branch B (future) allows handle-only
                               recipients.

        Returns:
            DeferredTransferResponse dict.

        Raises:
            ValidationError (422): Missing recipient_user_id for Branch A, or
                invalid claim state.
            PaymentNotFoundError (404): Transfer not found.
            ServerError (502): Recipient vIBAN provisioning failed.
            APIError (501): Branch B not yet implemented.
        """
        payload: dict[str, Any] = {
            "holder_name": holder_name,
            "viban_tenant_slug": viban_tenant_slug,
        }
        if recipient_user_id is not None:
            payload["recipient_user_id"] = recipient_user_id

        response = await self.http.post(
            f"/deferred-transfers/{deferred_transfer_id}/claim",
            json=payload,
        )
        return response.json()

    async def cancel(
        self,
        deferred_transfer_id: str,
        user_id: str,
        reason: Optional[Literal["recipient_unreachable", "sender_request"]] = None,
    ) -> dict[str, Any]:
        """
        Cancel a RESERVED or ARMED deferred transfer, recovering locked funds.

        Only the sender (authenticated JWT user_id == sender_user_id) may call
        this endpoint. Returns 404 if the caller is not the sender (avoids leaking
        ownership of transfers belonging to other users).

        Branch A (RESERVED): the send-time hold is released via the outbox so
        vIBAN-ledgers restores the sender's available amount immediately.
        Branch B (ARMED): status moves to CANCELLED; no ledger touch.

        Idempotent: if already CANCELLED, returns current state without re-emitting.

        Args:
            deferred_transfer_id: UUID of the deferred transfer to cancel.
            user_id: The authenticated sender's user ID (drives JWT sub claim).
            reason: Why the sender is cancelling (B-44). ``None`` (default)
                lets the server default to ``"sender_request"``.

        Returns:
            DeferredTransferResponse dict with status='cancelled' and
            cancel_reason set to the effective reason.

        Raises:
            PaymentNotFoundError (404): Transfer not found or caller is not sender.
            DuplicateResourceError (409): Transfer cannot be cancelled (already
                claimed, settled, expired, etc.).
            ValidationError (422): ``reason`` is not one of the two accepted values.
        """
        payload: dict[str, Any] = {"reason": reason} if reason is not None else {}

        response = await self.http.post(
            f"/deferred-transfers/{deferred_transfer_id}/cancel",
            user_id=user_id,
            json=payload,
        )
        return response.json()
