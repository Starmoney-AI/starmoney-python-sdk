"""SDK unit tests — PaymentsResource UP3 extensions + send_with_mandates."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from starmoney.resources.payments import PaymentsResource
from starmoney.up3.resource import UP3Resource
from starmoney.exceptions import (
    UP3SignatureInvalid,
    UP3SchemaInvalid,
    UP3Replay,
    UP3Expired,
)


SECRET = b"test-secret-key-at-least-32-chars"
ISSUER = "test-sdk"


def _make_payments_with_up3():
    http = MagicMock()
    resource = PaymentsResource(http)
    resource._up3 = UP3Resource(secret=SECRET, issuer=ISSUER)
    return resource, http


# ---------------------------------------------------------------------------
# payments.send — optional mandate fields forwarded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_forwards_intent_and_cart_mandates():
    resource, http = _make_payments_with_up3()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "transaction_id": "txn-1",
        "client_transaction_id": "cid-1",
        "status": "PENDING",
    }
    http.post = AsyncMock(return_value=mock_resp)

    fake_intent = {"version": "0.1", "type": "intent", "id": "mnd_000"}
    fake_cart = {"version": "0.1", "type": "cart", "id": "mnd_111"}

    await resource.send(
        user_id="user-1",
        amount=5000,
        currency="XOF",
        beneficiary_iban="SN12K00100152000025690000754",
        beneficiary_name="Fatou",
        description="Test",
        rail_name="BDK",
        client_transaction_id="cid-1",
        intent_mandate=fake_intent,
        cart_mandate=fake_cart,
    )

    called_json = http.post.call_args.kwargs["json"]
    assert called_json["intent_mandate"] == fake_intent
    assert called_json["cart_mandate"] == fake_cart


@pytest.mark.asyncio
async def test_send_omits_mandate_fields_when_not_provided():
    resource, http = _make_payments_with_up3()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"transaction_id": "txn-1", "client_transaction_id": "cid-1"}
    http.post = AsyncMock(return_value=mock_resp)

    await resource.send(
        user_id="user-1",
        amount=5000,
        currency="XOF",
        beneficiary_iban="SN12K00100152000025690000754",
        beneficiary_name="Fatou",
        description="Test",
        rail_name="BDK",
        client_transaction_id="cid-1",
    )

    called_json = http.post.call_args.kwargs["json"]
    assert "intent_mandate" not in called_json
    assert "cart_mandate" not in called_json


# ---------------------------------------------------------------------------
# send_with_mandates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_with_mandates_raises_without_up3_resource():
    http = MagicMock()
    resource = PaymentsResource(http)
    # _up3 is None by default

    with pytest.raises(RuntimeError, match="send_with_mandates requires the UP3 resource"):
        await resource.send_with_mandates(
            user_id="user-1",
            amount_minor=5000,
            currency="XOF",
            beneficiary_iban="SN12K00100152000025690000754",
            beneficiary_name="Fatou",
            description="Test",
            rail_name="BDK",
            user_ref="whatsapp:+221770000000",
        )


@pytest.mark.asyncio
async def test_send_with_mandates_builds_and_submits_mandates():
    resource, http = _make_payments_with_up3()

    # Build a real signed PaymentMandate so the verify step passes.
    up3 = resource._up3
    intent = up3.build_intent(
        user_ref="whatsapp:+221770000000",
        description="Test",
        max_amount_minor=5000,
        currency="XOF",
    )
    import datetime as _dt

    confirmed_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cart = up3.build_cart(
        intent,
        amount_minor=5000,
        beneficiary_iban="SN12K00100152000025690000754",
        beneficiary_name="Fatou",
        rail="BDK",
        fees_minor={},
        confirmed_at=confirmed_at,
    )

    # Build a fake (but signed) PaymentMandate in the response
    from starmoney.up3.vendor.signing import sign as _sign
    from starmoney.up3.resource import _mandate_id, _now_z, _future_z

    pm_id = _mandate_id()
    pm_payload = {
        "cart_mandate_id": cart["id"],
        "client_transaction_id": cart["id"],
        "rail": "BDK",
        "amount_minor": 5000,
        "currency": "XOF",
        "beneficiary_iban": "SN12K00100152000025690000754",
        "submitted_at": _now_z(),
        "status": "submitted",
        "rail_transaction_id": None,
        "rail_status_code": None,
        "settled_at": None,
    }
    pm_envelope: dict = {
        "version": "0.1",
        "type": "payment",
        "id": pm_id,
        "revision": 1,
        "issued_at": _now_z(),
        "expires_at": _future_z(60),
        "issuer": ISSUER,
        "payload": pm_payload,
    }
    pm_envelope["signature"] = _sign(pm_envelope, secret=SECRET)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "transaction_id": "txn-1",
        "client_transaction_id": cart["id"],
        "status": "PENDING",
        "payment_mandate": pm_envelope,
    }
    http.post = AsyncMock(return_value=mock_resp)

    result = await resource.send_with_mandates(
        user_id="user-1",
        amount_minor=5000,
        currency="XOF",
        beneficiary_iban="SN12K00100152000025690000754",
        beneficiary_name="Fatou",
        description="Test",
        rail_name="BDK",
        user_ref="whatsapp:+221770000000",
    )

    assert result["transaction_id"] == "txn-1"
    # verify mandate present in the POST call
    called_json = http.post.call_args.kwargs["json"]
    assert "intent_mandate" in called_json
    assert "cart_mandate" in called_json
    assert called_json["intent_mandate"]["type"] == "intent"
    assert called_json["cart_mandate"]["type"] == "cart"


# ---------------------------------------------------------------------------
# UP3 exceptions — code map
# ---------------------------------------------------------------------------


def test_up3_error_code_map_covers_all_13_codes():
    from starmoney.exceptions import UP3_ERROR_CODE_MAP

    expected_codes = {
        "UP3_SIG_INVALID",
        "UP3_KEY_NOT_REGISTERED",
        "UP3_CHAIN_BROKEN",
        "UP3_EXPIRED",
        "UP3_REPLAY",
        "UP3_AMOUNT_EXCEEDS_INTENT",
        "UP3_SCHEMA_INVALID",
        "UP3_TYPE_NOT_ACCEPTED",
        "UP3_REVISION_FIELD_DRIFT",
        "UP3_STATUS_INVALID",
        "UP3_BENEFICIARY_DRIFT",
        "UP3_RAIL_DRIFT",
        "UP3_REVISION_REGRESSION",
    }
    assert set(UP3_ERROR_CODE_MAP.keys()) == expected_codes


def test_up3_exceptions_have_correct_code_attr():
    assert UP3SignatureInvalid().code == "UP3_SIG_INVALID"
    assert UP3SchemaInvalid().code == "UP3_SCHEMA_INVALID"
    assert UP3Replay().code == "UP3_REPLAY"
    assert UP3Expired().code == "UP3_EXPIRED"
