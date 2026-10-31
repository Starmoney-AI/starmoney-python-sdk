"""StarMoney SDK - Typed Webhook Payloads

TypedDicts for delivered webhook bodies (deferred transfers, payment.*,
payment.received, account.*). These describe the **flat** delivery envelope built by
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

from typing import Literal, Optional, TypedDict


class FeeLine(TypedDict):
    """The fee line on every ``payment.*`` webhook of a quote-confirmed send
    (transfer routes, 0.3.0) and on the ``POST /v1/payments`` /
    ``GET /v1/payments/status/...`` responses. Absent on a legacy send (no
    quote). ``amount`` on the event stays the principal; ``total_debit_minor``
    is what left the sender (principal + both fee legs)."""

    quote_id: str
    settlement_rail: str  # "bdk.internal" (free) | "bdk.rtgs" (bank leg 2 500 F)
    fees_minor: dict[str, int]  # {"orchestrator": 0, "bank": 2500}
    fee_total_minor: int
    total_debit_minor: int
    fee_grid_version: int


# ``funds`` on ``payment.failed`` (B-49, 0.3.0) — closed vocabulary, never
# renamed: the sender's money was not taken, or it was and the books are
# under review. One generic failed push per payment (decision D25).
FundsOutcome = Literal["not_debited", "debited_under_review"]


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
    sm_reference: str  # StarMoney's reference for the customer to quote (0.3.0) — read this one
    customer_reference: str  # the same value under its 0.2.2 name; deprecated, dropped in 0.4.0
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
    sm_reference: str  # StarMoney's reference for the customer to quote (0.3.0) — read this one
    customer_reference: str  # the same value under its 0.2.2 name; deprecated, dropped in 0.4.0
    user_id: str
    created_by_service: str
    account_reference: str  # MASKED via mask_handle — never the full IBAN/RIB
    amount_minor: int
    currency: str
    source: str
    source_bank_code: str
    value_date: str
    # Who paid: the deferred-transfer sender's first name on a claim credit;
    # None when unknown (Eucalyptus virements carry no payer). Always present
    # (possibly null) since bank 0.1.17 / 0.1.18; required as of 0.1.21.
    sender_name: Optional[str]
    # The sending bank's name (e.g. "SOCIETE GENERALE SENEGAL"); None on an
    # internal deferred-transfer claim credit.
    source_bank_name: Optional[str]
    metadata: WebhookMetadata


class PaymentReceivedPayload(_PaymentReceivedPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.PAYMENT_RECEIVED`.

    Delivered to the credited account's owning service (``created_by_service``
    -gated, USER_PRIVATE). No ``balance`` field, ever — a transaction-log
    notification, never a derived balance push.
    """

    client_reference: str  # ADR-004: only present when the caller supplied one


class _DeferredTransferSettledPayloadRequired(TypedDict):
    event_type: str  # always "deferred_transfer.settled"
    timestamp: str
    correlation_id: str
    transaction_id: str  # the deferred_transfer_id
    client_transaction_id: str
    sm_reference: str  # StarMoney's reference for the customer to quote (0.3.0) — read this one
    customer_reference: str  # the same value under its 0.2.2 name; deprecated, dropped in 0.4.0
    user_id: str  # the SENDER's user id ("" before 0.1.21 / bank S-35)
    created_by_service: str
    amount_minor: int
    currency: str
    sender_account_reference: str
    recipient_account_reference: str
    recipient_handle: Optional[str]  # the handle the sender addressed
    recipient_display_name: Optional[str]  # the recipient's first name
    recipient_user_id: Optional[str]
    metadata: WebhookMetadata


