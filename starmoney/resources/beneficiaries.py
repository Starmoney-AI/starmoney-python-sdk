"""StarMoney SDK - Beneficiaries Resource"""

from typing import Any, Optional

from ..http_client import HTTPClient


class BeneficiariesResource:
    """
    Beneficiaries resource for managing payment beneficiaries.

    Handles full CRUD for beneficiaries:
    - Creating, listing, getting, updating, deleting beneficiaries
    - Toggling favorite status
    - Validating IBANs
    """

    def __init__(self, http_client: HTTPClient):
        self.http = http_client

    async def create(
        self,
        user_id: str,
        name: str,
        iban: str,
        bank_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        is_favorite: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create a new beneficiary for user.

        Args:
            user_id: User ID who owns this beneficiary.
            name: Beneficiary display name.
            iban: Beneficiary's IBAN (validated server-side via ISO 13616).
            bank_name: Bank or financial institution name.
            phone_number: Optional phone number in international format.
            email: Optional email address.
            is_favorite: Whether to mark as favorite immediately (default False).
            metadata: Additional beneficiary metadata dict.

        Returns:
            BeneficiaryResponse dict with keys:
              id, name, iban, phone_number, email, bank_name, is_favorite,
              is_active, metadata, created_at, updated_at.

        Raises:
            ValidationError (422): Invalid IBAN format or phone number.
            DuplicateResourceError (409): Duplicate beneficiary for this user.
        """
        payload: dict[str, Any] = {
            "name": name,
            "iban": iban,
            "is_favorite": is_favorite,
        }
        if bank_name is not None:
            payload["bank_name"] = bank_name
        if phone_number is not None:
            payload["phone_number"] = phone_number
        if email is not None:
            payload["email"] = email
        if metadata is not None:
            payload["metadata"] = metadata

        response = await self.http.post("/beneficiaries", json=payload, user_id=user_id)
        return response.json()

    async def list(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 50,
        include_inactive: bool = False,
    ) -> dict[str, Any]:
        """
        List beneficiaries for a user with pagination.

        Results are ordered by favorites first, then by creation date descending.

        Args:
            user_id: User ID to list beneficiaries for.
            page: Page number (1-based, default 1).
            page_size: Items per page (max 100, default 50).
            include_inactive: If True, include soft-deleted beneficiaries.

        Returns:
            BeneficiaryListResponse dict with keys:
              beneficiaries (list), total_count, page, page_size, has_next.
        """
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "include_inactive": str(include_inactive).lower(),
        }
        response = await self.http.get("/beneficiaries", params=params, user_id=user_id)
        return response.json()

    async def get(self, user_id: str, beneficiary_id: str) -> dict[str, Any]:
        """
        Get a specific beneficiary by ID.

        Only returns beneficiaries owned by the authenticated user.

        Args:
            user_id: Authenticated user's ID.
            beneficiary_id: UUID of the beneficiary.

        Returns:
            BeneficiaryResponse dict.

        Raises:
            PaymentNotFoundError (404): Beneficiary not found or not owned by user.
        """
        response = await self.http.get(
            f"/beneficiaries/{beneficiary_id}",
            user_id=user_id,
        )
        return response.json()

    async def update(
        self,
        user_id: str,
        beneficiary_id: str,
        *,
        name: Optional[str] = None,
        iban: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
        bank_name: Optional[str] = None,
        is_favorite: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Update a beneficiary.

        Only the provided (non-None) fields are sent. Only allows updating
        beneficiaries owned by the authenticated user.

        Args:
            user_id: Authenticated user's ID.
            beneficiary_id: UUID of the beneficiary to update.
            name: New display name.
            iban: New IBAN (validated server-side).
            phone_number: New phone number.
            email: New email.
            bank_name: New bank name.
            is_favorite: New favorite status.
            metadata: New metadata dict.

        Returns:
            Updated BeneficiaryResponse dict.

        Raises:
            PaymentNotFoundError (404): Beneficiary not found.
            ValidationError (422): Invalid IBAN or phone number.
        """
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if iban is not None:
            payload["iban"] = iban
        if phone_number is not None:
            payload["phone_number"] = phone_number
        if email is not None:
            payload["email"] = email
        if bank_name is not None:
            payload["bank_name"] = bank_name
        if is_favorite is not None:
            payload["is_favorite"] = is_favorite
        if metadata is not None:
            payload["metadata"] = metadata

        response = await self.http.put(
            f"/beneficiaries/{beneficiary_id}",
            json=payload,
            user_id=user_id,
        )
        return response.json()

    async def delete(self, user_id: str, beneficiary_id: str) -> dict[str, Any]:
        """
        Soft-delete (deactivate) a beneficiary.

        The beneficiary remains in the database but is marked inactive.
        Only allows deleting beneficiaries owned by the authenticated user.

        Args:
            user_id: Authenticated user's ID.
            beneficiary_id: UUID of the beneficiary to delete.

        Returns:
            Confirmation dict: {"message": "Beneficiary deleted successfully"}.

        Raises:
            PaymentNotFoundError (404): Beneficiary not found.
        """
        response = await self.http.delete(
            f"/beneficiaries/{beneficiary_id}",
            user_id=user_id,
        )
        return response.json()

    async def toggle_favorite(
        self,
        user_id: str,
        beneficiary_id: str,
        is_favorite: bool,
    ) -> dict[str, Any]:
        """
        Toggle the favorite status of a beneficiary.

        Uses PATCH /v1/beneficiaries/{id}/favorite.

        Args:
            user_id: Authenticated user's ID.
            beneficiary_id: UUID of the beneficiary.
            is_favorite: True to favorite, False to unfavorite.

        Returns:
            Updated BeneficiaryResponse dict.

        Raises:
            PaymentNotFoundError (404): Beneficiary not found.
        """
        payload = {"is_favorite": is_favorite}
        response = await self.http.request(
            "PATCH",
            f"/beneficiaries/{beneficiary_id}/favorite",
            json=payload,
            user_id=user_id,
        )
        return response.json()

    async def validate_iban(self, iban: str) -> dict[str, Any]:
        """
        Validate IBAN format without authentication.

        Args:
            iban: IBAN string to validate.

        Returns:
            dict with keys:
              - iban: The submitted IBAN.
              - is_valid: bool.
              - message: Human-readable result.
        """
        response = await self.http.get(
            "/beneficiaries/validate/iban",
            params={"iban": iban},
        )
        return response.json()
