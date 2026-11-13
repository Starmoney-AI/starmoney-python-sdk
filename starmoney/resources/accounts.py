"""StarMoney SDK - Accounts Resource"""

from datetime import date, datetime
from typing import Any, Dict, Optional, Union

from ..http_client import HTTPClient
from ..transfer_history import TransferHistoryPage


class AccountsResource:
    """
    Accounts resource for user account management.

    Handles:
    - Opening StarMoney accounts (home vIBAN provisioned inline by `create`)
    - Linking OTHER payment rails to accounts (`link_rail`)
    - Account-status enquiry (`get_status`)
    - The caller's own references (`resolve_self`, PR-G) — prefer it to the phone lookup
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

    async def link_rail(
        self,
        user_id: str,
        rail_name: str = "BDK",
        *,
        account_reference: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Link a payment rail to user's account.

        Args:
            user_id: User ID to link rail to
            rail_name: Payment rail name (default: 'BDK')
            account_reference: B-58 (service 0.3.13) — the IBAN of the account
                being linked, as the holder typed it. Mod-97 checked by the
                bank (``InvalidIBANError`` / 422 ``INVALID_IBAN`` with
                ``errors[0].field == "account_reference"``), stored in clear
                beside the credentials, returned on the rails listing as
                ``account.account_reference`` (full) and
                ``account.account_reference_masked`` (``SN……2706``). On an
                already-linked rail it is recorded on the existing row.
                B-95 (service 0.3.19): REQUIRED on a first BDK link — the
                bank links the account it has registered for the holder's
                phone + this IBAN, after BDK confirms it. The BDK login
                never leaves the bank.

        Returns:
            Rail link confirmation data; ``account`` is the listing's
            ``{display_name, account_reference, account_reference_masked}``
            once credentials exist, else absent/None. Never a balance.

        Raises:
            InvalidIBANError: 422 ``INVALID_IBAN`` — bad IBAN, or none given
                on a first BDK link (``errors[0].rule == "field.required"``).
            LinkableAccountNotFoundError: 404 — no registered account for
                this phone + IBAN (one answer for «not registered» and
                «another phone»).
            LinkVerificationFailedError: 409 — the registered account did not
                verify at BDK.
            InstitutionAlreadyLinkedError: 409 (B-101) — an account is already
                linked at this institution and ``account_reference`` is a
                different IBAN; ``linked_account_reference_masked`` names the
                linked one, which is unchanged. Unlink first to change it. The
                same IBAN again is 200 ``already_linked``.
            BankUnavailableError: 503 — BDK could not be reached; retry.

        Example:
            ```python
            await client.accounts.link_rail(
                user_id, rail_name="BDK", account_reference="SN11 K002 0015 …"
            )
            ```
        """
        payload: dict[str, Any] = {}
        if account_reference is not None:
            payload["account_reference"] = account_reference
        kwargs: dict[str, Any] = {"json": payload} if payload else {}
        response = await self.http.post(f"/accounts/rails/{rail_name}", user_id=user_id, **kwargs)
        return response.json()

    async def unlink_rail(self, user_id: str, rail_name: str = "BDK") -> dict[str, Any]:
        """
        Undo the holder's link on a rail (B-95, service 0.3.19).

        The bank deactivates the link (kept for audit); the rails listing then
        shows ``has_credentials: false`` and the linked balance answers
        ``RAIL_NOT_LINKED``. The holder can link the same IBAN again.

        Returns:
            ``{"rail_name": "bdk", "status": "unlinked"}``

        Raises:
            PaymentNotFoundError: the SDK's 404 class — ``RAIL_NOT_LINKED``,
                nothing is linked on that rail.

        Example:
            ```python
            await client.accounts.unlink_rail(user_id)  # BDK
            ```
        """
        response = await self.http.delete(f"/accounts/rails/{rail_name}", user_id=user_id)
        return response.json()

    async def set_rail_account_reference(
        self, user_id: str, rail_name: str, account_reference: str
    ) -> dict[str, Any]:
        """
        Record (or correct) the IBAN of the account linked on a rail (B-58).

        For a holder whose BDK account was linked before the IBAN was captured,
        the app asks once and calls this; the bank then returns it on the rails
        listing so home can show «Compte BDK · SN11 …».

        Args:
            user_id: The holder (user-scoped auth; the holder names their own
                account only)
            rail_name: Payment rail name, e.g. 'BDK'
            account_reference: The IBAN as the holder typed it (spaces fine)

        Returns:
            ``{"display_name", "account_reference", "account_reference_masked"}``

        Raises:
            InvalidIBANError: 422 ``INVALID_IBAN`` — the IBAN fails
                shape/country/length or the mod-97 check; nothing stored.
            PaymentNotFoundError: the SDK's 404 class — ``RAIL_NOT_LINKED``, the
                holder has no linked account on that rail; link first.

        Example:
            ```python
            acct = await client.accounts.set_rail_account_reference(
                user_id, "BDK", "SN11 K002 0015 2000 0000 0000 0777"
            )
            acct["account_reference_masked"]  # "SN……2706"
            ```
        """
        response = await self.http.put(
            f"/accounts/rails/{rail_name}/account",
            user_id=user_id,
            json={"account_reference": account_reference},
        )
        return response.json()

    async def get_transfer_history(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        *,
        cursor: Optional[str] = None,
        from_date: Optional[Union[date, str]] = None,
        to_date: Optional[Union[date, str]] = None,
    ) -> TransferHistoryPage:
        """
        Retrieve the authenticated user's transfer history, both directions in
        ONE list, newest first.

        Each row carries ``direction``: ``"out"`` (a send) or ``"in"`` (an
        inbound credit on the holder's vIBAN, read live from the vIBAN ledger;
        StarMoney stores nothing about it). A holder without a vIBAN gets
        ``out`` rows only. Every row has ``id``, ``direction``, ``amount_minor``,
        ``currency``, ``status``, ``date``, ``account_reference`` /
        ``account_label`` (the holder's own vIBAN, "Compte StarMoney"),
        ``counterparty_name``, ``counterparty_iban``, ``motif`` and
        ``sm_reference`` (+ ``customer_reference``, same value), ``payee_id`` and
        ``payee_name`` (the sender's saved payee for an ``out`` row, the holder's own
        payee for the payer on an ``in`` row, and its current name; ``None``
        when there is none or the payer's IBAN is unknown). ``out`` rows
        keep every field they always had (``transaction_id``,
        ``client_transaction_id``, ``recipient_iban``, the fee line, ...).
        See :class:`starmoney.transfer_history.TransferHistoryRow`.

        Example: Awa sends Moussa 5 000 F in-network. Moussa's history has one
        ``in`` row (``counterparty_name="Awa"``, ``sm_reference`` = Awa's,
        ``motif`` = the transfer's wording); Awa's has one ``out`` row.

        Args:
            user_id: User ID to retrieve transfer history for
            limit: number of rows to return (default 20, max 100)
            offset: legacy paging: skips this many rows of the MERGED list
                (ignored when ``cursor`` is given; capped at a ~1000-row window,
                beyond which the server answers INVALID_CURSOR). Prefer ``cursor``.
            cursor: the ``next_cursor`` of the previous page, passed back
                unchanged (opaque).
            from_date: first day to include (``date`` or ``"YYYY-MM-DD"``, UTC).
            to_date: last day to include (inclusive, same format).

        Returns:
            The page: ``user_id``, ``transfers``, ``limit``, ``offset`` and
            ``next_cursor`` (None at the end of the list).
        """
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if cursor is not None:
            params["cursor"] = cursor
        if from_date is not None:
            params["from"] = from_date.isoformat() if isinstance(from_date, date) else from_date
        if to_date is not None:
            params["to"] = to_date.isoformat() if isinstance(to_date, date) else to_date
        response = await self.http.get("/accounts/transfers", params=params, user_id=user_id)
        return response.json()

    async def resolve_self(self, user_id: str) -> Dict[str, Any]:
        """
        The authenticated holder's OWN account references (GET /accounts/resolve-self).

        Use this instead of ``get_user_by_phone`` for "show me my account": the
        bank resolves the holder from the JWT subject, the request names nobody,
        so no other customer can be reached. Each call is audit-logged by the
        bank and capped per holder (RESOLVE_SELF_LIMIT_PER_24H, default 20 in
        the rolling 24 h → ``RESOLVE_SELF_LIMIT_REACHED`` 429 with
        ``retry_after_seconds``).

        Args:
            user_id: The authenticated user's ID (mints the user-scoped JWT).

        Returns:
            dict with keys:
              - user_id
              - display_name: the holder's first name, or None
              - account_state: 'captured' | 'active_pre_kyc' | 'kyc_pending'
                | 'verified' | 'closed' | None (parse with ``starmoney.AccountState``)
              - accounts: list of {account_reference, viban_tenant_slug,
                currency, provisioning_state, payable, opened_at} — the
                holder's vIBANs, oldest first; [] before provisioning.

        Raises:
            NotFoundError (404): no such holder.
            AuthenticationError (401): user_id missing or JWT invalid.
            RateLimitError (429): RESOLVE_SELF_LIMIT_REACHED.
        """
        response = await self.http.get("/accounts/resolve-self", user_id=user_id)
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
            - available_rails: List of rails with name, display info, and credential status.
              Each item carries ``account``: ``{"display_name", "account_reference", "account_reference_masked"}``
              when an account is linked on that rail (e.g. ``{"display_name": "BDK",
              "account_reference": "SN11K002…0777", "account_reference_masked": "SN……2706"}``),
              else ``None`` — grey that row out. Both references are ``None`` until the
              holder gives the IBAN (``link_rail(account_reference=…)`` or
              ``set_rail_account_reference``, service 0.3.13); never a balance.
              B-101: each item also carries ``institution_code`` and ``linked_at``
              (when the link was made; ``None`` if not linked).
            - institutions: B-101 — the banks a holder may link:
              ``[{"code": "bdk", "display_name": "BDK", "country": "SN",
              "status": "available" | "coming_soon", "link_method":
              "phone_iban_registry"}]``. Link one with ``link_rail(user_id, code)``.
            - total_rails: Total number of rails
            - configured_rails: Number of rails with stored credentials

        Example:
            ```python
            rails = await client.accounts.get_user_available_rails(user_id)
            for rail in rails["available_rails"]:
                print(f"{rail['rail_name']}: {rail['has_credentials']}")
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
              - limits: list — the send limits binding the holder while the
                bank has not verified them; [] once verified. See get_limits().
              - limits_lifted: bool — True once verified (« sans limite »).
              - holder_status: 'opening' | 'unchecked' | 'checking' | 'verified'
                | 'closed' — the bank-defined word to show (B-90, 0.3.16);
                parse with ``starmoney.HolderStatus``. Deprecated: read the two below.
              - account_status: 'pending' | 'active' | 'closed' (B-94, 0.3.18;
                ``starmoney.AccountStatus``)
              - verification_status: 'not_started' | 'pending' | 'verified' | None
                (B-94; ``starmoney.VerificationStatus``)
              - can_send: bool — unchecked/checking under ``limits``, verified without.
              - account_type: 'individual' | 'business' (0.3.21;
                ``starmoney.AccountType``) — every account is individual today.

            ``account_state`` is a closed set; parse it with
            ``starmoney.AccountState``.

        Raises:
            NotFoundError (404): no account state for this user.
            AuthenticationError (401): user_id missing or JWT invalid.
        """
        response = await self.http.get("/accounts/status", user_id=user_id)
        return response.json()

    async def get_status_by_phone(self, phone_number: str) -> Dict[str, Any]:
        """
        What is this phone number to the bank? (B-90, service-scoped, 0.3.16)

        For a number you have no user_id for — the «invited» case: another
        holder sent money to it or asked to add it as a beneficiary, and no
        account exists yet. Returns STATE only: no name, no user_id, never a
        balance.

        Args:
            phone_number: any format the bank can parse (E.164 preferred).

        Returns:
            dict with keys:
              - phone_number: the number normalised to E.164
              - holder_status: 'none' | 'invited' | 'opening' | 'unchecked'
                | 'checking' | 'verified' | 'closed' (``starmoney.HolderStatus``;
                deprecated, read the two below)
              - account_status: 'none' | 'invited' | 'pending' | 'active' | 'closed'
                (B-94, ``starmoney.AccountStatus``)
              - verification_status: 'not_started' | 'pending' | 'verified' | None
                (B-94, ``starmoney.VerificationStatus``)
              - can_send: bool
              - account_state: the account_state value, or None when no holder
              - invited_at: ISO datetime | None (for invited)

        Raises:
            ValidationError (422): the number cannot be parsed.
        """
        response = await self.http.get(f"/accounts/status/by-phone/{phone_number}")
        return response.json()

    async def get_limits(self, user_id: str) -> list[dict[str, Any]]:
        """
        The send limits currently binding the holder — ``[]`` once verified.

        While the bank has not verified the holder (``active_pre_kyc`` or
        ``kyc_pending``) the pre-KYC limit grid applies (B-102, 0.3.41: the
        Wave KYC-1 shape, maintained by the bank's ops), all lifted on
        ``kyc_verified`` with NO reset date (lifetime until verification).

        Each item carries ``kind``, ``direction`` (``"outbound"`` |
        ``"inbound"`` | ``"balance"``), ``period`` (``"per_transaction"`` |
        ``"lifetime_until_verified"`` | ``"at_any_time"`` | ``"calendar_month"``)
        and ``enforced`` (False = shown to the holder, refused nowhere).

          - ``pre_kyc_per_send``      — ceiling per send; ``consumed_minor`` /
            ``pending_minor`` / ``remaining_minor`` are None.
          - ``pre_kyc_total_sends``   — ceiling on all sends together.
            ``consumed_minor`` = executed, ``pending_minor`` = in flight (counts
            against the ceiling), ``remaining_minor`` = what may still be sent.
          - ``pre_kyc_balance``       — what the account may HOLD at any time
            (the payee cap: a send that would push the holder past it is refused
            to the SENDER with RECIPIENT_LIMIT_REACHED). ``consumed_minor`` = the
            holder's own posted balance, read live from the ledger at this
            moment (None when the ledger could not be read); ``remaining_minor``
            = what they may still receive. This item is the ONE place the SDK
            hands a balance-derived figure, and only to the holder themself.
          - ``pre_kyc_total_inbound`` — money received this UTC calendar month;
            ``consumed_minor`` = this month's credits. Declared, ``enforced``
            False today.

        ``remaining_minor`` on the send limits counts the holder's own sends
        (« envois possibles ») — never present it as a balance. Indicative: the
        server's guards are the authority (a concurrent send can change the figures).

        Convenience over get_status(): returns its ``limits`` list.
        """
        status = await self.get_status(user_id)
        return list(status.get("limits") or [])

    async def get_balance(self, user_id: str) -> dict[str, Any]:
        """
        The holder's vIBAN balance, read live from the vIBAN ledger.

        Read-through: nothing is stored server-side; BDK remains the
        account-of-record. Pre-KYC holders get it too (show it next to their
        limits). XOF has no minor unit — the ``*_minor`` values are whole francs.

        Auth: user-scoped JWT (``user_id`` mints the sub claim).

        Returns:
            dict with keys:
              - account_reference: str — the vIBAN (IBAN) the balance belongs to
              - available_minor: int — what the holder can use now
              - reserved_minor: int — held for in-flight transfers
              - balance_minor: int — available_minor + reserved_minor
              - currency: str
              - as_of: ISO datetime — when the ledger computed the figures

        Raises:
            NoVibanAccountError (404): the holder has no vIBAN (yet).
            AccountNotPayableError (409): the vIBAN account is closed.
            LedgerUnavailableError (503): the ledger could not be read; retry.
        """
        response = await self.http.get("/accounts/balance", user_id=user_id)
        return response.json()

    async def get_linked_balance(self, user_id: str, rail_name: str = "bdk") -> dict[str, Any]:
        """
        The balance of the holder's linked BDK account, read live from BDK (B-92).

        Show ``available_minor`` (BDK's available balance, owner 10 Nov 2026).
        ``balance_minor`` is BDK's booked balance and ``reserved_minor`` the part
        BDK holds. Read-through: nothing is stored server-side. Only ``bdk``.
        Example: available 1 536 228, booked 1 711 576, reserved 175 348.

        Auth: user-scoped JWT (``user_id`` mints the sub claim).

        Returns:
            dict with the same keys as ``get_balance``: account_reference (the
            linked IBAN), available_minor, reserved_minor, balance_minor,
            currency, as_of.

        Raises:
            PaymentNotFoundError (404, ``RAIL_NOT_LINKED``): no linked account.
            LinkedAccountReferenceMissingError (409): the IBAN was never given.
            LinkedAccountRejectedError (409): BDK refused the saved IBAN.
            BankUnavailableError (503): BDK could not be read; retry.
        """
        response = await self.http.get(f"/accounts/rails/{rail_name}/balance", user_id=user_id)
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
