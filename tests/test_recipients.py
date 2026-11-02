"""SDK unit tests — RecipientsResource.check (bank B-41)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from starmoney.resources.recipients import RecipientsResource


@pytest.mark.asyncio
async def test_check_calls_the_user_scoped_path_with_the_phone():
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "creditable": True,
        "self": False,
        "execute_before_max": "2026-11-09T12:00:00Z",
    }
    http.get = AsyncMock(return_value=resp)

    result = await RecipientsResource(http).check("user-1", "+221781234567")

    http.get.assert_called_once_with(
        "/recipients/check", params={"phone": "+221781234567"}, user_id="user-1"
    )
    assert result["creditable"] is True and result["self"] is False
