"""Recipient check (bank B-41): can this phone number be credited right now?

Call it before the review screen so the customer signs the right thing: an
immediate transfer (the number already has a StarMoney account that can be
credited) or a deferred one (7-day hold).
"""

from typing import TypedDict

from ..http_client import HTTPClient


class RecipientCheck(TypedDict):
    """The whole answer. Nothing else about the number's holder is ever returned
    (no name, no IBAN, no account state)."""

    creditable: bool
    # True when the number is the caller's own. A send to yourself is refused
    # (SelfTransferNotAllowedError), so ``creditable`` is False whenever this is True.
    self: bool
    # ISO 8601 UTC: the latest ``execute_before`` a deferred transfer signed now may carry.
    execute_before_max: str


class RecipientsResource:
    """Recipient checks (user-scoped: the JWT names the asking customer)."""

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def check(self, user_id: str, phone: str) -> RecipientCheck:
        """
        Ask whether ``phone`` already has a StarMoney account that can be credited
        (``GET /v1/recipients/check``). The bank applies the same rule the deferred
        send uses, so the check and the send agree.

        Args:
            user_id: The authenticated customer asking (mints the user-scoped JWT).
            phone: Any spelling a send accepts; normalised by the bank.

        Returns:
            RecipientCheck: ``{creditable, self, execute_before_max}``.

        Raises:
            InvalidPhoneError (422 INVALID_PHONE): not a phone number
                (``errors[0].field == "phone"``). Costs no quota.
            RateLimitError (429 RECIPIENT_CHECK_LIMIT_REACHED): more than the per-user
                hourly cap (default 30); ``retry_after_seconds`` in the body.
            AuthenticationError (401): user_id missing or JWT invalid.
        """
        response = await self.http.get("/recipients/check", params={"phone": phone}, user_id=user_id)
        return response.json()
