"""SDK unit tests — WebhookEvent catalog + typed payloads (PR #101 bump).

Drift guard: these constants are a hand-synced mirror of
``app/core/events/types.py`` (``EVENT_CONFIGS``, ``can_broadcast=True``) in
the starmoney-bank-service monorepo. This SDK is published standalone (no
import of the server package is possible once split into
``Starmoney-AI/starmoney-python-sdk``), so the comparison here is against the
literal wire strings copied from the server catalog at bump time — not a
live cross-repo import. If the server catalog changes, this file must be
updated by hand in the same PR that bumps the SDK.
"""

from __future__ import annotations

from starmoney.webhooks import (
    DeferredTransferSentPayload,
    PaymentReceivedPayload,
    WebhookEvent,
    WebhookMetadata,
)

# ---------------------------------------------------------------------------
# The two new events (transfer-notifications work, PR #101) — exact literal
# strings the server emits (docs/WEBHOOK_EVENTS.md §5 / app/core/events/types.py).
# ---------------------------------------------------------------------------


def test_deferred_transfer_sent_matches_server_string():
    assert WebhookEvent.DEFERRED_TRANSFER_SENT == "deferred_transfer.sent"
    assert WebhookEvent.DEFERRED_TRANSFER_SENT.value == "deferred_transfer.sent"


def test_payment_received_matches_server_string():
    assert WebhookEvent.PAYMENT_RECEIVED == "payment.received"
    assert WebhookEvent.PAYMENT_RECEIVED.value == "payment.received"


def test_webhook_event_members_are_plain_strings():
    """WebhookEvent members must drop straight into a JSON request body."""
    assert isinstance(WebhookEvent.PAYMENT_RECEIVED, str)
    assert isinstance(WebhookEvent.DEFERRED_TRANSFER_SENT, str)


# ---------------------------------------------------------------------------
# Full broadcastable catalog drift check (16 events, 5 domains — see
# docs/WEBHOOK_EVENTS.md §5 in the monorepo).
# ---------------------------------------------------------------------------

_EXPECTED_BROADCASTABLE_EVENTS = {
    # Payment lifecycle
    "payment.initiated",
    "payment.accepted",
    "payment.completed",
    "payment.failed",
    "payment.cancelled",
    "payment.expired",
    # UP3 Mandate audit
    "payment.mandate.submitted",
    "payment.mandate.settled",
    "payment.mandate.rejected",
    "payment.mandate.failed",
    # Deferred transfer
    "deferred_transfer.sent",
    "deferred_transfer.settled",
    # Account lifecycle (ADR-002)
    "account.opened",
    "account.kyc.verified",
    "account.kyc.review_required",
    # Inbound credit
    "payment.received",
}


def test_webhook_event_catalog_matches_server_broadcastable_set():
    actual = {member.value for member in WebhookEvent}
    assert actual == _EXPECTED_BROADCASTABLE_EVENTS
    assert len(_EXPECTED_BROADCASTABLE_EVENTS) == 16


# ---------------------------------------------------------------------------
# Typed payloads accept a realistic delivered body (structural — TypedDict
# does no runtime validation, but this exercises the exact key set a
# consumer would parse off the wire).
# ---------------------------------------------------------------------------


def test_deferred_transfer_sent_payload_accepts_realistic_body():
    body: DeferredTransferSentPayload = {
        "event_type": "deferred_transfer.sent",
        "timestamp": "2026-08-27T10:00:00Z",
        "correlation_id": "corr-1",
        "transaction_id": "dt-notify-001",
        "client_transaction_id": "ctid-notify-001",
        "user_id": "user-alice",
        "created_by_service": "whatsapp-chatbot",
        "recipient_handle": "+22170000001",
        "amount_minor": 5_000,
        "currency": "XOF",
        "sender_display_name": "Alice",
        "notification_copy": "Alice sent you 5,000 XOF — open to receive",
        "client_reference": "bot_557712",
        "metadata": {
            "service": "starmoney-bank-service",
            "version": "1.0.0",
            "subscription_id": "sub-1",
        },
    }

    assert body["event_type"] == WebhookEvent.DEFERRED_TRANSFER_SENT
    assert body["recipient_handle"] == "+22170000001"
    assert body["amount_minor"] == 5_000
    assert "balance" not in body
    assert "wallet" not in {k.lower() for k in body}


def test_deferred_transfer_sent_payload_omits_optional_client_reference():
    body: DeferredTransferSentPayload = {
        "event_type": "deferred_transfer.sent",
        "timestamp": "2026-08-27T10:00:00Z",
        "correlation_id": "corr-2",
        "transaction_id": "dt-notify-002",
        "client_transaction_id": "ctid-notify-002",
        "user_id": "user-bob",
        "created_by_service": "adita",
        "recipient_handle": "+22170000002",
        "amount_minor": 1_000,
        "currency": "XOF",
        "sender_display_name": "Bob",
        "notification_copy": "Bob sent you 1,000 XOF — open to receive",
        "metadata": {
            "service": "starmoney-bank-service",
            "version": "1.0.0",
            "subscription_id": "sub-2",
        },
    }

    assert "client_reference" not in body


def test_payment_received_payload_accepts_realistic_body():
    """Matches the frozen example in docs/WEBHOOK_EVENTS.md §5."""
    body: PaymentReceivedPayload = {
        "event_type": "payment.received",
        "timestamp": "2026-08-27T10:00:00Z",
        "correlation_id": "corr-3",
        "transaction_id": "corr-3",
        "client_transaction_id": None,
        "user_id": "user-fatou",
        "created_by_service": "adita",
        "account_reference": "SN12Kx…xx754",
        "amount_minor": 500_000,
        "currency": "XOF",
        "source": "eucalyptus",
        "source_bank_code": "BDK",
        "value_date": "2026-08-27",
        "sender_name": None,
        "source_bank_name": "SOCIETE GENERALE SENEGAL",
        "client_reference": "bot_557712",
        "metadata": {
            "service": "starmoney-bank-service",
            "version": "1.0.0",
            "subscription_id": "sub-3",
        },
    }

    assert body["event_type"] == WebhookEvent.PAYMENT_RECEIVED
    assert body["client_transaction_id"] is None
    assert "x" in body["account_reference"]  # masked, never the full IBAN/RIB
    assert "balance" not in body


def test_payment_received_payload_omits_optional_client_reference():
    body: PaymentReceivedPayload = {
        "event_type": "payment.received",
        "timestamp": "2026-08-27T10:00:00Z",
        "correlation_id": "corr-4",
        "transaction_id": "corr-4",
        "client_transaction_id": None,
        "user_id": "user-fatou",
        "created_by_service": "adita",
        "account_reference": "SN12Kx…xx754",
        "amount_minor": 500_000,
        "currency": "XOF",
        "source": "eucalyptus",
        "source_bank_code": "BDK",
        "value_date": "2026-08-27",
        "metadata": {
            "service": "starmoney-bank-service",
            "version": "1.0.0",
            "subscription_id": "sub-4",
        },
    }

    assert "client_reference" not in body


def test_webhook_metadata_shape():
    meta: WebhookMetadata = {
        "service": "starmoney-bank-service",
        "version": "1.0.0",
        "subscription_id": "sub-5",
    }
    assert set(meta.keys()) == {"service", "version", "subscription_id"}
