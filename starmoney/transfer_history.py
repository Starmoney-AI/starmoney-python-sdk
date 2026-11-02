"""Typed shape of ``GET /v1/accounts/transfers`` (``accounts.get_transfer_history``).

One newest-first list of BOTH directions for a holder. ``direction`` is
``"out"`` (a send StarMoney orchestrated) or ``"in"`` (an inbound credit on the
holder's vIBAN, read live from the vIBAN ledger; nothing about it is stored by
StarMoney). These are structural types for editor/type-checker help; the SDK
returns the parsed JSON dict unchanged.
"""

from __future__ import annotations

from typing import Literal, Optional, TypedDict

TransferDirection = Literal["in", "out"]


class _TransferHistoryRowBase(TypedDict):
    """Keys present on EVERY row, whichever the direction."""

    id: str  # out: the transaction row id; in: the ledger entry id (always present)
    direction: TransferDirection
    amount_minor: int  # whole XOF
    currency: str
    # in: always "completed". out: pending | processing | accepted | completed |
    # failed | cancelled.
    status: str
    date: str  # ISO 8601, UTC
    # The holder's own vIBAN, unmasked. None on an out row sent from a linked
    # (non-vIBAN) account.
    account_reference: Optional[str]
    account_label: Optional[str]  # "Compte StarMoney" when account_reference is set
    # in: who paid, when known (an in-network sender's first name; None for an
    # external credit). out: the recipient's name.
    counterparty_name: Optional[str]
    # in: always None for now (not yet ruled). out: the recipient IBAN.
    counterparty_iban: Optional[str]
    motif: Optional[str]  # in: the inbound libelle. out: the description
    # The reference both parties quote ('SM-7KQ4X-9TDB2'). On an in row: the
    # sender's, when the libelle carries it; None on a credit that predates it.
    sm_reference: Optional[str]
    customer_reference: Optional[str]  # same value as sm_reference, until 0.4.0


class TransferHistoryRow(_TransferHistoryRowBase, total=False):
    """A row of the merged list. The keys below are what an ``out`` row has always
    carried, unchanged; they are present but null on an ``in`` row (a credit has no
    transaction of ours)."""

    transaction_id: str
    client_transaction_id: Optional[str]
    from_user_id: str
    recipient_iban: str
    recipient_name: str
    amount: str
    transaction_type: str
    rail_name: str
    description: str
    created_at: str
    # Fee line of a quote-confirmed send; every key None on a legacy send.
    quote_id: Optional[str]
    settlement_rail: Optional[str]
    fees_minor: Optional[dict[str, int]]
    fee_total_minor: Optional[int]
    total_debit_minor: Optional[int]
    fee_grid_version: Optional[int]


class TransferHistoryPage(TypedDict):
    user_id: str
    transfers: list[TransferHistoryRow]
    limit: int
    # Legacy paging. Skips this many rows of the MERGED list; ignored when a
    # cursor is passed. Page with ``next_cursor`` instead.
    offset: int
    # Pass back as ``cursor=`` for the next page; None at the end of the list.
    next_cursor: Optional[str]
