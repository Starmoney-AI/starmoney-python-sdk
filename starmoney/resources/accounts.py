"""StarMoney SDK - Accounts Resource"""

from datetime import datetime
from typing import Any, Dict, Optional

from ..http_client import HTTPClient


class AccountsResource:
    """
    Accounts resource for user account management.

    Handles:
    - Opening StarMoney accounts (home vIBAN provisioned inline by `create`)
    - Linking OTHER payment rails to accounts (`link_rail`)
    - Account-status enquiry (`get_status`)
    - KYC attestation submission
    - Profile management
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def create(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone_number: str,
        document_type: str,
        document_number: str,
        address: str,
        viban_tenant_slug: Optional[str] = None,
        client_reference: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Open a StarMoney account (and provision its home vIBAN by default).

        The StarMoney account is the holder's identity record; provisioning the
        home vIBAN is StarMoney's business, done inline here — it is NOT a
        separate consumer call. To attach OTHER rails afterwards, use
        ``link_rail``. The vIBAN is the home rail; you do not "provision a
        vIBAN" as a public step.

        Args:
            first_name: User's first name
            last_name: User's last name
            email: User's email address
            phone_number: User's phone number (E.164 format recommended)
            document_type: Document type (e.g., 'PASSPORT', 'ID_CARD')
            document_number: Document number
            address: User's address
            viban_tenant_slug: Which vIBAN-ledgers tenant to provision the home
                vIBAN in. Optional — when omitted the service resolves the sole
                configured tenant. If no tenant is resolvable the holder is
                created at CAPTURED (no vIBAN; e.g. BDK-only deployments).
            client_reference: Optional opaque routing reference (ADR-004),
                echoed back verbatim on this account's lifecycle webhooks
                (account.opened / account.kyc.verified / account.kyc.review_required)
                so a multi-tenant consumer can correlate the event to its own
                context (e.g. which bot owns the conversation). Treated as opaque
                by StarMoney and delivered only back to the calling service.
                MUST NOT contain PII — it is a routing token, not user data.

        Returns:
            dict with keys:
              - user_id: The holder's ID (always present on success).
              - account_state: 'active_pre_kyc' when the home vIBAN was
                provisioned; 'captured' when it was not (bank-decision gate
                declined / no vIBAN tenant) — branch your UX on this.
              - account_reference: The home vIBAN reference when provisioned;
                null at CAPTURED. StarMoney provisions the reference, never the
                funds.

        Example:
            ```python
            account = await client.accounts.create(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                phone_number="+1234567890",
                document_type="PASSPORT",
                document_number="AB123456",
                address="123 Main St",
                viban_tenant_slug="solarbox",
            )
            user_id = account["user_id"]
            if account["account_state"] == "active_pre_kyc":
                viban = account["account_reference"]
            ```
        """
        payload = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone_number": phone_number,
            "document_type": document_type,
            "document_number": document_number,
            "address": address,
        }
        if viban_tenant_slug is not None:
            payload["viban_tenant_slug"] = viban_tenant_slug
        if client_reference is not None:
            payload["client_reference"] = client_reference

        response = await self.http.post("/accounts", json=payload)
        return response.json()

    async def link_rail(self, user_id: str, rail_name: str = "BDK") -> dict[str, Any]:
        """
        Link a payment rail to user's account.

        Args:
            user_id: User ID to link rail to
            rail_name: Payment rail name (default: 'BDK')

        Returns:
            Rail link confirmation data

        Example:
            ```python
            await client.accounts.link_rail(user_id, rail_name="BDK")
            ```
        """
        response = await self.http.post(f"/accounts/rails/{rail_name}", user_id=user_id)
        return response.json()

    async def get_transfer_history(self, user_id: str, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """
        Retrieve the authenticated user's transfer history.

        Args:
            user_id: User ID to retrieve transfer history for
            limit: number of transfers to return (default 20)
            offset: pagination offset (default 0)

        Returns:
            Parsed JSON response with transfers, limit, offset and user_id
        """
        params = {"limit": limit, "offset": offset}
        response = await self.http.get("/accounts/transfers", params=params, user_id=user_id)
        return response.json()

    async def get_user_by_phone(self, phone_number: str) -> Dict[str, Any] | None:
        """
        Retrieve a user by phone number using the accounts lookup endpoint.

        Args:
            phone_number: Phone number string to lookup (should be in E.164 or service-expected format)

        Returns:
            The parsed JSON response as a dict if found, or None if the API returns 404.
        """
        response = await self.http.get(f"/accounts/lookup/phone/{phone_number}")

        return response.json()

    async def get_user_available_rails(self, user_id: str) -> Dict[str, Any]:
        """
        Get available payment rails for the authenticated user.

        Returns the list of payment rails available to the user based on their
        stored credentials and rail configurations.

        Args:
            user_id: User ID to retrieve available rails for

        Returns:
            Parsed JSON response containing:
            - user_id: The user's ID
            - available_rails: List of rails with name, display info, and credential status
            - total_rails: Total number of rails
            - configured_rails: Number of rails with stored credentials

        Example:
            ```python
            rails = await client.accounts.get_user_available_rails(user_id)
            for rail in rails["available_rails"]:
                print(f"{rail['name']}: {rail['has_credentials']}")
            ```
        """
        response = await self.http.get("/accounts/rails", user_id=user_id)
        return response.json()

    async def get_status(self, user_id: str) -> dict[str, Any]:
        """
        Get the holder's account status (the KYC-assurance state machine).

        Answers "what's the status of my account?" — is the home vIBAN live, is
        KYC verified, is KYC still required. Returns STATE only; it never
        returns a balance (positioning: state, not funds).

        Auth: user-scoped JWT required. The endpoint resolves the user from the
        JWT sub claim, so ``user_id`` must be provided for the SDK to mint the
        correct user-scoped token.

        Args:
            user_id: The authenticated user's ID (used to mint the JWT sub claim).

        Returns:
            dict with keys:
              - user_id
              - account_state: 'captured' | 'active_pre_kyc' | 'kyc_pending'
                | 'verified' | 'closed'
              - is_provisioned: bool — a home vIBAN is live (active_pre_kyc+)
              - kyc_verified: bool — the bank has adjudicated KYC
              - kyc_required: bool — the holder must KYC to lift the ceiling
              - last_event: str | None
              - updated_at: ISO datetime | None

        Raises:
            NotFoundError (404): no account state for this user.
            AuthenticationError (401): user_id missing or JWT invalid.
        """
        response = await self.http.get("/accounts/status", user_id=user_id)
        return response.json()

    async def submit_kyc(
        self,
        user_id: str,
        attester: str,
        document_refs: dict[str, str],
        idempotency_key: str,
        attested_at: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Submit a KYC attestation for an ACTIVE_PRE_KYC account holder.

        StarMoney captures the in-person identity check and records an opaque
        document reference (no PII stored in this service). BDK adjudicates;
        the ACTIVE_PRE_KYC -> KYC_PENDING transition is recorded append-only.

        Idempotent: re-submitting the same idempotency_key returns the current
        state without re-emitting.

        Args:
            user_id: The user whose KYC is being submitted (path parameter).
            attester: Identity of the StarMoney operator performing the in-person
                      check. Not the account holder.
            document_refs: Opaque references / hashes pointing to documents in the
                           KYC-document store. No PII here.
            idempotency_key: Client-supplied idempotency key for the submission.
            attested_at: UTC datetime when the in-person check was performed.
                         Defaults to request time when omitted.

        Returns:
            dict with keys:
              - user_id: str
              - account_state: 'kyc_pending' on success; current state if already
                past ACTIVE_PRE_KYC (idempotent).
              - message: Human-readable status description.
        """
        payload: dict[str, Any] = {
            "attester": attester,
            "document_refs": document_refs,
            "idempotency_key": idempotency_key,
        }
        if attested_at is not None:
            payload["attested_at"] = attested_at.isoformat()

        response = await self.http.post(
            f"/accounts/{user_id}/kyc/submit",
            json=payload,
        )
        return response.json()

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """
        Get the current user's profile information.

        Args:
            user_id: User ID whose profile to retrieve (drives the JWT sub claim).

        Returns:
            UserProfileResponse dict with keys:
              - user_id, first_name, last_name, email, phone_number,
                kyc_status, document_type, document_number, address, created_at.
        """
        response = await self.http.get("/accounts/profile", user_id=user_id)
        return response.json()

    async def update_profile(
        self,
        user_id: str,
        *,
        email: Optional[str] = None,
        phone_number: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        document_type: Optional[str] = None,
        document_number: Optional[str] = None,
        address: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Update the current user's profile information.

        Only the provided (non-None) fields are sent in the update request.

        Args:
            user_id: User ID to update (drives the JWT sub claim).
            email: New email address.
            phone_number: New phone number (E.164 format).
            first_name: New first name.
            last_name: New last name.
            document_type: New document type.
            document_number: New document number.
            address: New address.

        Returns:
            Updated UserProfileResponse dict.
        """
        payload: dict[str, Any] = {}
        if email is not None:
            payload["email"] = email
        if phone_number is not None:
            payload["phone_number"] = phone_number
        if first_name is not None:
            payload["first_name"] = first_name
        if last_name is not None:
            payload["last_name"] = last_name
        if document_type is not None:
            payload["document_type"] = document_type
        if document_number is not None:
            payload["document_number"] = document_number
        if address is not None:
            payload["address"] = address

        response = await self.http.put("/accounts/profile", json=payload, user_id=user_id)
        return response.json()
