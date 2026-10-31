"""SDK unit tests — payments.quote (transfer routes, PR-A)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from starmoney.resources.payments import PaymentsResource


@pytest.mark.asyncio
async def test_quote_posts_the_identifier_and_amount():
    http = MagicMock()
    response = MagicMock()
    response.json.return_value = {"quote": {"id": "q1", "digest": "ab", "digest_alg": "sha256-jcs-v1"}}
    http.post = AsyncMock(return_value=response)

    out = await PaymentsResource(http).quote(
        "user-1", beneficiary_type="msisdn", beneficiary_value="+221771234567", amount_minor=15000
    )

    http.post.assert_awaited_once_with(
        "/payments/quotes",
        json={
            "beneficiary": {"type": "msisdn", "value": "+221771234567"},
            "amount_minor": 15000,
            "currency": "XOF",
        },
        user_id="user-1",
    )
    assert out["quote"]["id"] == "q1"


@pytest.mark.asyncio
async def test_send_with_quote_id_posts_the_quote_and_nothing_it_does_not_know():
    """Confirm by quote (0.3.0): amount / IBAN come from the quote server-side,
    so the SDK sends only what the caller gave."""
    http = MagicMock()
    response = MagicMock()
    response.json.return_value = {"transaction_id": "t1", "quote_id": "q1", "fee_total_minor": 2500}
    http.post = AsyncMock(return_value=response)

    out = await PaymentsResource(http).send(
        "user-1", client_transaction_id="c1", quote_id="q1", beneficiary_name="Moussa N."
    )

    http.post.assert_awaited_once_with(
        "/payments",
        json={
            "currency": "XOF",
            "client_transaction_id": "c1",
            "beneficiary_name": "Moussa N.",
            "quote_id": "q1",
        },
        user_id="user-1",
    )
    assert out["fee_total_minor"] == 2500


@pytest.mark.asyncio
async def test_send_without_quote_id_still_requires_the_legacy_body():
    http = MagicMock()
    http.post = AsyncMock()
    with pytest.raises(ValueError, match="Without quote_id these are required: amount, beneficiary_iban"):
        await PaymentsResource(http).send(
            "user-1", client_transaction_id="c1", beneficiary_name="X", description="d"
        )
    http.post.assert_not_awaited()
