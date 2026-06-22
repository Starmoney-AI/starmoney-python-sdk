"""StarMoney SDK - Deferred Transfers Resource

Mirrors POST /v1/deferred-transfers/send, GET /v1/deferred-transfers/{id},
POST /v1/deferred-transfers/{id}/claim, POST /v1/deferred-transfers/{id}/cancel.
"""

from typing import Any, Literal, Optional

from ..http_client import HTTPClient


class DeferredTransfersResource:
    """
    Deferred Transfers resource (flow 01).

    A deferred transfer lets a sender push funds to a recipient who does not
    yet have a StarMoney account. The send-half places a hold on the sender's
    vIBAN (Branch A) or defers the pull (Branch B); the claim-half settles
    once the recipient onboards.

    All methods are async and mirror the endpoint contracts exactly.
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def send(
        self,
        client_transaction_id: str,
        recipient_handle: str,
        amount_minor: int,
        currency: Literal["XOF"] = "XOF",
        funding_source: Literal["viban_hold", "external_pull"] = "viban_hold",
        linked_external_account_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a deferred-trigger transfer (send-half).

        Branch A (funding_source='viban_hold'): the sender's vIBAN account is
        resolved server-side from their stored rail credentials and a hold is
        placed. No account field from the caller.

        Branch B (funding_source='external_pull'): funds are pulled from a
        linked external account at claim time. linked_external_account_id is
        required.

        Idempotent on client_transaction_id.

        Args:
            client_transaction_id: Idempotency key. Same value always returns
                                   the same DeferredTransfer.
            recipient_handle: Recipient phone or handle (opaque — the recipient
                              has no account yet).
            amount_minor: Instruction amount in the smallest currency unit (> 0).
            currency: Currency code. Only 'XOF' is accepted.
            funding_source: 'viban_hold' (Branch A, default) or 'external_pull'
                            (Branch B).
            linked_external_account_id: Branch B only. Required when
                                        funding_source='external_pull'.

        Returns:
            DeferredTransferResponse dict with keys:
              id, client_transaction_id, sender_user_id, recipient_handle,
              amount_minor, currency, branch, status, expires_at,
              created_at, updated_at.

        Raises:
            ValidationError (422): Invalid request (e.g. missing
                linked_external_account_id for Branch B, amount <= 0).
            APIError (503): vIBAN ledger service unavailable.
        """
        payload: dict[str, Any] = {
            "client_transaction_id": client_transaction_id,
            "recipient_handle": recipient_handle,
            "amount_minor": amount_minor,
            "currency": currency,
            "funding_source": funding_source,
        }
        if linked_external_account_id is not None:
            payload["linked_external_account_id"] = linked_external_account_id

        # user_id is resolved server-side from the JWT sub claim.
        response = await self.http.post("/deferred-transfers/send", json=payload)
        return response.json()

    async def get(self, deferred_transfer_id: str) -> dict[str, Any]:
        """
        Read current status of a deferred transfer by its UUID.

        Args:
            deferred_transfer_id: UUID of the deferred transfer.

        Returns:
            DeferredTransferResponse dict.

        Raises:
            PaymentNotFoundError (404): Transfer not found.
        """
        response = await self.http.get(f"/deferred-transfers/{deferred_transfer_id}")
        return response.json()

    async def claim(
        self,
        deferred_transfer_id: str,
        viban_tenant_slug: str,
        holder_name: str,
        recipient_user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Claim a RESERVED deferred transfer and settle if within pre-KYC ceiling.

        This is a service-authenticated call (relayed from the onboarding service
        carrying the recipient's details).

        Branch A (hold_backed): onboard recipient vIBAN -> ceiling check ->
          - <= ceiling: RESERVED -> CLAIMED -> SETTLED
          - > ceiling: RESERVED -> CLAIMED -> CLAIMED_PENDING_KYC (hold stays active)

        Branch B (external_pull): not yet implemented; returns 501.

        Idempotent: if the transfer is already CLAIMED/SETTLED/CLAIMED_PENDING_KYC,
        returns the current state without re-emitting.

        Args:
            deferred_transfer_id: UUID of the deferred transfer to claim.
            viban_tenant_slug: vIBAN-ledgers tenant slug for the recipient's
                               new account.
            holder_name: Full name of the recipient (passed to Eucalyptus for
                         provisioning).
            recipient_user_id: The recipient's StarMoney user_id. REQUIRED for
                               Branch A — omitting it returns 422. Optional only
                               because Branch B (future) allows handle-only
                               recipients.

        Returns:
            DeferredTransferResponse dict.

        Raises:
            ValidationError (422): Missing recipient_user_id for Branch A, or
                invalid claim state.
            PaymentNotFoundError (404): Transfer not found.
            ServerError (502): Recipient vIBAN provisioning failed.
            APIError (501): Branch B not yet implemented.
        """
        payload: dict[str, Any] = {
            "holder_name": holder_name,
            "viban_tenant_slug": viban_tenant_slug,
        }
        if recipient_user_id is not None:
            payload["recipient_user_id"] = recipient_user_id

        response = await self.http.post(
            f"/deferred-transfers/{deferred_transfer_id}/claim",
            json=payload,
        )
        return response.json()

    async def cancel(
        self,
        deferred_transfer_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """
        Cancel a RESERVED or ARMED deferred transfer, recovering locked funds.

        Only the sender (authenticated JWT user_id == sender_user_id) may call
        this endpoint. Returns 404 if the caller is not the sender (avoids leaking
        ownership of transfers belonging to other users).

        Branch A (RESERVED): the send-time hold is released via the outbox so
        vIBAN-ledgers restores the sender's available amount immediately.
        Branch B (ARMED): status moves to CANCELLED; no ledger touch.

        Idempotent: if already CANCELLED, returns current state without re-emitting.

        Args:
            deferred_transfer_id: UUID of the deferred transfer to cancel.
            user_id: The authenticated sender's user ID (drives JWT sub claim).

        Returns:
            DeferredTransferResponse dict with status='cancelled'.

        Raises:
            PaymentNotFoundError (404): Transfer not found or caller is not sender.
            DuplicateResourceError (409): Transfer cannot be cancelled (already
                claimed, settled, expired, etc.).
        """
        response = await self.http.post(
            f"/deferred-transfers/{deferred_transfer_id}/cancel",
            user_id=user_id,
        )
        return response.json()
