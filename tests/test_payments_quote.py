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
