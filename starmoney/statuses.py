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
