"""StarMoney SDK - Deferred Transfers Resource

Wraps the bank service's send-to-a-phone/handle endpoints:

    POST /v1/deferred-transfers/send          — sender initiates
    GET  /v1/deferred-transfers/{id}          — status read
    POST /v1/deferred-transfers/{id}/claim    — recipient claim/settle
    POST /v1/deferred-transfers/{id}/cancel   — sender cancels an un-claimed transfer

Semantic model — the bank service reserves funds on the sender's vIBAN
(``funding_source='viban_hold'``) or defers the pull until claim
(``funding_source='external_pull'``). Currency is XOF only. The recipient
is identified by an opaque handle (typically a phone number) and does not
need a StarMoney account at send time — the bank service dispatches the
claim invitation.

Positioning rules (from the bank service):
  - No 'balance', 'wallet', 'pool', 'held' vocabulary.
  - Amounts are in ``amount_minor`` (smallest currency unit).
"""

from typing import Any, Optional

from ..http_client import HTTPClient


class DeferredTransfersResource:
    """Deferred-transfer resource for send-to-handle flows.

    The chatbot / calling service is the sender's agent. The recipient
    identity is opaque at send time (handle only). The claim call is made
    by the onboarding service on the recipient's behalf.
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def send(
        self,
        user_id: str,
        client_transaction_id: str,
        recipient_handle: str,
        amount_minor: int,
        funding_source: str,
        currency: str = "XOF",
        linked_external_account_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Initiate a deferred transfer.

        Args:
            user_id: Sender's StarMoney user_id (JWT-authenticated).
            client_transaction_id: Idempotency key. Same value returns the
                same DeferredTransfer on retry.
            recipient_handle: Opaque recipient identifier — typically a
                phone number. The recipient need not have a StarMoney
                account at send time.
            amount_minor: Amount in the smallest currency unit (XOF has
                no fractional unit, so this is the whole-XOF amount).
                Must be > 0.
            funding_source: ``'viban_hold'`` (Branch A — server places a
                hold on the sender's vIBAN via vIBAN-ledgers) or
                ``'external_pull'`` (Branch B — funds pulled from a linked
                external account at claim time).
            currency: Currency code. Bank service accepts only ``'XOF'``.
            linked_external_account_id: Required iff
                ``funding_source='external_pull'``. Identifier of the
                sender's linked external funding account.

        Returns:
            DeferredTransfer response dict — ``id``, ``status`` (typically
            ``'PENDING_CLAIM'``), ``branch``, ``expires_at`` (Branch A only),
            ``created_at``, ``updated_at``.
        """
        payload = {
            "client_transaction_id": client_transaction_id,
            "recipient_handle": recipient_handle,
            "amount_minor": amount_minor,
            "currency": currency,
            "funding_source": funding_source,
            "linked_external_account_id": linked_external_account_id,
        }
        response = await self.http.post(
            "/deferred-transfers/send", json=payload, user_id=user_id
        )
        return response.json()

    async def get(
        self,
        user_id: str,
        deferred_transfer_id: str,
    ) -> dict[str, Any]:
        """Read a deferred transfer's current status.

        Args:
            user_id: The caller's StarMoney user_id (JWT-authenticated).
                Typically the sender or the onboarding service.
            deferred_transfer_id: ``id`` returned by ``send``.

        Returns:
            DeferredTransfer response dict.
        """
        response = await self.http.get(
            f"/deferred-transfers/{deferred_transfer_id}", user_id=user_id
        )
        return response.json()

    async def claim(
        self,
        user_id: str,
        deferred_transfer_id: str,
        holder_name: str,
        viban_tenant_slug: str,
        recipient_user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Claim / settle a pending deferred transfer.

        Called by the onboarding service after the recipient has opened
        a StarMoney account.

        Args:
            user_id: The onboarding service's user_id (service-authenticated).
            deferred_transfer_id: ``id`` returned by ``send``.
            holder_name: Full name of the recipient — passed to Eucalyptus
                for provisioning.
            viban_tenant_slug: vIBAN-ledgers tenant slug for the recipient's
                new account.
            recipient_user_id: Recipient's StarMoney ``user_id``. Required
                for Branch A (``viban_hold``) claims, because over-ceiling
                claims park in ``CLAIMED_PENDING_KYC`` and the VERIFIED
                relay keys on this ID. Optional at the schema layer for a
                future Branch B that allows handle-only recipients.

        Returns:
            DeferredTransfer response dict with the updated status.
        """
        payload = {
            "holder_name": holder_name,
            "viban_tenant_slug": viban_tenant_slug,
            "recipient_user_id": recipient_user_id,
        }
        response = await self.http.post(
            f"/deferred-transfers/{deferred_transfer_id}/claim",
            json=payload,
            user_id=user_id,
        )
        return response.json()

    async def cancel(
        self,
        user_id: str,
        deferred_transfer_id: str,
    ) -> dict[str, Any]:
        """Cancel an un-claimed deferred transfer (sender only).

        Only the sender may cancel. Bank enforces this via JWT — the caller
        must authenticate as the same user_id that initiated the transfer;
        otherwise the bank returns 404 (avoids leaking ownership).

        Branch A (RESERVED): the send-time hold is released via the outbox,
        restoring the sender's available amount immediately. Branch B
        (ARMED): status moves to CANCELLED with no ledger touch.

        State guard (CAS): cancel is allowed ONLY from ``RESERVED`` or
        ``ARMED``. Any other status (``CLAIMED``, ``CLAIMED_PENDING_KYC``,
        ``SETTLED``, ``EXPIRED``, ``RELEASED``, ``CANCELLED``) returns 409
        from the bank with the current status in the response detail.
        Idempotent: cancelling an already-``CANCELLED`` transfer returns
        the current state without re-emitting the hold-release event.

        Args:
            user_id: Sender's StarMoney user_id (JWT-authenticated). Must
                match the transfer's ``sender_user_id`` or the bank returns
                404.
            deferred_transfer_id: ``id`` returned by ``send``.

        Returns:
            DeferredTransfer response dict with the updated status.
        """
        response = await self.http.post(
            f"/deferred-transfers/{deferred_transfer_id}/cancel",
            user_id=user_id,
        )
        return response.json()
