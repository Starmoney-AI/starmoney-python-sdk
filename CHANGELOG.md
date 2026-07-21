# Changelog

## [0.1.6] — 2026-06-22

### New features

**Accounts resource**
- `create(..., viban_tenant_slug=None)` — POST /v1/accounts. **Opens a StarMoney account AND provisions its home vIBAN inline** (the vIBAN is the home rail — provisioning is StarMoney's business, not a separate consumer call). Returns `account_state` ('active_pre_kyc' when provisioned, 'captured' when the bank-decision gate declined or no tenant resolved) + `account_reference`. `viban_tenant_slug` is optional (server resolves the sole configured tenant when omitted).
- `get_status(user_id)` — GET /v1/accounts/status. Account-status enquiry: returns the KYC-assurance state (`captured`/`active_pre_kyc`/`kyc_pending`/`verified`/`closed`) + derived flags (`is_provisioned`, `kyc_verified`, `kyc_required`). STATE only — never a balance.
- `submit_kyc(user_id, attester, document_refs, idempotency_key, attested_at=None)` — POST /v1/accounts/{user_id}/kyc/submit. Submits an in-person KYC attestation; idempotent on `idempotency_key`.
- `get_profile(user_id)` — GET /v1/accounts/profile.
- `update_profile(user_id, *, email=None, phone_number=None, ...)` — PUT /v1/accounts/profile. Only provided (non-None) fields are sent.
- **Removed `provision_viban`** from the public surface — `create` now provisions the home vIBAN. The `POST /v1/accounts/provision-viban` endpoint remains server-side for internal re-provision/retry, but is no longer a consumer-facing SDK verb.

**Deferred Transfers resource (`client.deferred_transfers`)**
New resource, added as `@property` on `StarmoneyClient`.
- `send(client_transaction_id, recipient_handle, amount_minor, currency, funding_source, linked_external_account_id=None)` — POST /v1/deferred-transfers/send. Branch A (viban_hold) or Branch B (external_pull).
- `get(deferred_transfer_id)` — GET /v1/deferred-transfers/{id}.
- `claim(deferred_transfer_id, viban_tenant_slug, holder_name, recipient_user_id=None)` — POST /v1/deferred-transfers/{id}/claim. Idempotent.
- `cancel(deferred_transfer_id, user_id)` — POST /v1/deferred-transfers/{id}/cancel.

**Beneficiaries resource — completed CRUD**
- `get(user_id, beneficiary_id)` — GET /v1/beneficiaries/{id}.
- `update(user_id, beneficiary_id, *, name=None, iban=None, ...)` — PUT /v1/beneficiaries/{id}. Only provided fields sent.
- `delete(user_id, beneficiary_id)` — DELETE /v1/beneficiaries/{id} (soft delete).
- `toggle_favorite(user_id, beneficiary_id, is_favorite)` — PATCH /v1/beneficiaries/{id}/favorite.
- `validate_iban(iban)` — GET /v1/beneficiaries/validate/iban. Public, no auth required.
- `list()` now accepts `page`, `page_size`, `include_inactive` pagination params and returns `BeneficiaryListResponse` (dict).

**UP3 surface (`client.up3`)**
New resource, always present on `StarmoneyClient`. Secret defaults to `jwt_secret`; pass `up3_secret` for a distinct key (recommended in production).
- `build_intent(user_ref, description, max_amount_minor, currency, ...)` — builds and signs an IntentMandate envelope. TTL capped at 60 min.
- `build_cart(intent_mandate, *, amount_minor, beneficiary_iban, beneficiary_name, rail, ...)` — builds and signs a CartMandate. `consent_evidence` defaults to `{"type": "service_attestation", "data": {}}` (v0.1 guardrail; do NOT pass `consent_token_v1` until v0.2).
- `verify_payment_mandate(envelope) -> bool` — verifies the StarMoney signature on a returned PaymentMandate envelope.
- `verify_payment_mandate_strict(envelope) -> bool` — same but raises `UP3SignatureInvalid` on failure.

**Payments resource — UP3 extensions**
- `send(...)` now accepts optional `intent_mandate` and `cart_mandate` kwargs, forwarded as-is to POST /v1/payments.
- `send_with_mandates(user_id, *, amount_minor, currency, beneficiary_iban, beneficiary_name, description, rail_name, user_ref, ...)` — one-call helper: builds Intent, builds Cart, submits to `/v1/payments`, verifies the returned PaymentMandate. This is the method skills/flows should call.

**13 typed UP3 exceptions**
Added to `starmoney.exceptions` and exported from `starmoney`:
`UP3Error`, `UP3SignatureInvalid`, `UP3KeyNotRegistered`, `UP3ChainBroken`, `UP3Expired`, `UP3Replay`, `UP3AmountExceedsIntent`, `UP3SchemaInvalid`, `UP3TypeNotAccepted`, `UP3RevisionFieldDrift`, `UP3StatusInvalid`, `UP3BeneficiaryDrift`, `UP3RailDrift`, `UP3RevisionRegression`.

The HTTP client now detects `UP3_*` codes in API error responses and raises the typed exception instead of the generic `APIError`.

**New dependency**
- `rfc8785 ^0.1.2` — JCS canonicalization for UP3 mandate signing.

**StarmoneyClient**
- New `up3_secret: Optional[str]` parameter. Defaults to `jwt_secret` (UP3 spec v0.1 §10 FAQ).
- New `deferred_transfers` property.
- New `up3` property.

### Bug fixes

- `payments.send` no longer always includes `metadata` in the payload when `None`; only sends it when the caller provides it.

### Tests

- 48 new SDK unit tests across 4 new test files covering all new methods, the UP3 reference vector (byte-exact interop gate), and client wiring.

---

## [0.1.5] — (prior release)

Previous version. See git log for details.
