"""StarMoney SDK - Accounts Resource"""

from datetime import datetime
from typing import Any, Dict, Optional

from ..http_client import HTTPClient


class AccountsResource:
    """
    Accounts resource for user account management.

    Handles:
    - Creating user accounts
    - Linking payment rails to accounts
    - vIBAN provisioning
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
    ) -> dict[str, Any]:
        """
        Create a new user account.

        Args:
            first_name: User's first name
            last_name: User's last name
            email: User's email address
            phone_number: User's phone number (E.164 format recommended)
            document_type: Document type (e.g., 'PASSPORT', 'ID_CARD')
            document_number: Document number
            address: User's address

        Returns:
            Account data including user_id

        Example:
            ```python
            account = await client.accounts.create(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                phone_number="+1234567890",
                document_type="PASSPORT",
                document_number="AB123456",
                address="123 Main St"
            )
            user_id = account["user_id"]
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

    async def provision_viban(
        self,
        viban_tenant_slug: str,
        currency: str = "XOF",
        holder_name: str = "Customer",
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Provision a vIBAN for the calling user.

        Calls Eucalyptus synchronously, ACKs account_created + account_activated
        in vIBAN-ledgers, then transitions the holder to ACTIVE_PRE_KYC. The bank
        decides independently; a non-201 from Eucalyptus returns 502 to the caller.

        Auth: user-scoped JWT required. The endpoint resolves user_id from the JWT
        sub claim server-side, so `user_id` must be provided here for the SDK to
        mint the correct user-scoped token.

        Args:
            viban_tenant_slug: Which vIBAN-ledgers tenant the account belongs to.
            currency: Currency code. Only 'XOF' is supported in v1.
            holder_name: Declared identity passed to Eucalyptus. Not verified here.
            user_id: The authenticated user's ID (used to mint the JWT sub claim).

        Returns:
            dict with keys:
              - account_reference: The vIBAN reference (StarMoney provisions the
                reference, never the funds).
              - upstream_account_id: Eucalyptus account UUID.
              - account_state: Always 'active_pre_kyc' on success.
              - correlation_id: Request correlation ID.

        Raises:
            ValidationError (400): viban_tenant_slug missing.
            AuthenticationError (401): user_id missing or JWT invalid.
            ServerError (502): Eucalyptus declined or vIBAN-ledgers ACK failed.
        """
        payload = {
            "viban_tenant_slug": viban_tenant_slug,
            "currency": currency,
            "holder_name": holder_name,
        }
        response = await self.http.post(
            "/accounts/provision-viban",
            json=payload,
            user_id=user_id,
        )
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
