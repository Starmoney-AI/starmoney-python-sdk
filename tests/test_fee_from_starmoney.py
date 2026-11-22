"""Fee from the StarMoney vIBAN: debits[] breakdown, fee_source, FEE_FUNDS_INSUFFICIENT."""

from typing import get_type_hints
from unittest.mock import MagicMock

import httpx
import pytest
import starmoney
from starmoney import FeeFundsInsufficientError, transfer_history
from starmoney.exceptions import APIError
from starmoney.http_client import HTTPClient
from starmoney.transfer_history import TransferHistoryRow
from starmoney.webhooks import payloads


def _handle(status: int, body: dict) -> None:
    response = httpx.Response(
        status, json=body, request=httpx.Request("POST", "http://x/v1/payments")
    )
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


def test_fee_funds_insufficient_is_typed_and_carries_the_three_figures():
    body = {
        "error_code": "FEE_FUNDS_INSUFFICIENT",
        "kind": "state",
        "message": "the StarMoney account cannot cover the fee",
        "starmoney_fee_minor": 1000,
        "available_minor": 400,
        "shortfall_minor": 600,
    }
    with pytest.raises(FeeFundsInsufficientError) as exc:
        _handle(402, body)
    err = exc.value
    assert isinstance(err, APIError)
    assert (err.status_code, err.error_code) == (402, "FEE_FUNDS_INSUFFICIENT")
    assert (err.starmoney_fee_minor, err.available_minor, err.shortfall_minor) == (1000, 400, 600)


def test_names_are_exported():
    assert {
        "FeeFundsInsufficientError",
        "Debit",
        "DebitLine",
        "DebitLineKind",
        "DebitAccount",
        "FeeSource",
    } <= set(starmoney.__all__)
    assert starmoney.FeeSource.__args__ == ("starmoney", "paying_account")
    assert starmoney.DebitLineKind.__args__ == ("amount", "bank_fee", "starmoney_fee", "rtgs_fee")
    assert starmoney.DebitAccount.__args__ == ("linked", "starmoney")


def test_failure_reason_has_fee_funds_insufficient():
    assert "fee_funds_insufficient" in starmoney.PaymentFailureReason.__args__


def test_debit_shape():
    hints = get_type_hints(payloads.Debit, globalns=vars(payloads))
    assert {"account", "institution", "link_id", "total_minor", "lines"} <= set(hints)
    assert set(payloads.DebitLine.__annotations__) == {"kind", "amount_minor", "collected_by"}


@pytest.mark.parametrize(
    "typed",
    [
        payloads.FeeLine,
        payloads.PaymentInitiatedPayload,
        payloads.PaymentRailFailedPayload,
        payloads.PaymentBankStatusPayload,
    ],
)
def test_fee_line_and_payment_payloads_carry_debits_and_fee_source(typed):
    hints = get_type_hints(typed, globalns=vars(payloads))
    assert {"debits", "fee_source"} <= set(hints)


def test_transfer_history_rows_carry_debits_and_fee_source():
    hints = get_type_hints(TransferHistoryRow, globalns=vars(transfer_history))
    assert {"debits", "fee_source"} <= set(hints)


def test_deferred_transfer_surfaces_carry_debits_and_fee_source():
    """A transfer scheduled from a linked account has StarMoney's fee taken from the sender's
    StarMoney vIBAN when it executes: the read, the list row and deferred_transfer.sent show it."""
    from starmoney.resources import deferred_transfers

    for typed in (deferred_transfers.DeferredTransferListItem, deferred_transfers.DeferredTransferRead):
        hints = get_type_hints(typed, globalns=vars(deferred_transfers))
        assert {"debits", "fee_source"} <= set(hints)
    hints = get_type_hints(payloads.DeferredTransferSentPayload, globalns=vars(payloads))
    assert {"debits", "fee_source"} <= set(hints)
