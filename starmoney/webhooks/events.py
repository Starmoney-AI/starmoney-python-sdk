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

16 broadcastable events across five domains, as of PR #101
(``feat/transfer-notifications-3-1-3-3``).
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

    # -----------------------------------------------------------------
    # Account lifecycle — sensitivity: USER_PRIVATE (ADR-002)
    # -----------------------------------------------------------------
    ACCOUNT_OPENED = "account.opened"
    ACCOUNT_KYC_VERIFIED = "account.kyc.verified"
    ACCOUNT_KYC_REVIEW_REQUIRED = "account.kyc.review_required"

    # -----------------------------------------------------------------
    # Inbound credit — sensitivity: USER_PRIVATE
    # -----------------------------------------------------------------
    PAYMENT_RECEIVED = "payment.received"
    """An inbound credit landed on the account ("you received money").
    Delivered to the credited account's owning service; ``account_reference``
    is MASKED. No ``balance`` field — a transaction-log notification, never a
    derived balance push."""


__all__ = ["WebhookEvent"]
