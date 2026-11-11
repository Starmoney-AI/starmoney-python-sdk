"""Fee grid v2 (0.3.22): segment + funding_rail on the fee line, FUNDING_RAIL_CHANGED."""

from typing import get_type_hints
from unittest.mock import MagicMock

import httpx
import pytest
import starmoney
from starmoney import FundingRailChangedError, transfer_history
from starmoney.exceptions import APIError
from starmoney.http_client import HTTPClient
from starmoney.transfer_history import TransferHistoryRow
from starmoney.webhooks import payloads


def _handle(status: int, body: dict) -> None:
    response = httpx.Response(
        status, json=body, request=httpx.Request("POST", "http://x/v1/payments")
    )
    HTTPClient._handle_error(MagicMock(spec=HTTPClient), response)


def test_funding_rail_changed_raises_a_typed_error_naming_both_rails():
    body = {
        "error_code": "FUNDING_RAIL_CHANGED",
        "kind": "state",
        "message": "funding rail changed from viban to bdk",
        "quoted_funding_rail": "viban",
        "current_funding_rail": "bdk",
    }
    with pytest.raises(FundingRailChangedError) as exc:
        _handle(409, body)
    err = exc.value
    assert isinstance(err, APIError)
    assert (err.status_code, err.error_code, err.kind) == (409, "FUNDING_RAIL_CHANGED", "state")
    assert (err.quoted_funding_rail, err.current_funding_rail) == ("viban", "bdk")


def test_the_error_and_the_literals_are_exported():
    assert "FundingRailChangedError" in starmoney.__all__
    assert {"FeeSegment", "FundingRail"} <= set(starmoney.__all__)
    assert starmoney.FundingRail.__args__ == ("viban", "bdk")
    assert starmoney.FeeSegment.__args__ == ("p2p", "b2c", "b2b", "marketplace")


@pytest.mark.parametrize(
    "typed",
    [
        payloads.FeeLine,
        payloads.PaymentInitiatedPayload,
        payloads.PaymentRailFailedPayload,
        payloads.PaymentBankStatusPayload,
    ],
)
def test_the_fee_line_and_every_payment_payload_carry_segment_and_funding_rail(typed):
    hints = get_type_hints(typed, globalns=vars(payloads))
    assert {"segment", "funding_rail"} <= set(hints)


def test_transfer_history_rows_carry_segment_and_funding_rail():
    hints = get_type_hints(TransferHistoryRow, globalns=vars(transfer_history))
    assert {"segment", "funding_rail"} <= set(hints)
