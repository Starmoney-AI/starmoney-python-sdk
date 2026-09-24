"""StarMoney SDK - Typed Webhook Payloads

TypedDicts for the delivered webhook body of the two newest broadcastable
events (``deferred_transfer.sent`` / ``payment.received``, PR #101). These
describe the **flat** delivery envelope built by
``WebhookDeliveryService._create_webhook_payload`` on the server — there is
no nested ``data`` key; event-specific fields sit alongside ``event_type``,
``timestamp``, and ``correlation_id`` at the top level:

    {
      "event_type": "...",
      "timestamp": "...",
      "correlation_id": "...",
      <event-specific fields>,
      "metadata": {"service": "...", "version": "...", "subscription_id": "..."}
    }

These are structural types for editor/type-checker help — StarMoney does not
validate incoming JSON against them at runtime; verify the HMAC signature
first (``WebhookValidator``), then treat the parsed dict as one of these
shapes.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class WebhookMetadata(TypedDict):
    """The ``metadata`` sub-object present on every delivered webhook."""

    service: str
    version: str
    subscription_id: str


class _DeferredTransferSentPayloadRequired(TypedDict):
    event_type: str  # always "deferred_transfer.sent"
    timestamp: str
    correlation_id: str
    transaction_id: str  # the deferred_transfer_id
    client_transaction_id: str
    user_id: str  # sender_user_id
    created_by_service: str
    recipient_handle: str
    amount_minor: int
    currency: str
    sender_display_name: str
    notification_copy: str
    metadata: WebhookMetadata


class DeferredTransferSentPayload(_DeferredTransferSentPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.DEFERRED_TRANSFER_SENT`.

    Delivered only to the sending service (``created_by_service``-gated,
    SERVICE_PRIVATE). ``recipient_handle`` is the raw phone number — not
    masked, since delivery is already owner-only.
    """

    client_reference: str  # ADR-004: only present when the caller supplied one


class _PaymentReceivedPayloadRequired(TypedDict):
    event_type: str  # always "payment.received"
    timestamp: str
    correlation_id: str
    transaction_id: str  # internal correlation id; no transactions row exists for a credit
    client_transaction_id: None  # inbound credits have no client-supplied idempotency key
    user_id: str
    created_by_service: str
    account_reference: str  # MASKED via mask_handle — never the full IBAN/RIB
    amount_minor: int
    currency: str
    source: str
    source_bank_code: str
    value_date: str
    metadata: WebhookMetadata


class PaymentReceivedPayload(_PaymentReceivedPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.PAYMENT_RECEIVED`.

    Delivered to the credited account's owning service (``created_by_service``
    -gated, USER_PRIVATE). No ``balance`` field, ever — a transaction-log
    notification, never a derived balance push.
    """

    client_reference: str  # ADR-004: only present when the caller supplied one
    # Who paid: the deferred-transfer sender's first name on a claim credit;
    # None when unknown (Eucalyptus virements carry no payer). Absent on
    # events emitted before 0.1.17.
    sender_name: Optional[str]
    # The sending bank's name (e.g. "SOCIETE GENERALE SENEGAL"); None on an
    # internal deferred-transfer claim credit. Absent before 0.1.18.
    source_bank_name: Optional[str]


__all__ = [
    "WebhookMetadata",
    "DeferredTransferSentPayload",
    "PaymentReceivedPayload",
]
