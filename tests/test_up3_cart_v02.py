"""SDK unit tests — the 0.2 cart signs the quote (transfer routes, 0.3.0).

``UP3Resource.build_cart_v02`` copies the quote the bank returned into the cart
(P17) and never lets the cart outlive the quote (P12);
``PaymentsResource.send_with_mandates(quote=...)`` posts that chain with no
instruction fields in the body. The server-side mirror of these shapes is
``tests/integration/sandbox/test_up3.py::test_up3_cart_02_*`` over the mock bank.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from starmoney.resources.payments import PaymentsResource
from starmoney.up3.resource import UP3Resource
from starmoney.up3.vendor.signing import verify

from ._evidence import pin_evidence

SECRET = b"test-secret-key-at-least-32-chars"
ISSUER = "test-sdk"
DIGEST = "ab" * 32
EXTERNAL_IBAN = "SN17SN0100152000025690007546"

_SCHEMA = Path(__file__).resolve().parents[3] / "app/protocols/up3/schemas/cart-mandate-0.2.schema.json"


def _z(dt: _dt.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _quote_response(*, expires_in_seconds: int = 600, **overrides) -> dict:
    """The ``POST /v1/payments/quotes`` answer as the bank returns it (row C:
    external IBAN → bdk.rtgs, bank leg 2 500 F)."""
    expires = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=expires_in_seconds)
    body = {
        "quote": {
            "id": "0f3c2d1e-9b8a-4c7d-8e6f-5a4b3c2d1e0f",
            "digest": DIGEST,
            "digest_alg": "sha256-jcs-v1",
            # the bank serialises with microseconds and an offset, not Z
            "expires_at": expires.isoformat(),
        },
        "outcome": "external",
        "rail": "bdk.rtgs",
        "rail_kind": "rtgs",
        "bank": "bdk",
        "display_name": None,
        "display_name_verified": False,
        "beneficiary": {"type": "iban", "value": EXTERNAL_IBAN},
        "amount_minor": 5_000,
        "currency": "XOF",
        "fees_minor": {"orchestrator": 0, "bank": 2_500},
        "fee_total_minor": 2_500,
        "total_debit_minor": 7_500,
        "fee_collection": "accrued",
        "fee_grid_version": 1,
        "send_remaining_minor": 195_000,
    }
    body.update(overrides)
    return body


def _resource() -> UP3Resource:
    return UP3Resource(secret=SECRET, issuer=ISSUER)


def _intent(resource: UP3Resource, amount: int = 5_000) -> dict:
    return resource.build_intent(
        user_ref="whatsapp:+221770000001", description="send 5000 F", max_amount_minor=amount
    )


# ---------------------------------------------------------------------------
# build_cart_v02
# ---------------------------------------------------------------------------


def test_cart_v02_copies_the_quote_and_validates_against_the_bank_schema():
    resource = _resource()
    intent = _intent(resource)
    quote = _quote_response()
    confirmed_at = _z(_dt.datetime.now(_dt.timezone.utc))

    consent_evidence = pin_evidence(confirmed_at)

    cart = resource.build_cart_v02(
        intent, quote=quote, confirmed_at=confirmed_at, consent_evidence=consent_evidence
    )

    assert cart["version"] == "0.2" and cart["type"] == "cart" and cart["issuer"] == ISSUER
    p = cart["payload"]
    assert p["intent_mandate_id"] == intent["id"]
    assert p["user_ref"] == "whatsapp:+221770000001"
    assert p["amount_minor"] == 5_000 and p["currency"] == "XOF"
    # P17: the identifier as the customer saw it, the quote binding, the quoted legs
    assert p["beneficiary"] == {"type": "iban", "value": EXTERNAL_IBAN}
    assert p["quote"] == {"id": quote["quote"]["id"], "digest": DIGEST, "digest_alg": "sha256-jcs-v1"}
    assert p["fees_minor"] == {"orchestrator": 0, "bank": 2_500}
    assert p["beneficiary_name"] is None  # the quote had no display name
    assert p["confirmed_at"] == confirmed_at
    assert p["user_consent_evidence"] == consent_evidence  # P19: exactly the block passed
    # nothing by value, no rail (ADR-001 / P11)
    assert "beneficiary_iban" not in p and "rail" not in p
    assert verify(cart, secret=SECRET) is True

    schema = json.loads(_SCHEMA.read_text())
    payload_schema = schema["properties"]["payload"]
    assert set(p) == set(payload_schema["required"]), "payload keys ≠ the bank's 0.2 schema"
    assert schema["properties"]["version"]["const"] == "0.2"
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(cart, schema)


def test_cart_v02_takes_the_display_name_the_quote_showed_or_the_callers_shortening():
    resource = _resource()
    intent = _intent(resource)
    quote = _quote_response(display_name="Moussa Ndiaye", display_name_verified=True)

    assert resource.build_cart_v02(intent, quote=quote, consent_evidence=pin_evidence())["payload"]["beneficiary_name"] == "Moussa Ndiaye"
    short = resource.build_cart_v02(intent, quote=quote, beneficiary_name="Moussa N.", consent_evidence=pin_evidence())
    assert short["payload"]["beneficiary_name"] == "Moussa N."
    # an explicit None is honoured (the screen showed no name)
    assert resource.build_cart_v02(intent, quote=quote, beneficiary_name=None, consent_evidence=pin_evidence())["payload"]["beneficiary_name"] is None


def test_cart_v02_never_outlives_the_quote_p12():
    resource = _resource()
    intent = _intent(resource)
    # quote expires in 45 s, cart TTL asks for 2 min → clamped to the quote
    quote = _quote_response(expires_in_seconds=45)
    cart = resource.build_cart_v02(intent, quote=quote, ttl_minutes=2, consent_evidence=pin_evidence())
    quote_exp = _dt.datetime.fromisoformat(quote["quote"]["expires_at"])
    cart_exp = _dt.datetime.strptime(cart["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    assert cart_exp <= quote_exp
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cart["expires_at"])

    # a long-lived quote leaves the cart's own TTL in place
    roomy = resource.build_cart_v02(intent, quote=_quote_response(expires_in_seconds=600), ttl_minutes=2, consent_evidence=pin_evidence())
    roomy_exp = _dt.datetime.strptime(roomy["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    assert roomy_exp - _dt.datetime.now(_dt.timezone.utc) > _dt.timedelta(seconds=100)


def test_cart_v02_same_seed_same_id_and_cart_id_for_agrees():
    resource = _resource()
    intent = _intent(resource)
    a = resource.build_cart_v02(intent, quote=_quote_response(), idempotency_seed="consent-jti-1", consent_evidence=pin_evidence())
    b = resource.build_cart_v02(intent, quote=_quote_response(), idempotency_seed="consent-jti-1", consent_evidence=pin_evidence())
    c = resource.build_cart_v02(intent, quote=_quote_response(), idempotency_seed="consent-jti-2", consent_evidence=pin_evidence())
    assert a["id"] == b["id"] == resource.cart_id_for("consent-jti-1")
    assert a["id"] != c["id"]
    assert re.fullmatch(r"mnd_[A-Z0-9]{26}", a["id"])


def test_cart_v02_refuses_a_partial_quote_or_a_deferred_one():
    resource = _resource()
    intent = _intent(resource)
    with pytest.raises(ValueError, match="whole POST /v1/payments/quotes response"):
        resource.build_cart_v02(intent, quote={"quote_id": "x", "amount_minor": 5_000}, consent_evidence=pin_evidence())
    with pytest.raises(ValueError, match="deferred"):
        resource.build_cart_v02(intent, quote=_quote_response(outcome="deferred"), consent_evidence=pin_evidence())


# ---------------------------------------------------------------------------
# send_with_mandates(quote=...)
# ---------------------------------------------------------------------------


def _payments() -> tuple[PaymentsResource, MagicMock]:
    http = MagicMock()
    resource = PaymentsResource(http)
    resource._up3 = UP3Resource(secret=SECRET, issuer=ISSUER)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "transaction_id": "txn-1",
        "client_transaction_id": "set-below",
        "status": "PENDING",
        "sm_reference": "SM-7KQ4X-9TDB2",
        "customer_reference": "SM-7KQ4X-9TDB2",
        "quote_id": "0f3c2d1e-9b8a-4c7d-8e6f-5a4b3c2d1e0f",
        "settlement_rail": "bdk.rtgs",
        "fees_minor": {"orchestrator": 0, "bank": 2_500},
        "total_debit_minor": 7_500,
    }
    http.post = AsyncMock(return_value=mock_resp)
    return resource, http


@pytest.mark.asyncio
async def test_quoted_send_posts_the_02_chain_and_nothing_else_about_the_instruction():
    resource, http = _payments()
    quote = _quote_response(display_name="Moussa Ndiaye")

    result = await resource.send_with_mandates(
        user_id="user-1",
        user_ref="whatsapp:+221770000001",
        quote=quote,
        description="loyer novembre",
        idempotency_seed="consent-jti-9",
        consent_token=pin_evidence(),
    )

    body = http.post.call_args.kwargs["json"]
    cart = body["cart_mandate"]
    assert cart["version"] == "0.2"
    assert cart["payload"]["quote"]["digest"] == DIGEST
    assert cart["payload"]["beneficiary"] == {"type": "iban", "value": EXTERNAL_IBAN}
    assert cart["payload"]["beneficiary_name"] == "Moussa Ndiaye"
    assert cart["id"] == resource._up3.cart_id_for("consent-jti-9")
    assert body["client_transaction_id"] == cart["id"]
    # the cart IS the quote: no quote_id, no amount, no IBAN, no name, no rail in the body
    for absent in ("quote_id", "amount", "beneficiary_iban", "beneficiary_name", "rail_name"):
        assert absent not in body or body[absent] is None, f"{absent} travelled in the body: {body}"
    assert body["currency"] == "XOF"  # send()'s default; equal to the cart's, so no B-19 drift
    assert body["description"] == "loyer novembre"
    intent = body["intent_mandate"]
    assert intent["payload"]["max_amount_minor"] == 5_000 and intent["payload"]["beneficiary_hint"] == "Moussa Ndiaye"
    assert cart["payload"]["intent_mandate_id"] == intent["id"]
    # the posted envelopes come back with the bank's answer
    assert result["cart_mandate"] == cart and result["intent_mandate"] == intent
    assert result["sm_reference"] == "SM-7KQ4X-9TDB2"


@pytest.mark.asyncio
async def test_quoted_send_needs_no_description_and_no_instruction_fields():
    resource, http = _payments()
    await resource.send_with_mandates(user_id="user-1", user_ref="whatsapp:+221770000001", quote=_quote_response(), consent_token=pin_evidence())
    body = http.post.call_args.kwargs["json"]
    assert body["cart_mandate"]["version"] == "0.2"
    assert body.get("description") is None
    # the intent still carries a description (the schema requires one)
    assert body["intent_mandate"]["payload"]["description"]


@pytest.mark.asyncio
async def test_quoted_send_refuses_contradicting_arguments():
    resource, _ = _payments()
    with pytest.raises(ValueError, match="quote_id=.*is not the quote passed"):
        await resource.send_with_mandates(
            user_id="u", user_ref="whatsapp:+221770000001", quote=_quote_response(), quote_id="another",
            consent_token=pin_evidence(),
        )
    with pytest.raises(ValueError, match="rail_name cannot be combined"):
        await resource.send_with_mandates(
            user_id="u", user_ref="whatsapp:+221770000001", quote=_quote_response(), rail_name="BDK",
            consent_token=pin_evidence(),
        )
    with pytest.raises(ValueError, match="does not match"):
        await resource.send_with_mandates(
            user_id="u", user_ref="whatsapp:+221770000001", quote=_quote_response(), client_transaction_id="my-id",
            consent_token=pin_evidence(),
        )


@pytest.mark.asyncio
async def test_legacy_send_without_a_quote_still_needs_the_full_instruction():
    resource, http = _payments()
    with pytest.raises(ValueError, match="missing amount_minor, beneficiary_iban"):
        await resource.send_with_mandates(
            user_id="u", user_ref="whatsapp:+221770000001", currency="XOF", beneficiary_name="F", description="d",
            consent_token=pin_evidence(),
        )
    # the 0.1 path is unchanged
    await resource.send_with_mandates(
        user_id="u",
        user_ref="whatsapp:+221770000001",
        amount_minor=5_000,
        currency="XOF",
        beneficiary_iban="SN12K00100152000025690007542",
        beneficiary_name="Fatou",
        description="d",
        consent_token=pin_evidence(),
    )
    body = http.post.call_args.kwargs["json"]
    assert body["cart_mandate"]["version"] == "0.1"
    assert body["cart_mandate"]["payload"]["beneficiary_iban"] == "SN12K00100152000025690007542"
    assert body["amount"] == "5000"
