"""StarMoney SDK - Webhook Event Catalog

Discoverable, typo-safe constants for every event a consumer (adita, an ERP,
a third-party fintech, an AI agent) may subscribe to via
``POST /v1/webhook-subscriptions``.

Source of truth: ``app/core/events/types.py`` (``EVENT_CONFIGS``) in the
starmoney-bank-service repo — an event is subscribable **iff** its config has
``can_broadcast=True``. This enum is a hand-synced mirror of that set (there
is no cross-repo import: this SDK is published standalone to
``Starmoney-AI/starmoney-python-sdk`` / PyPI as ``starmoney-python`` and must
not depend on the server package). See ``docs/WEBHOOK_EVENTS.md`` for the full
catalog with payload shapes, auth rules, and delivery envelope.

``payment.fee_refunded`` joined the catalog with the automatic fee refund;
``payment.reversed`` with the return of a refused send's principal (B-75).
"""

from __future__ import annotations

from enum import Enum


class WebhookEvent(str, Enum):
    """Every event type you may pass to ``webhooks.create_subscription`` /
    ``webhooks.batch_subscribe`` (or the raw ``event_types`` list on
    ``POST /v1/webhook-subscriptions``).

    Members are plain strings (``str, Enum``) so they drop straight into a
    JSON request body — ``WebhookEvent.PAYMENT_RECEIVED == "payment.received"``.
    """

    # -----------------------------------------------------------------
    # Payment lifecycle — sensitivity: SERVICE_PRIVATE
    # -----------------------------------------------------------------
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_ACCEPTED = "payment.accepted"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_CANCELLED = "payment.cancelled"
    PAYMENT_EXPIRED = "payment.expired"

    # -----------------------------------------------------------------
    # Fee refund — sensitivity: USER_PRIVATE
    # -----------------------------------------------------------------
    PAYMENT_FEE_REFUNDED = "payment.fee_refunded"
    """The fee of a quoted vIBAN send came back: BDK accepted the send, then
    refused it (``payment.failed`` with ``funds="debited_under_review"`` and
    ``fee_refund="pending"``), and the ledger posted the refund. Carries the
    refunded ``fee_lines`` and ``fee_total_minor``. The principal stays under
    review and is not part of this event. Delivered to the sending service."""

    # -----------------------------------------------------------------
    # Principal returned (B-75) — sensitivity: USER_PRIVATE
    # -----------------------------------------------------------------
    PAYMENT_REVERSED = "payment.reversed"
    """The bank returned the principal of a send it had refused after accepting
    it (``payment.failed`` with ``funds="debited_under_review"``), and the ledger
    booked the return. Carries ``amount_minor`` (the principal), the fee brought
    back by this event (``fee_returned_minor``, 0 when ``payment.fee_refunded``
    already returned it) and ``fee_refunded_earlier``. Delivered to the sending
    service."""

    # -----------------------------------------------------------------
    # UP3 Mandate audit trail — sensitivity: SERVICE_PRIVATE
    # Each payload IS the full signed UP3 PaymentMandate envelope.
    # -----------------------------------------------------------------
    PAYMENT_MANDATE_SUBMITTED = "payment.mandate.submitted"
    PAYMENT_MANDATE_SETTLED = "payment.mandate.settled"
    PAYMENT_MANDATE_REJECTED = "payment.mandate.rejected"
    PAYMENT_MANDATE_FAILED = "payment.mandate.failed"

    # -----------------------------------------------------------------
    # Deferred transfer — sensitivity: SERVICE_PRIVATE
    # -----------------------------------------------------------------
    DEFERRED_TRANSFER_SENT = "deferred_transfer.sent"
    """"X sent you N FCFA — open to receive." Delivered only to the sending
    service (owner-routed). Carries the recipient's raw handle (phone
    number) — not masked, since delivery is already owner-gated."""

    DEFERRED_TRANSFER_SETTLED = "deferred_transfer.settled"
    """DEPRECATED since 0.1.22 — no longer emitted. A claimed transfer settles as
    an ordinary payment: follow ``payment.initiated`` / ``payment.completed`` /
    ``payment.failed``, which carry ``deferred_transfer_id``."""

    DEFERRED_TRANSFER_EXPIRED = "deferred_transfer.expired"
    """The transfer expired unpaid and the hold was released: the money is back
    with the sender. ``reason_code``: ``not_claimed`` | ``recipient_kyc_incomplete``."""

    DEFERRED_TRANSFER_CANCELLED = "deferred_transfer.cancelled"
    """The sender cancelled before the claim; the hold was released (money back).
    ``reason_code``: ``cancelled_by_sender``."""

    DEFERRED_TRANSFER_FAILED = "deferred_transfer.failed"
    """A pull-funded (best-effort) transfer ended ``failed``: BDK refused the pull
    from the sender's account at the claim, or the pull payment failed. Nothing
    was taken and nothing is retried. Carries ``recipient_handle`` so the consumer
    can tell the recipient. ``reason_code``: ``bdk_refused`` | ``payment_failed``."""

    # -----------------------------------------------------------------
    # Account lifecycle — sensitivity: USER_PRIVATE (ADR-002)
    # -----------------------------------------------------------------
    ACCOUNT_OPENED = "account.opened"
    ACCOUNT_KYC_VERIFIED = "account.kyc.verified"
    ACCOUNT_KYC_REVIEW_REQUIRED = "account.kyc.review_required"

    # -----------------------------------------------------------------
    # Beneficiaries by phone — sensitivity: USER_PRIVATE (B-27)
    # -----------------------------------------------------------------
    BENEFICIARY_ADDED = "beneficiary.added"
    """A pending beneficiary request became a beneficiary: the number's holder
    opened a StarMoney account. Delivered to the saver's own service; carries
    the saver's label and the new vIBAN, nothing about the holder."""

    BENEFICIARY_REQUEST_EXPIRED = "beneficiary_request.expired"
    """Nobody opened an account for the saved number within 7 days. Delivered
    to the saver's own service; ``reason`` is ``no_account``."""

    # -----------------------------------------------------------------
    # Inbound credit — sensitivity: USER_PRIVATE
    # -----------------------------------------------------------------
    PAYMENT_RECEIVED = "payment.received"
    """An inbound credit landed on the account ("you received money").
    Delivered to the credited account's owning service; ``account_reference``
    is MASKED. No ``balance`` field — a transaction-log notification, never a
    derived balance push."""


__all__ = ["WebhookEvent"]
