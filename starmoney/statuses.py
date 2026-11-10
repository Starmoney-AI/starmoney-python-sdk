"""Typed values for response fields: POST /v1/payments `status`, and
GET /v1/accounts/status `account_state`.

(Original note, payments:) Typed values for the `status` field of a POST /v1/payments response.

Members are plain strings (``str, Enum``) so they compare equal to the raw JSON
value: ``resp["status"] == PaymentResponseStatus.ALREADY_FAILED`` works, as does
``PaymentResponseStatus(resp["status"])``. The API returns the value lowercase
(e.g. ``"already_failed"``); use :meth:`parse` to be case-tolerant.
"""

from enum import Enum


class PaymentResponseStatus(str, Enum):
    # A new payment was created (HTTP 201).
    VALIDATED = "validated"
    # Stored outcomes (HTTP 200) — a same-seed replay of a mandated send. Nothing
    # was executed again; the response carries the ORIGINAL payment (ADR-005).
    ALREADY_IN_PROGRESS = "already_in_progress"  # original still in flight
    ALREADY_COMPLETED = "already_completed"  # original settled
    ALREADY_FAILED = "already_failed"  # original failed/cancelled — re-confirm with a NEW seed

    @classmethod
    def parse(cls, value: str) -> "PaymentResponseStatus":
        """Case-insensitive parse of a response `status` value."""
        return cls(str(value).lower())

    @property
    def is_stored_outcome(self) -> bool:
        return self is not PaymentResponseStatus.VALIDATED


class AccountState(str, Enum):
    """The closed set of ``account_state`` values on GET /v1/accounts/status.

    captured → active_pre_kyc → kyc_pending → verified; closed is terminal.
    There is no "refused" state.
    """

    CAPTURED = "captured"  # holder record only; no vIBAN yet
    ACTIVE_PRE_KYC = "active_pre_kyc"  # vIBAN live; pre-KYC limits apply
    KYC_PENDING = "kyc_pending"  # documents submitted; awaiting the bank
    VERIFIED = "verified"  # bank-adjudicated; limits lifted (« sans limite »)
    CLOSED = "closed"  # terminal

    @property
    def has_viban(self) -> bool:
        return self in (
            AccountState.ACTIVE_PRE_KYC,
            AccountState.KYC_PENDING,
            AccountState.VERIFIED,
        )


class HolderStatus(str, Enum):
    """``holder_status`` (B-90): the bank-defined word to show a customer.

    Deprecated since 0.3.18: read ``account_status`` + ``verification_status``
    (B-94, ``AccountStatus`` / ``VerificationStatus``) instead.

    On GET /v1/accounts/status and GET /v1/accounts/status/by-phone/{phone}.
    Derived from ``account_state``; the bank owns the set, consumers map to it
    and infer nothing. ``can_send`` rides next to it on both reads.
    """

    NONE = "none"  # the bank knows nothing about this phone / user
    INVITED = "invited"  # no account; another holder is waiting on this number
    OPENING = "opening"  # account creation started (captured); no vIBAN yet
    UNCHECKED = "unchecked"  # vIBAN live; identity check not done; sends under limits
    CHECKING = "checking"  # documents with the bank; sends under limits
    VERIFIED = "verified"  # identity check done; no limits
    CLOSED = "closed"  # terminal

    @property
    def can_send(self) -> bool:
        return self in (HolderStatus.UNCHECKED, HolderStatus.CHECKING, HolderStatus.VERIFIED)

    @property
    def has_account(self) -> bool:
        return self not in (HolderStatus.NONE, HolderStatus.INVITED)


class AccountStatus(str, Enum):
    """``account_status`` (B-94): the account's own status, market-standard words.

    On both status reads, next to ``verification_status``. Example: Awa opens her
    account → active / not_started (she sends under the pre-KYC limits); she sends
    her ID → active / pending; BDK approves → active / verified, no limits.
    """

    NONE = "none"  # the bank knows nothing about this phone / user
    INVITED = "invited"  # no account; another holder is waiting on this number
    PENDING = "pending"  # account opening; no vIBAN yet
    ACTIVE = "active"  # vIBAN live (can_send says whether it may send now)
    CLOSED = "closed"  # terminal


class VerificationStatus(str, Enum):
    """``verification_status`` (B-94): the identity check (KYC). Null when there
    is no account to check (``account_status`` none or closed)."""

    NOT_STARTED = "not_started"  # no documents yet; pre-KYC limits apply
    PENDING = "pending"  # documents with the bank; pre-KYC limits apply
    VERIFIED = "verified"  # identity checked; no limits


class DeferredTransferStatus(str, Enum):
    """``status`` of a deferred transfer (send / claim / list / status reads).

    reserved → claimed → settling → settled; claimed_pending_kyc waits for KYC.
    SETTLED means SENT (BDK accepted, sender debited) — the recipient's credit
    comes as their own payment.received. settling is NOT cancellable.
    A transfer funded from the sender's BDK account (``external_pull``) is ``armed``
    until the recipient opens an account, then pulls; if the bank refuses it ends
    ``failed`` (the sender's ``payment.failed`` says nothing was taken).
    """

    RESERVED = "reserved"
    ARMED = "armed"
    CLAIMED = "claimed"
    CLAIMED_PENDING_KYC = "claimed_pending_kyc"
    SETTLING = "settling"  # the BDK virement is in flight
    SETTLED = "settled"
    EXPIRED = "expired"
    RELEASED = "released"  # the hold was released; the sender has the money back
    CANCELLED = "cancelled"
    FAILED = "failed"  # Branch B: the bank refused the pull at the claim; nothing was taken