class DeferredTransferSettledPayload(_DeferredTransferSettledPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.DEFERRED_TRANSFER_SETTLED`.

    Delivered only to the SENDING service (``created_by_service``-gated,
    SERVICE_PRIVATE). As of 0.1.22 it means SENT: BDK accepted the virement and
    the sender was debited. The recipient's credit arrives separately, when BDK
    reports it, as the recipient's own ``payment.received`` — StarMoney never
    settles internally.
    """

    client_reference: str  # ADR-004: only present when the caller supplied one


class _DeferredTransferClosedPayloadRequired(TypedDict):
    event_type: str  # "deferred_transfer.expired" | "deferred_transfer.cancelled"
    timestamp: str
    correlation_id: str
    transaction_id: str  # the deferred_transfer_id
    client_transaction_id: str
    user_id: str  # the SENDER's user id
    created_by_service: str
    amount_minor: int
    currency: str
    # expired: "not_claimed" | "recipient_kyc_incomplete"; cancelled: "cancelled_by_sender"
    reason_code: str
    recipient_handle: str
    recipient_user_id: Optional[str]  # set once the recipient claimed
    sm_reference: str  # StarMoney's reference for the customer to quote (0.3.0) — read this one
    customer_reference: str  # the same value under its 0.2.2 name; deprecated, dropped in 0.4.0
    metadata: WebhookMetadata


class DeferredTransferClosedPayload(_DeferredTransferClosedPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.DEFERRED_TRANSFER_EXPIRED` and
    :attr:`WebhookEvent.DEFERRED_TRANSFER_CANCELLED`.

    The transfer closed unpaid and its hold was released: the money is back
    with the sender. Delivered to the sending service (``user_id`` = sender).
    A settle that fails AFTER the claim is not reported here — it is an
    ordinary payment and ends as ``payment.failed`` with ``deferred_transfer_id``.
    """

    client_reference: str  # ADR-004: only present when the caller supplied one


DeferredTransferExpiredPayload = DeferredTransferClosedPayload
DeferredTransferCancelledPayload = DeferredTransferClosedPayload


class _PaymentInitiatedPayloadRequired(TypedDict):
    event_type: str  # always "payment.initiated"
    timestamp: str
    correlation_id: str
    transaction_id: str
    client_transaction_id: str
    user_id: str  # the paying user
    created_by_service: str
    rail_transaction_id: str  # our BDK reference ("SM-…")
    idempotency_key: str
    amount: str  # whole XOF as a string
    currency: str
    beneficiary_iban: str
    beneficiary_name: str
    rail_name: str
    initiated_at: str
    sm_reference: str  # StarMoney's reference for the customer to quote (0.3.0) — read this one
    customer_reference: str  # the same value under its 0.2.2 name; deprecated, dropped in 0.4.0
    metadata: WebhookMetadata


class PaymentInitiatedPayload(_PaymentInitiatedPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.PAYMENT_INITIATED`: BDK accepted
    the instruction (money is moving; the terminal outcome comes later)."""

    client_reference: str  # ADR-004: only present when the caller supplied one
    # Only on a deferred transfer's settle payment (0.1.22): the claimed
    # transfer this payment pays out. user_id / client_reference are the
    # original sender's.
    deferred_transfer_id: str
    # The fee line (transfer routes, 0.3.0): present only when the send confirmed
    # a quote (POST /v1/payments with quote_id); absent on a legacy send. Same
    # keys and meaning as :class:`FeeLine`.
    quote_id: str
    settlement_rail: str
    fees_minor: dict[str, int]
    fee_total_minor: int
    total_debit_minor: int
    fee_grid_version: int


class _PaymentRailFailedPayloadRequired(TypedDict):
    event_type: str  # always "payment.failed"
    timestamp: str
    correlation_id: str
    transaction_id: str
    client_transaction_id: str
    user_id: str
    created_by_service: str
    status: str  # always "FAILED"
    error: str
    failure_stage: str
    rail_name: str
    permanent_failure: bool
    failed_at: str
    amount: str
    currency: str
    beneficiary_iban: str
    beneficiary_name: str
    description: str
    external_reference: Optional[str]
    sm_reference: str  # StarMoney's reference for the customer to quote (0.3.0) — read this one
    customer_reference: str  # the same value under its 0.2.2 name; deprecated, dropped in 0.4.0
    funds: FundsOutcome  # B-49: "not_debited" here, or "debited_under_review" after a ledger refusal
    metadata: WebhookMetadata


class PaymentRailFailedPayload(_PaymentRailFailedPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.PAYMENT_FAILED` when StarMoney
    stopped the payment itself — at or before the rail call (bank refusal,
    insufficient funds, hold about to lapse). Nothing was executed.

    Compare :class:`PaymentBankStatusPayload`: a ``payment.failed`` reported
    later by BDK's status callback has that shape instead (tell them apart by
    ``"error" in body``).
    """

    client_reference: str  # ADR-004: only present when the caller supplied one
    deferred_transfer_id: str  # only on a deferred transfer's settle payment
    # The fee line (transfer routes, 0.3.0): present only when the send confirmed
    # a quote (POST /v1/payments with quote_id); absent on a legacy send. Same
    # keys and meaning as :class:`FeeLine`.
    quote_id: str
    settlement_rail: str
    fees_minor: dict[str, int]
    fee_total_minor: int
    total_debit_minor: int
    fee_grid_version: int


class _PaymentBankStatusPayloadRequired(TypedDict):
    event_type: str  # "payment.accepted" | "payment.completed" | "payment.failed"
    timestamp: str
    correlation_id: str
    transaction_id: str
    client_transaction_id: str
    user_id: str
    created_by_service: str
    rail_transaction_id: str
    idempotency_key: str
    amount: str
    currency: str
    provider: str  # "bdk"
    webhook_raw_data: dict  # BDK's callback, as received
    processed_webhook_data: dict  # {external_reference, new_status, accounting_date, message, ...}
    sm_reference: str  # StarMoney's reference for the customer to quote (0.3.0) — read this one
    customer_reference: str  # the same value under its 0.2.2 name; deprecated, dropped in 0.4.0
    metadata: WebhookMetadata


class PaymentBankStatusPayload(_PaymentBankStatusPayloadRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.PAYMENT_ACCEPTED` /
    :attr:`WebhookEvent.PAYMENT_COMPLETED` / :attr:`WebhookEvent.PAYMENT_FAILED`
    when BDK's asynchronous status callback reports the outcome."""

    client_reference: str  # ADR-004: only present when the caller supplied one
    deferred_transfer_id: str  # only on a deferred transfer's settle payment
    # B-49: on payment.failed only — the bank had accepted, so always
    # "debited_under_review" on this path.
    funds: FundsOutcome
    # The fee line (transfer routes, 0.3.0): present only when the send confirmed
    # a quote (POST /v1/payments with quote_id); absent on a legacy send. Same
    # keys and meaning as :class:`FeeLine`.
    quote_id: str
    settlement_rail: str
    fees_minor: dict[str, int]
    fee_total_minor: int
    total_debit_minor: int
    fee_grid_version: int


class _AccountLifecyclePayloadRequired(TypedDict):
    event_type: str  # account.opened | account.kyc.verified | account.kyc.review_required
    timestamp: str
    correlation_id: str
    user_id: str  # the account holder
    created_by_service: str
    account_reference: str  # the holder's vIBAN
    account_state: str  # active_pre_kyc (opened / review_required) or verified
    metadata: WebhookMetadata


class AccountLifecyclePayload(_AccountLifecyclePayloadRequired, total=False):
    """Delivered body for the account-lifecycle events (ADR-002):
    :attr:`WebhookEvent.ACCOUNT_OPENED`, :attr:`WebhookEvent.ACCOUNT_KYC_VERIFIED`
    and :attr:`WebhookEvent.ACCOUNT_KYC_REVIEW_REQUIRED` share one shape.

    Delivered to the account's owning service (USER_PRIVATE). PII-free: no
    name, document or rejection reason.
    """

    client_reference: str  # ADR-004: only present when the caller supplied one


AccountOpenedPayload = AccountLifecyclePayload


class _BeneficiaryAddedRequired(TypedDict):
    event_type: str  # beneficiary.added
    timestamp: str
    correlation_id: str
    user_id: str  # the saver
    created_by_service: str
    beneficiary_id: str
    beneficiary_request_id: str
    name: str  # the saver's own label
    phone_number: str  # E.164 (normalised)
    iban: str  # the holder's new vIBAN
    kind: str  # "starmoney"
    activated_at: str
    metadata: WebhookMetadata


class BeneficiaryAddedPayload(_BeneficiaryAddedRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.BENEFICIARY_ADDED` (B-27 contract
    §4): a pending request became a beneficiary. USER_PRIVATE, routed to the
    saver's service. ``client_reference`` only when the saver supplied one."""

    client_reference: str


class _BeneficiaryRequestExpiredRequired(TypedDict):
    event_type: str  # beneficiary_request.expired
    timestamp: str
    correlation_id: str
    user_id: str  # the saver
    created_by_service: str
    beneficiary_request_id: str
    name: str
    phone_number: str
    saved_at: str
    expired_at: str
    reason: str  # "no_account"
    metadata: WebhookMetadata


class BeneficiaryRequestExpiredPayload(_BeneficiaryRequestExpiredRequired, total=False):
    """Delivered body for :attr:`WebhookEvent.BENEFICIARY_REQUEST_EXPIRED`
    (B-27 contract §4). USER_PRIVATE, routed to the saver's service."""

    client_reference: str


AccountKycVerifiedPayload = AccountLifecyclePayload
AccountKycReviewRequiredPayload = AccountLifecyclePayload


__all__ = [
    "WebhookMetadata",
    "FeeLine",
    "FundsOutcome",
    "BeneficiaryAddedPayload",
    "BeneficiaryRequestExpiredPayload",
    "DeferredTransferSentPayload",
    "DeferredTransferSettledPayload",
    "DeferredTransferClosedPayload",
    "DeferredTransferExpiredPayload",
    "DeferredTransferCancelledPayload",
    "PaymentInitiatedPayload",
    "PaymentRailFailedPayload",
    "PaymentBankStatusPayload",
    "PaymentReceivedPayload",
    "AccountLifecyclePayload",
    "AccountOpenedPayload",
    "AccountKycVerifiedPayload",
    "AccountKycReviewRequiredPayload",
]
