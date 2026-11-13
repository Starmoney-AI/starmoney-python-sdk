# Changelog

## [Unreleased]

- Service-side only (React backoffice read views, PR #343; the backoffice is now React only at `/admin`, with its login and grid writes as JSON under `/admin/api`). No SDK surface change.

- Version bump in lockstep with the service (B-107 request telemetry: the bank now logs one redacted line per request and per handler run; nothing changes on the wire). No SDK surface change.

## [0.3.43] — 2026-11-13

- B-104, one code = one send: `payments.send_with_mandates(...)` and `deferred_transfers.send_with_mandates(...)` can raise **`UP3EvidenceReused`** (409 `UP3_EVIDENCE_REUSED`, kind `state`) when the cart's `chat_session_pin_v1` act (`session_id_hash` + `verified_at`) already confirmed another cart the bank stored for this service. Nothing was held, sent or written. Ask the user their code again and mint a new cart (new seed) stamped with the fresh check; a same-seed retry of the first cart still answers 200 with the stored outcome. Always on at the bank — no flag to flip. `service_attestation` is unaffected. Suggested copy: «Par sécurité, saisissez à nouveau votre code pour confirmer cet envoi.»

## [0.3.42] — 2026-11-13

- Version bump in lockstep with the service (B-102 follow-up: the bank dropped the 24 h sticky refusal — every attempt re-checks the payee's balance, so a `RecipientLimitReachedError` can be followed by an accepted send as soon as the payee spends down; retrying is harmless). No SDK surface change.

## [0.3.41] — 2026-11-13

- B-102, the payee cap: `payments.quote(...)`, `payments.send(...)` / `send_with_mandates(...)` and `deferred_transfers.send(...)` / `send_with_mandates(...)` can raise **`RecipientLimitReachedError`** (403 `RECIPIENT_LIMIT_REACHED`): the recipient's unverified or new account cannot hold the amount. Nothing was written; the error carries no figure (the payee's balance is theirs) — show «{name} a atteint la limite de son compte» and suggest they verify. A sender refused 3 times toward one payee in 24 h is refused every amount to that payee for the window. `LedgerUnavailableError` (503) can also come from those calls when the recipient's ledger account could not be read.
- `accounts.get_limits(user_id)` / `get_status(...).limits[]`: every item carries `enforced` (bool); an unverified holder also gets `pre_kyc_balance` (`direction: "balance"`, `period: "at_any_time"`, `consumed_minor` = their own posted balance read live, `remaining_minor` = what they may still receive) and `pre_kyc_total_inbound` (`"inbound"` · `"calendar_month"`, `enforced: false` today). Additive.
- Versions 0.3.25 → 0.3.40 were lockstep bumps with no SDK surface change.

## [0.3.24] — 2026-11-12

- Version bump in lockstep with the service (B-96, the fee transfer to StarMoney's gain vIBAN). No SDK surface change: no request, response, event or error shape changed, and the fee transfer emits no consumer webhook. Values only: `fee_collection` reads `charged` (was `accrued`) on a vIBAN-funded send and `fee_grid_version` is 4.

## [0.3.23] — 2026-11-12

- B-98: the deferred transfer carries the 1 % (owner, 12 Nov: «the fee is deducted at transfer time, if pending goes back to cancelled the fee is refunded. For deferred/scheduled transfer the fee is taken when the transfer is executed»). The `deferred_quote` of a `RECIPIENT_HAS_NO_ACCOUNT` refusal now prices it, so `deferred_transfers.send_with_mandates(...)` signs real fee legs. Example: Awa (vIBAN) sends 25 000 F to a number with no account → `fees_minor {orchestrator: 250, bank: 0}`, `total_debit_minor` 25 250 (the hold reserves amount + fee, released whole on cancel or expiry, booked when the transfer is executed); from a linked BDK account `total_debit_minor` stays 25 000.
- `DeferredTransferRead` gains `segment` and `funding_rail` (`Optional[str]`, null on a transfer sent without a quote; the fee line of `deferred_transfers.send` / `.get` / `.cancel` carries them). Additive.
- `deferred_transfers.send(...)` / `send_with_mandates(...)` can now raise `FundingRailChangedError` (409 `FUNDING_RAIL_CHANGED`): the rail that funds the send is not the one the quote was priced for. Request a new quote.

## [0.3.22] — 2026-11-11

- Fee grid v2 (phase A): quotes, payment responses, transfer-history rows and every `payment.*` fee line carry `segment` (`p2p` | `b2c` | `b2b` | `marketplace`) and `funding_rail` (`viban` | `bdk`); new `starmoney.FeeSegment` and `starmoney.FundingRail`. `FeeLine` and the payment payload TypedDicts gain both keys.
- New typed error `FundingRailChangedError` (409 `FUNDING_RAIL_CHANGED`, properties `quoted_funding_rail` / `current_funding_rail`): the sender's funding moved between preview and confirm, request a new quote.
- Fee amounts follow the v2 grid: P2P is 1 % (`orchestrator`), the RTGS 2 500 F is on the `bank` leg only when a linked BDK account funds the send. `total_debit_minor` is what leaves the paying account.

## [0.3.21] — 2026-11-11

- `accounts.get_status` returns `account_type` (`individual` | `business`); new `starmoney.AccountType`. Every account is individual today.

## [0.3.20] — 2026-11-11

- B-52: `payment.received` payloads type `sender_phone` and `sender_iban` (both `Optional[str]`, null when the payer is outside StarMoney).
- `payments.get_status` answers 404 (`NotFoundError`) for a payment another service or another user made, as for an unknown id.

## [0.3.19] — 2026-11-10

- B-95: `accounts.link_rail(user_id, account_reference=IBAN)` links BDK from the bank's registry of linkable accounts (the IBAN is required on a first link). New `accounts.unlink_rail(user_id, rail_name="BDK")`. New typed errors: `LinkableAccountNotFoundError` (404) and `LinkVerificationFailedError` (409); `BankUnavailableError` (503) as in B-92.

## [0.3.18] — 2026-11-10

- B-92: `accounts.get_linked_balance(user_id, rail_name="bdk")` reads the linked BDK account's balance through from BDK. Show `available_minor`. New typed errors: `LinkedAccountReferenceMissingError` (409), `LinkedAccountRejectedError` (409), `BankUnavailableError` (503, a `ServerError`).
- B-94: `starmoney.AccountStatus` (`none` · `invited` · `pending` · `active` · `closed`) and `starmoney.VerificationStatus` (`not_started` · `pending` · `verified`). Both status reads return `account_status` and `verification_status`. `HolderStatus` is deprecated.

## [0.3.17] — 2026-11-10

- B-91: `starmoney.PaymentFailureReason` (closed set `payee_name_too_long` · `payee_account_invalid` · `insufficient_funds` · `rail_not_linked` · `bank_unreachable` · `bank_refused_other` · `technical`). `payment.failed` payloads type the new `failure_reason` and optional `bank_message`. A beneficiary `name` over 30 characters now raises the SDK's validation error (`rule="field.too_long"`, `expected="30"`).

## [0.3.16] — 2026-11-10

- B-90: `starmoney.HolderStatus` (closed set `none` · `invited` · `opening` · `unchecked` · `checking` · `verified` · `closed`, with `.can_send` / `.has_account`). `accounts.get_status` now returns `holder_status` and `can_send`; new `accounts.get_status_by_phone(phone)` (service-scoped) for a number you have no user_id for. Status only, never a balance.

## [0.3.15] — 2026-11-09

- Lockstep with the service. No SDK code change. Webhook envelopes now carry `metadata.delivery_id` / `metadata.delivery_attempt` inside the signed body (same values as the two `X-StarMoney-*` delivery headers); `WebhookEvent` exposes them through `metadata` as before.

## [0.3.14] — 2026-11-09

- Lockstep with the service. No SDK code change. The service now sends `X-StarMoney-Event-Id` (stable across retries of one delivery) and `X-StarMoney-Delivery-Attempt` on every webhook POST; read them from your request headers next to `X-StarMoney-Signature` and dedupe on the id.

## [0.3.13] — 2026-11-09

- **B-58: the linked account's IBAN.** `accounts.link_rail(user_id, rail_name, account_reference=…)` forwards the IBAN the holder gave as the optional body of `POST /accounts/rails/{rail_name}` (works on an already-linked rail too); new `accounts.set_rail_account_reference(user_id, rail_name, account_reference)` → `PUT /accounts/rails/{rail_name}/account`, returns `{display_name, account_reference, account_reference_masked}`. A mistyped IBAN raises `InvalidIBANError` (422 `INVALID_IBAN`, `errors[0].field == "account_reference"`); a rail with nothing linked raises the SDK's 404 class (`RAIL_NOT_LINKED`). `get_user_available_rails` now returns the captured IBAN full and masked on `account`; both stay `None` until the holder gives it. Never a balance.

## [0.3.12] — 2026-11-08

- No SDK surface change. Version bumped in lockstep with the service (bank B-82: the stage wipe handles the append-only mandate tables; nothing on the API).

## [0.3.11] — 2026-11-08

- No SDK surface change. Version bumped in lockstep with the service (bank B-82: the test-number wipe has a single trigger; nothing on the API).

## [0.3.10] — 2026-11-08

- No SDK surface change. Version bumped in lockstep with the service (bank B-82: stage-only wipe of the on-app test numbers; nothing on the API).

## [0.3.9] — 2026-11-07

- No SDK surface change. Version bumped in lockstep with the service (bank B-81: the name sent to BDK as `nomCredit` is resolved by the bank; `beneficiary_name` is still accepted on `payments.create` / `send_with_mandates`, and is ignored for the wire when the bank knows the recipient).

## [0.3.8] — 2026-11-05

- Transfer-detail fields (bank B-54), all additive and always sent (typed like `sender_name`; read with `.get()` against an older bank): `description: Optional[str]` on `PaymentInitiatedPayload`, `DeferredTransferSentPayload` and `DeferredTransferSettledPayload` (the sender's own wording; `None` when none); `motif: Optional[str]` on `PaymentReceivedPayload` (the inbound virement's libelle); `recipient_display_name: Optional[str]` on `DeferredTransferListItem` and `DeferredTransferRead` (the recipient's first name once they have an account). Example: Awa sends Moussa 5 000 XOF, motif «loyer»: her `payment.initiated` has `description="loyer"`, Moussa's `payment.received` has `motif="loyer"`, and her deferred row shows `recipient_display_name="Moussa"` once he has opened an account.
- Beneficiary items (`beneficiaries.list(...)` rows and the `create` / `get` / `update` / `toggle_favorite` results) carry `verified_holder_name` (bank B-80, typed `PayeeVerifiedHolder`; always sent, so typed required, read with `.get()` against an older bank): the bank-verified holder as a quote shows it, first name plus last-name initial; `None` for an external IBAN, a pending request and a closed holder. `name` stays the saved label. Additive. Example: DJO saved «Souleymane Dubaï» for vIBAN ···5662; the row has `name="Souleymane Dubaï"`, `verified_holder_name="SoulDubai D."`; an external SGBS IBAN row has `None`.
- `deferred_transfers.send(..., description=None)` and `deferred_transfers.send_with_mandates(..., description=None)` (bank B-54): the sender's own wording for a deferred send (max 30 characters, stripped by the bank), sent in the request body only when given; `description` (`Optional[str]`, always sent) on `DeferredTransferListItem` and `DeferredTransferRead`, and filled on the `deferred_transfer.sent` / `.settled` payloads. In `send_with_mandates`, `description` was only the intent's human echo (default `hold … for …`); it is now also the wording, so a value over 30 characters is refused by the bank with 422. Example: Awa sends 5 000 XOF to Moussa's number with `description="loyer"`; `deferred_transfer.sent` and `deferred_transfers.list(...)` show `"loyer"`.

## [0.3.7] — 2026-11-04

- `PaymentReceivedPayload` gains `sender_payee_id` / `sender_payee_name` (bank B-79; always sent, so typed like `sender_name`; read with `.get()` against an older bank): the recipient's own saved payee for the sender and its current name; `None` when unknown. `TransferHistoryRow.payee_id` / `payee_name` are now also set on `in` rows (the holder's payee for the payer's IBAN). Additive. Example: Awa saved Djo's account as «Djo»; Djo («Souleymane») sends her 2 000 XOF; `payment.received` has `sender_name="Souleymane"`, `sender_payee_name="Djo"`, and your bot decides which to show.
- `client.payments.get_mandates(user_id, cart_id)` (bank B-37) returns the typed `StoredMandates` (`status` `"stored"` or `"abandoned"`, `intent`, `cart`, `payment_mandates`, `money_status`, `abandoned_at`); a cart the bank never stored raises `PaymentNotFoundError` (404, `error_code` `RESOURCE_NOT_FOUND`). `client.payments.abandon_cart(user_id, cart_id)` (bank B-35) returns `CartAbandonment` (idempotent), and raises `UP3Replay` when the bank already stored the cart. A late `send_with_mandates` of an abandoned cart raises the new `UP3CartAbandoned` (`UP3_CART_ABANDONED`, 409). Example: Awa's 5 000 XOF send to Moussa times out at 12:05:30; `get_mandates(...)` raises `PaymentNotFoundError`, `abandon_cart(...)` returns, adita tells Awa nothing left her account, and the same send arriving late is refused with `UP3CartAbandoned`.

## [0.3.6] — 2026-11-04

- `TransferHistoryRow` gains (optional keys, absent from an older bank) `payee_id` and `payee_name` (bank B-78): the sender's saved payee for that send and the name it carries now (the name at send time if the payee was deleted); both `None` when the send matched no saved payee, and on every `in` row. `counterparty_name` is unchanged (the verified holder name). Additive. Example: DJO saved «Souleymane Dubaï» for a holder the bank verifies as «SoulDubai D.»; his row reads `counterparty_name="SoulDubai D."`, `payee_name="Souleymane Dubaï"`, and after he renames the payee, the new name.
- `WebhookEvent.DEFERRED_TRANSFER_FAILED` (`"deferred_transfer.failed"`) and the typed `DeferredTransferFailedPayload` (bank B-40): a pull-funded transfer ended `failed`, nothing taken, no retry. Same fields as `DeferredTransferClosedPayload` plus `failed_at`; `reason_code` is `bdk_refused` | `payment_failed`; `recipient_handle` lets you tell the recipient. Example: Awa's BDK account holds 3 000 of the 5 000 when Moussa opens his account; Awa gets `payment.failed`, and your service gets `deferred_transfer.failed` with Moussa's number so it can tell him. Additive.
- `execution_mode` (optional) on `UP3Resource.build_cart_v02` and `build_deferred_cart_v02` (bank B-40): `"immediate"` | `"deferred_held"` | `"deferred_best_effort"`, validated client-side. Pass `"deferred_best_effort"` to `build_deferred_cart_v02` to consent to the pull from the sender's BDK account when the recipient opens an account (nothing held; if the bank refuses, the transfer ends `failed` with nothing taken); post it with `deferred_transfers.send_with_mandates` and no `funding_source`. Omitting it changes nothing. Example: Awa signs a 5 000 XOF cart for Moussa's number with `execution_mode="deferred_best_effort"`; Moussa opens his account and is credited, or her BDK account holds only 3 000 and the transfer ends `failed`, both told, nothing moved.
- New `UP3ExecutionModeMismatch` (`UP3_EXECUTION_MODE_MISMATCH`, 409): the cart's `execution_mode` contradicts the quote's outcome or the send's `funding_source`; `errors[0].expected` names the mode reality supports. New `DeferredTransferStatus.FAILED` (`"failed"`).
- `WebhookValidator.verify_signature(...)` returns `False` when the validator's `webhook_secret` is empty or the signature header is missing, instead of computing an HMAC over an empty key. Example: a bot whose secret failed to load answers every webhook with "invalid signature" rather than accepting a signature anyone could forge with an empty key. Callers should still answer 503 when their secret is not loaded.
- New `PhoneCountryNotSupportedError` (subclass of `InvalidPhoneError`) for the bank's `422 PHONE_COUNTRY_NOT_SUPPORTED` (B-45): the recipient's phone country is not on the bank's allow-list; `errors[0].expected` lists the allowed region codes. Code catching `InvalidPhoneError` keeps working.

## [0.3.5] — 2026-11-03

- `deferred_transfers.list(...)` rows and `deferred_transfers.get(...)` carry `funding_source` (`"viban_hold"` | `"external_pull"`), `sender_account_reference` (None for external_pull) and `recipient_account_reference` (full, None until claimed; mask it) (bank B-56). Typed as `DeferredTransferListItem` / `DeferredTransferRead` / `DeferredFundingSource` in `starmoney.resources.deferred_transfers`. Additive.

- `beneficiaries.list(...)` pending items carry `held_total_minor`, `held_count`,
  `earliest_expires_at`, `latest_expires_at` (what your RESERVED deferred transfers to that
  number add up to; `0` / `0` / `None` / `None` when nothing waits, `None` on ready items).
  New TypedDict `PendingPayeeHeld` in `starmoney.resources.beneficiaries`. Additive.

- New `client.recipients.check(user_id, phone)` (bank `GET /v1/recipients/check`, B-41) returning a
  `RecipientCheck` TypedDict `{creditable, self, execute_before_max}`. A bad number raises
  `InvalidPhoneError` (422), the per-user hourly cap raises `RateLimitError` (429
  `RECIPIENT_CHECK_LIMIT_REACHED`). Example: ask before the review screen whether Moussa's number can
  be credited right now.

- No SDK code change (the SDK never validated IBAN lengths): the service now refuses a 27-character Senegal IBAN with the existing `InvalidIBANError` (422), because Senegal IBANs are 28 characters (bank B-53). Example: `beneficiaries.create(iban="SN85K0010015200041629122706")` raises `InvalidIBANError`; Awa's renamed 28-character vIBAN `SN18K00100152000041629122706` is accepted. Test fixtures now use 28-character IBANs.

## [0.3.4] — 2026-11-03

- `accounts.get_transfer_history(...)` returns the merged in + out list (bank B-59): new keyword arguments `cursor`, `from_date`, `to_date` (a `date` or `"YYYY-MM-DD"`), and the page carries `next_cursor`. Every row gains `direction` (`"in"` | `"out"`), `amount_minor`, `status`, `date`, `account_reference` / `account_label`, `counterparty_name`, `counterparty_iban` (on an `in` row: the in-network sender's vIBAN, null for an external credit), `motif`, `deferred_transfer_id` (on an `out` row that settles a phone transfer: that transfer's id, else null) (+ `id` always present); `out` rows keep all their fields. Typed as `starmoney.TransferHistoryPage` / `TransferHistoryRow` / `TransferDirection`. `offset` still works (skips rows of the merged list; prefer the cursor). Additive.

## [0.3.3] — 2026-11-03

- **Principal returned (bank B-75)**: new event `WebhookEvent.PAYMENT_REVERSED` (`payment.reversed`) with its typed payload `PaymentReversedPayload` (`currency`, `prior_status`, `reason`, `amount_minor`, `fee_returned_minor`, `fee_refunded_earlier`, `returned_at`), and `starmoney.FundsOutcome` gains `"returned"` (read side only: `payments.get_status` and an `already_failed` retry). Example: Awa's 50 000 F RTGS send is refused after acceptance (`payment.failed`, `funds="debited_under_review"`), the 2 500 F fee comes back (`payment.fee_refunded`), two days later the bank returns the 50 000 F: `payment.reversed` with `amount_minor=50000`, `fee_returned_minor=0`, `fee_refunded_earlier=True`. Additive; subscribe to the new event to be told.
- `accounts.get_user_available_rails(...)`: each rail now carries `account` (`display_name`, `account_reference`, `account_reference_masked`) when linked, else `None` (B-58). Docstring only; the SDK returns the dict unchanged.

## [0.3.2] — 2026-11-01

- `payments.get_status(...)` and a same-cart `payments.send(...)` retry answering
  `already_failed` now carry `funds` (`starmoney.FundsOutcome`) on a failed payment —
  the bank's own answer, identical to that payment's `payment.failed`. Docstrings only;
  the SDK returns the dicts unchanged.
- **Automatic fee refund** (bank `VIBAN_FEE_REFUND_ENABLED`): new event
  `WebhookEvent.PAYMENT_FEE_REFUNDED` (`payment.fee_refunded`) with its typed payload
  `PaymentFeeRefundedPayload` (`fee_lines`, `fee_total_minor`, `refunded_at`), and the
  optional `fee_refund: "pending"` (`starmoney.FeeRefundMarker`) and `fee_refund_minor`
  (the fee being refunded, whole XOF) on `PaymentBankStatusPayload`. Example: Awa sends 50 000 F by RTGS (fee 2 500 F); BDK
  accepts, then refuses an hour later: `payment.failed` with
  `funds="debited_under_review"`, `fee_refund="pending"`, `fee_refund_minor=2500`, then `payment.fee_refunded`
  with 2 500 F. Additive; subscribe to the new event to be told.

## [0.3.1] — 2026-11-01

### The settle of a deferred transfer is a payment (bank B-15 #133, PR-D2 #179)

- Typed payloads for the settle payment's events and the closed transfer:
  `PaymentInitiatedPayload`, `PaymentRailFailedPayload`, `PaymentBankStatusPayload`
  (each with `sm_reference` first, the optional fee line, `funds` on a failure, and
  `deferred_transfer_id` on a settle payment) and `DeferredTransferClosedPayload`
  for the new `deferred_transfer.expired` / `deferred_transfer.cancelled`. The event
  catalog lists both new types.
- `deferred_transfer.settled` is no longer sent by the bank. A deferred transfer has
  arrived when `payment.completed` carries its `deferred_transfer_id`.
- A deferred transfer confirmed with a UP3 cart (0.3.0) now gets its PaymentMandate
  revisions 1 and 2 under the settle payment (`<cart.id>:settle`); join them on
  `payload.cart_mandate_id`.

## [0.3.0] — 2026-11-01

### The bank's `detail` is a plain string again (bank PR-J) — no SDK change

- The server retires the one-release `detail` object (0.2.1 → 0.3.0) and sends
  `detail` as the `message` string. The SDK has read the top-level keys
  (`error_code`, `kind`, `message`, `errors`, extras) since 0.2.1 and already
  treats a string `detail` as the message, so every exception class maps as
  before. A consumer that bypasses the SDK and indexes `response_data["detail"][...]`
  must read the top-level key of the same name instead.

### History rows carry the fee line (bank PR-I)

- `accounts.get_transfer_history(user_id)` rows now carry the fee line (`quote_id`,
  `settlement_rail`, `fees_minor`, `fee_total_minor`, `total_debit_minor`,
  `fee_grid_version`; `None` on a row that confirmed no quote) beside `sm_reference` —
  the same `FeeLine` keys as the send / status responses. No SDK code change; the rows
  are returned as the bank sends them.

### The hold from the quote — a deferred transfer confirmed with a UP3 cart (bank PR-D, B-67)

- `deferred_transfers.send_with_mandates(user_id, user_ref=…, refusal=<the 422 body>,
  beneficiary_value=<the phone as typed>, amount_minor=…, hold_days=7 | execute_before=…,
  idempotency_seed=…, consent_token=…)`: when `payments.quote(...)` refused a phone
  with `RECIPIENT_HAS_NO_ACCOUNT` + `deferred_quote`, this builds the intent and a
  **UP3 cart `0.2` that signs the deferred quote** — the phone, the amount, the (empty)
  fee legs and an **execution window** `execute_before` (UP3 0.2-draft R1–R4) — and
  posts the chain to `POST /v1/deferred-transfers/send` with nothing else about the
  instruction. The bank verifies the consent before placing the hold, spends the quote
  with the row, bounds the hold by the window (≤ 7 days) and answers the deferred
  transfer with its fee line (`quote_id`, `settlement_rail=bdk.internal`, `fees_minor`,
  `fee_total_minor`, `total_debit_minor`, `fee_grid_version`) and `sm_reference`. No
  PaymentMandate at this step (none exists until the recipient's account does).
- `up3.build_deferred_cart_v02(intent, refusal=…, beneficiary_value=…, amount_minor=…)`
  for callers that post the chain themselves.
- `deferred_transfers.send(...)` also takes `quote_id=` alone (the quote is the whole
  instruction; `recipient_handle` / `amount_minor` / `funding_source` become optional
  and may only repeat the quote) or `intent_mandate=` + `cart_mandate=`
  (`client_transaction_id` defaults to `cart.id`). The legacy full-instruction call is
  unchanged.
- New bank error on this path: `UP3_EXECUTION_WINDOW_INVALID` (422, validation) —
  the window is missing on a deferred quote, ends before the cart does, or ends more
  than 7 days after the tap. `QUOTE_MISMATCH` / `QUOTE_CONSUMED` (with the hold's
  `sm_reference`) / `QUOTE_EXPIRED` as on payments; the UP3 codes when a cart signs.

### The transfer route from the SDK — preview, then confirm with a cart that signs the quote

- `payments.quote(user_id, beneficiary_type=, beneficiary_value=, amount_minor=)`
  previews one transfer (any IBAN, a phone, a saved beneficiary): the rail
  (`bdk.internal` free · `bdk.rtgs` bank leg 2 500 F), the fee legs, the
  display name, and a `quote {id, digest, digest_alg, expires_at}`. Moves no money.
- `payments.send_with_mandates(user_id, user_ref=…, quote=<that response>)`
  confirms it: the SDK builds the intent and a **UP3 cart `0.2`** that signs the
  quote (`beneficiary {type, value}`, `quote {id, digest, digest_alg}`, the fee
  legs — P17) and posts the chain with no amount / IBAN / name in the body. The
  bank binds the cart to the quote it stored and bills exactly the quoted fee
  (`UP3_QUOTE_DRIFT` / `UP3_FEE_DRIFT` otherwise). The cart never outlives the
  quote (P12). `description` is optional (it becomes the motif after the
  reference). `idempotency_seed` keeps the retry contract.
- `up3.build_cart_v02(intent, quote=…)` for callers that post the chain themselves.
- The instruction arguments of `send_with_mandates` (`amount_minor`, `currency`,
  `beneficiary_iban`, `beneficiary_name`, `description`) are now optional and
  required only without `quote=`; a missing one raises `ValueError` before any
  request. `quote_id=` beside a full instruction still works (0.1 cart).
- `deferred_transfers.list(user_id, client_transaction_id=…)` (bank B-71): the
  transfer you sent under your own id, whatever its status.
- Responses and webhooks: read **`sm_reference`** (same value as
  `customer_reference`, which is deprecated and dropped in 0.4.0). Every
  `payment.*` of a quote-confirmed send, and the send / status responses, carry
  the fee line typed as `starmoney.FeeLine` (`quote_id`, `settlement_rail`,
  `fees_minor {orchestrator, bank}`, `fee_total_minor`, `total_debit_minor`,
  `fee_grid_version`); `payment.failed` carries `funds` (`starmoney.FundsOutcome`:
  `not_debited` | `debited_under_review`).
- `accounts.resolve_self(user_id)` (bank PR-G): the caller's own account
  references and state under a user-scoped JWT — use it instead of
  `get_user_by_phone` for "show me my account".
- Version in lockstep with the bank service: `0.3.0`.

## [0.2.3] — 2026-10-27

### `customer_reference` on the payment responses

- `payments.send()`, `payments.send_with_mandates()` and `payments.get_status()`
  now return `customer_reference` (e.g. `SM-7KQ4X-9TDB2`), the same value as
  the transfer's `payment.*` webhooks and its `get_transfer_history()` row, so
  a confirmation screen can show it right after the send. A replayed mandated
  send (`ALREADY_COMPLETED` / `ALREADY_IN_PROGRESS` / `ALREADY_FAILED`)
  returns the original payment's reference.
- The `detail` → plain-string revert moves past 0.2.3; this release is
  additive only.

## [0.2.2] — 2026-10-20

### `customer_reference` — StarMoney's reference for the customer to quote

- New `customer_reference` (e.g. `SM-7KQ4X-9TDB2`) on every `payment.*`,
  `deferred_transfer.*` and `payment.received` webhook, on
  `accounts.get_transfer_history()` rows and on every `deferred_transfers`
  response (send, get, cancel/claim, list). StarMoney mints it; the same
  transfer always carries the same value, and a deferred transfer keeps one
  reference from send to settle. Show it to the customer instead of your own
  `client_transaction_id`.
- `accounts.get_transfer_history()` rows and `deferred_transfers.list()`
  rows also carry `client_transaction_id` (your own id, as sent).
- Typed on `DeferredTransferSentPayload`, `PaymentReceivedPayload`,
  `DeferredTransferSettledPayload`.
- The `detail` → plain-string revert announced for 0.2.2 moves to **0.2.3**;
  this release is additive only.

## [0.2.1] — 2026-10-10

> **Numbering:** from this release the SDK carries the same version as
> `starmoney-bank-service` (`0.2.1`). This is the release that was announced
> to consumers as "0.1.26"; no `v0.1.26` tag exists. Pin `v0.2.1`. The
> follow-up previously called "0.1.27" is `0.2.2`.

### Explainable errors (B-32) — new top-level fields; `detail` is a one-release shim

- The server's error body is now ONE flat shape:
  `{"error_code", "kind", "message", "error_id", "errors"}`, plus — **for
  this release only** — a legacy `"detail": {"message", "error_code",
  "errors"}` OBJECT mirroring those same fields, kept so a consumer still
  reading `response_data["detail"]["error_code"]` / `["detail"]["errors"]`
  (the pre-B-32 shape) does not break the moment the server deploys this.
  **`detail` reverts to a plain string again in SDK 0.2.2** — do not build
  new code against `detail.*`; read the top-level keys. Every extra field
  an error carries (`retry_after_seconds`, `beneficiary_id`,
  `beneficiary_request_id`, `ceiling_minor`, `consumed_minor`,
  `pending_minor`, `remaining_minor`, `currency`, `lifts_on`,
  `cancel_reason`, ...) is a top-level key only, never nested under
  `detail`. See `docs/ERRORS.md` in starmoney-bank-service for the full
  contract.
- Every `APIError`/`UP3Error` (sub)class gains `.error_code` (`""` when the
  server didn't send one), `.kind` (`"validation"` | `"state"` |
  `"technical"`, defaulted by HTTP status when the server omits it),
  `.errors` (a list, **never** `None` — `[]` when there is none), `.error_id`
  and `.message` (the top-level `message`, falling back to the legacy
  `detail.message`, falling back to the message the SDK derived itself —
  e.g. from response text on a transport error). Parsing accepts BOTH the
  new flat shape and the legacy nested `detail` dict, so pinned-old-server
  consumers keep working during rollout.
- `InvalidPhoneError.errors[0]["rule"]` is now `"phone.normalisation"` or
  `"phone.region"`; `InvalidIBANError.errors[0]["rule"]` is one of
  `"iban.format"` / `"iban.length"` / `"iban.country"` / `"iban.checksum"`.

### Deferred-transfer cancel reason (B-44)

- `deferred_transfers.cancel(deferred_transfer_id, user_id, reason=None)` —
  `reason` is `"recipient_unreachable"` or `"sender_request"` (server
  default when omitted). The response's `cancel_reason` echoes the effective
  value. An unrecognised `reason` raises `ValidationError` (422).

## [0.1.25] — 2026-10-08

### Beneficiaries by phone (B-27)

- `beneficiaries.create(user_id, name, phone=..., client_reference=...)`: save a
  number. 201 when its holder already has a StarMoney account (status `active`,
  `iban` = their vIBAN); 202 when not (status `pending`, `beneficiary_request_id`,
  `expires_at`). `iban` is now optional; exactly one of `iban` / `phone`.
- `beneficiaries.list(user_id, status="all" | "active" | "pending")`: one list; pending
  items have `iban` `None` and carry `beneficiary_request_id` + `expires_at`.
- New resource `client.beneficiary_requests`: `get`, `cancel`, `invite` (records
  `invited_at`; the consumer sends the template).
- New webhook events `beneficiary.added` and `beneficiary_request.expired`
  (`BeneficiaryAddedPayload`, `BeneficiaryRequestExpiredPayload`).
- New exceptions `SelfTransferNotAllowedError` (422), `InvalidPhoneError` (422),
  `BeneficiaryAddLimitReachedError` (429, `.retry_after_seconds`);
  `DuplicateResourceError.existing_id` names the existing beneficiary or request.
  `BENEFICIARY_ACCOUNT_CLOSED` (409, a send to a closed holder) is a
  `DuplicateResourceError` with that code in `response_data`.

## [0.1.24] — 2026-10-04

### UP3 refusals are UP3 errors, never "duplicates"

- New exceptions `UP3MandateRequired` (409, profile P9), `UP3PayerMismatch` (409,
  P2), `UP3IssuerMismatch` (409, P3) and `UP3TypeRequiredMissing` (422, P10). A
  409 carrying one of these codes used to surface as `DuplicateResourceError`,
  whose name says "already exists" — a caller mapping that to "already done"
  would tell a customer money left when nothing was sent.
- Any `UP3_*` code this SDK does not know yet is raised as `UP3Error` with
  `.code` set, never as `DuplicateResourceError` or a bare `APIError`.

## [0.1.23] — 2026-10-04

### `send_with_mandates` returns the envelopes it signed

- The returned dict now also carries `intent_mandate` and `cart_mandate`: the
  exact signed envelopes this call posted (with your `confirmed_at` and the
  consent evidence). Store them against your consent record instead of only
  the cart id. Extra keys; nothing in the bank's response moves.

## [0.1.22] — 2026-10-03

### UP3 fixes for the Mandate flow (B-20)

- `payments.send_with_mandates(..., confirmed_at=...)`: pass the moment the user
  actually confirmed the terms (Flow submit / button tap, RFC 3339 Z). It is
  signed into the cart and the bank measures consent freshness from it. The
  default stays "now", which is only right at the tap itself.
- `payments.cart_id_for(seed)` and `up3.cart_id_for(seed)`: the cart.id (= the
  client_transaction_id) a seed derives to, without building a cart. Use it after
  a timed-out `send_with_mandates`: `get_status(user_id, cart_id_for(seed))` tells
  you whether the bank captured the payment before offering a fresh consent.
- `send_with_mandates` no longer "verifies" the returned PaymentMandate: it
  checked the bank's signature with the client's own secret, which can only
  fail, and ignored the result. `up3.verify_payment_mandate(envelope,
  orchestrator_secret=...)` stays for callers that hold the Orchestrator's key.
- `deferred_transfers.send(..., user_id=...)`: the sender is passed to the
  request signer, so the call no longer needs raw HTTP to set the JWT subject.

## [0.1.21] — 2026-09-28

### Typed payloads for `deferred_transfer.settled` and the `account.*` events

- `starmoney.webhooks.DeferredTransferSettledPayload`: `user_id` is the
  SENDER's user id (the bank delivered `""` before; bank fix S-35). It adds
  `recipient_user_id`, `recipient_handle` and `recipient_display_name`.
- `starmoney.webhooks.AccountLifecyclePayload` (aliases `AccountOpenedPayload`,
  `AccountKycVerifiedPayload`, `AccountKycReviewRequiredPayload`) for
  `account.opened` / `account.kyc.verified` / `account.kyc.review_required`.
- `PaymentReceivedPayload.sender_name` / `source_bank_name` move from optional to
  REQUIRED keys (value `Optional[str]`): the bank always sends them, possibly null.
- The bank's test suite pins each delivered key set to these TypedDicts.
  Typing only; no runtime change.

## [0.1.20] — 2026-09-27

- `accounts.get_balance()` now also returns `account_reference`: the vIBAN
  (IBAN) the balance belongs to. Additive.

## [0.1.19] — 2026-09-27

### vIBAN balance read + richer account status

- `accounts.get_balance(user_id)` → `GET /v1/accounts/balance`: `available_minor`,
  `reserved_minor`, `balance_minor`, `currency`, `as_of` (whole XOF francs, read
  live from the vIBAN ledger). Typed errors: `NoVibanAccountError` (404),
  `AccountNotPayableError` (409), `LedgerUnavailableError` (503, a `ServerError`).
- `starmoney.AccountState` — the closed set of `account_state` values
  (`captured`, `active_pre_kyc`, `kyc_pending`, `verified`, `closed`).
- `get_status()` now carries `limits_lifted` (True once verified), and each
  `limits` item carries `direction` and `period`. Additive — existing keys unchanged.

## [0.1.18] — 2026-09-24

### `payment.received` names the sending bank

- `PaymentReceivedPayload.source_bank_name: Optional[str]` (optional key) — the
  sending bank's name from the Eucalyptus notification (e.g. "SOCIETE GENERALE
  SENEGAL"); `None` on an internal deferred-transfer claim credit. Use it when
  `sender_name` is `None`. Typing only, no runtime change.

## [0.1.17] — 2026-09-23

### `payment.received` names the payer

- `PaymentReceivedPayload.sender_name: Optional[str]` (optional key) — the
  deferred-transfer sender's first name when the credit is a claim; `None`
  when the payer is unknown (Eucalyptus virements carry no payer). Typing only,
  no runtime change.

## [0.1.12] — 2026-08-28

### Webhook event catalog + typed payloads (transfer notifications, PR #101)

Discoverable, typo-safe constants for every subscribable webhook event, and
typed payloads for the two newest ones — no behavior change, purely additive.

- `starmoney.webhooks.WebhookEvent` — a `str` enum covering the full
  16-event broadcastable catalog (payment lifecycle, UP3 Mandate audit,
  deferred transfer, account lifecycle, inbound credit), including the two
  events added by the transfer-notifications work:
  - `WebhookEvent.DEFERRED_TRANSFER_SENT` ("deferred_transfer.sent") — "money
    is waiting for a recipient who has no account yet".
  - `WebhookEvent.PAYMENT_RECEIVED` ("payment.received") — "you received
    money" (ordinary inbound credit).
- `starmoney.webhooks.DeferredTransferSentPayload` /
  `PaymentReceivedPayload` — `TypedDict`s matching the exact flat delivered
  webhook body for these two events (editor/type-checker help only; no
  runtime validation — verify the HMAC signature first).
- `resources/webhooks.py` docstring examples updated to use `WebhookEvent`
  constants and demonstrate subscribing to both new events.

## [0.1.9] — 2026-08-04

### List a sender's deferred transfers (ADR-003) — enables the cancel pick-list

New read method so a consumer (adita) can show a user their cancellable transfers
to pick from, instead of asking them to type an opaque `deferred_transfer_id`.

- `deferred_transfers.list(user_id, status=None, limit=20, offset=0)` — lists the
  transfers the caller **sent** (sender-scoped: only rows where JWT `sub` ==
  `sender_user_id`, same ownership rule as `cancel`; a caller can never enumerate
  another user's transfers). Mirrors `GET /v1/deferred-transfers`.
  - `status` is an optional comma-list (e.g. `"reserved,armed"`); when omitted the
    API defaults to the **cancellable** set (`reserved`, `armed`) so the common
    "what can I cancel?" call needs no params.
  - Each row carries `deferred_transfer_id`, `recipient_handle` (**MASKED**, e.g.
    `+2217xxxxxx99` — enough to disambiguate a pick-list without re-exposing full
    PII), `amount_minor`, `currency`, `status`, `created_at`, `expires_at`. No
    balance/available field (positioning: per-transfer state, never funds).

Consumer flow: `list(...)` → render pick-rows → user taps one → existing
`cancel(deferred_transfer_id, user_id)`. No new cancel behaviour.

## [0.1.8] — 2026-07-23

### Server-side rail selection (ADR-001) — `rail_name` is now an optional hint

Rail selection moved server-side. StarMoney selects the funding/settlement rail;
the caller no longer decides it. (Everything settles over BDK RTGS today; `VIBAN`
vs `BDK` is whether the sender funds from their vIBAN.)

- `payments.send_with_mandates(..., rail_name=None)` — `rail_name` is now **optional**.
  Omit it and StarMoney routes: `VIBAN` when the sender can fund from their vIBAN,
  else `BDK`. When provided it is a hint: `'BDK'` is honored; `'VIBAN'` is honored
  only if the sender has a payable vIBAN, else the API returns 400. The response's
  resolved rail tells you what was chosen.
- `payments.send(..., rail_name=None)` — `rail_name` accepts `None`; omitted from the
  request payload when not given.
- `up3.build_cart(..., rail=None)` — `rail` is now **optional and omitted** from the
  CartMandate payload when not supplied. Rail is orchestrator-owned and no longer
  part of the user-signed cart; the backend stamps the executed rail onto the
  PaymentMandate. `UP3_RAIL_DRIFT` is retired (the backend no longer enforces
  `payment.rail == cart.rail`).

Caller migration (adita `send_money`): call `send_with_mandates(...)` with **no
`rail_name`**. This is the frozen contract in ADR-001 §7.

### Also — rail example literal corrected (FIX-1)

- Docstring examples that showed the non-resolving `"BDK_RTGS"` rail literal now
  show `"BDK"`. `RailName("BDK_RTGS")` raises `ValueError` and 422s a live send;
  the only valid literals are `"BDK"` (external) and `"VIBAN"` (sender funds from
  their vIBAN). With ADR-001 you normally omit `rail_name` entirely.

## [0.1.7] — 2026-07-23

### Release hygiene — this is the real 0.1.6 surface, published under a fresh tag

No API changes versus the intended 0.1.6 surface below. Version bump only, for
a release-mechanics reason: the published `v0.1.6` tag is frozen at a stale
commit (a deferred-transfers-only build predating the #69 accounts redesign and
the UP3 surface), and the auto-publish tag step is idempotent — so it could
never be moved onto the correct code. `0.1.7` ships the full accounts (#69) +
UP3 + deferred-transfers + beneficiaries surface documented under 0.1.6, for
real, under a fresh tag consumers can pin.

- **Do not use `v0.1.6`** — it is a dead artifact pinned to old code.
- Consumers pin `rev = "v0.1.7"` against `Starmoney-AI/starmoney-python-sdk`.

The complete surface is unchanged from the 0.1.6 notes that follow.

---

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
