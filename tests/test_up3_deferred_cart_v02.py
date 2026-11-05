"""SDK unit tests — the 0.2 cart that consents to a DEFERRED transfer (bank PR-D, B-67).

``UP3Resource.build_deferred_cart_v02`` signs the ``deferred_quote`` a
``RECIPIENT_HAS_NO_ACCOUNT`` refusal carried, the phone as typed, the amount
and an execution window (``execute_before``);
``DeferredTransfersResource.send_with_mandates`` posts that chain with no
instruction fields in the body. The server-side mirror is
``tests/integration/sandbox/test_deferred_transfer.py::test_deferred_transfer_from_quote_*``
over the mock bank.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from starmoney.resources.deferred_transfers import DeferredTransfersResource
from starmoney.up3.resource import UP3Resource
from starmoney.up3.vendor.signing import verify

SECRET = b"test-secret-key-at-least-32-chars"
ISSUER = "test-sdk"
DIGEST = "cd" * 32
PHONE = "+221781112233"
QUOTE_ID = "3f0c9c2e-6f3a-4a6e-9d8b-2c1e5a7b9f10"

_SCHEMA = Path(__file__).resolve().parents[3] / "app/protocols/up3/schemas/cart-mandate-0.2.schema.json"
_Z = "%Y-%m-%dT%H:%M:%SZ"


def _z(dt: _dt.datetime) -> str:
    return dt.strftime(_Z)


def _parse_z(value: str) -> _dt.datetime:
    return _dt.datetime.strptime(value, _Z).replace(tzinfo=_dt.timezone.utc)


def _refusal(*, expires_in_seconds: int = 600, with_quote: bool = True, **overrides) -> dict:
    """The 422 body of ``POST /v1/payments/quotes`` for a phone nobody holds (row F)."""
    expires = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=expires_in_seconds)
    body: dict = {
        "error_code": "RECIPIENT_HAS_NO_ACCOUNT",
        "kind": "state",
        "message": "The recipient has no account yet",
        "recipient_status": "no_account",
        "beneficiary_type": "msisdn",
        "error_id": "corr-1",
    }
    if with_quote:
        body["deferred_quote"] = {
            "id": QUOTE_ID,
            "digest": DIGEST,
            "digest_alg": "sha256-jcs-v1",
            "expires_at": expires.isoformat(),  # microseconds + offset, as the bank writes it
            "rail": "bdk.internal",
            "fees_minor": {"orchestrator": 0, "bank": 0},
            "fee_total_minor": 0,
            "total_debit_minor": 20_000,
            "fee_collection": "waived",
            "fee_grid_version": 1,
        }
        body["deferred_quote"].update(overrides)
    return body


def _resource() -> UP3Resource:
    return UP3Resource(secret=SECRET, issuer=ISSUER)


def _intent(resource: UP3Resource, amount: int = 20_000) -> dict:
    return resource.build_intent(
        user_ref="whatsapp:+221770000001", description="hold 20000 F", max_amount_minor=amount
    )


# ---------------------------------------------------------------------------
# build_deferred_cart_v02
# ---------------------------------------------------------------------------


def test_deferred_cart_signs_the_refusals_quote_and_validates_against_the_bank_schema():
    resource = _resource()
    intent = _intent(resource)
    confirmed_at = _z(_dt.datetime.now(_dt.timezone.utc))

    cart = resource.build_deferred_cart_v02(
        intent,
        refusal=_refusal(),
        beneficiary_value=PHONE,
        amount_minor=20_000,
        confirmed_at=confirmed_at,
        execute_before=_z(_parse_z(confirmed_at) + _dt.timedelta(days=3)),
    )

    assert cart["version"] == "0.2" and cart["type"] == "cart" and cart["issuer"] == ISSUER
    p = cart["payload"]
    assert p["intent_mandate_id"] == intent["id"]
    assert p["amount_minor"] == 20_000 and p["currency"] == "XOF"
    # the phone as typed, no name (nobody holds it), the quote binding, the (empty) fee legs
    assert p["beneficiary"] == {"type": "msisdn", "value": PHONE}
    assert p["beneficiary_name"] is None
    assert p["quote"] == {"id": QUOTE_ID, "digest": DIGEST, "digest_alg": "sha256-jcs-v1"}
    assert p["fees_minor"] == {"orchestrator": 0, "bank": 0}
    # the execution window, 3 days after the tap
    assert p["execute_before"] == _z(_parse_z(confirmed_at) + _dt.timedelta(days=3))
    assert "beneficiary_iban" not in p and "rail" not in p
    assert verify(cart, secret=SECRET) is True

    schema = json.loads(_SCHEMA.read_text())
    payload_schema = schema["properties"]["payload"]
    assert set(p) == set(payload_schema["required"]) | {"execute_before"}
    assert "execute_before" in payload_schema["properties"]
    assert "execute_before" not in payload_schema["required"], "optional in the schema; R3 is the verifier's"
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(cart, schema)


def test_deferred_cart_accepts_the_whole_refusal_or_its_deferred_quote():
    resource = _resource()
    intent = _intent(resource)
    whole = resource.build_deferred_cart_v02(
        intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000
    )
    inner = resource.build_deferred_cart_v02(
        intent, refusal=_refusal()["deferred_quote"], beneficiary_value=PHONE, amount_minor=20_000
    )
    assert whole["payload"]["quote"] == inner["payload"]["quote"] == {
        "id": QUOTE_ID, "digest": DIGEST, "digest_alg": "sha256-jcs-v1"
    }


def test_deferred_cart_default_window_is_hold_days_after_the_tap_and_capped_at_seven():
    resource = _resource()
    intent = _intent(resource)
    confirmed_at = "2026-10-31T12:00:00Z"

    seven = resource.build_deferred_cart_v02(
        intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000, confirmed_at=confirmed_at
    )
    assert seven["payload"]["execute_before"] == "2026-11-07T12:00:00Z"

    two = resource.build_deferred_cart_v02(
        intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000,
        confirmed_at=confirmed_at, hold_days=2,
    )
    assert two["payload"]["execute_before"] == "2026-11-02T12:00:00Z"

    for bad in (0, 8):
        with pytest.raises(ValueError, match="hold_days"):
            resource.build_deferred_cart_v02(
                intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000, hold_days=bad
            )


def test_deferred_cart_normalises_an_explicit_window_to_the_envelope_z_form():
    resource = _resource()
    cart = resource.build_deferred_cart_v02(
        _intent(resource), refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000,
        execute_before="2026-11-03T12:00:00.123456+00:00",
    )
    assert cart["payload"]["execute_before"] == "2026-11-03T12:00:00Z"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cart["payload"]["execute_before"])


def test_deferred_cart_never_outlives_the_quote_p12():
    resource = _resource()
    cart = resource.build_deferred_cart_v02(
        _intent(resource), refusal=_refusal(expires_in_seconds=45), beneficiary_value=PHONE,
        amount_minor=20_000, ttl_minutes=2,
    )
    quote_exp = _dt.datetime.fromisoformat(_refusal(expires_in_seconds=45)["deferred_quote"]["expires_at"])
    assert _parse_z(cart["expires_at"]) <= quote_exp + _dt.timedelta(seconds=1)


def test_deferred_cart_same_seed_same_id():
    resource = _resource()
    intent = _intent(resource)
    a = resource.build_deferred_cart_v02(
        intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000, idempotency_seed="jti-1"
    )
    b = resource.build_deferred_cart_v02(
        intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000, idempotency_seed="jti-1"
    )
    assert a["id"] == b["id"] == resource.cart_id_for("jti-1")


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"refusal": _refusal(with_quote=False)}, "deferred_quote"),
        ({"refusal": {"error_code": "RECIPIENT_HAS_NO_ACCOUNT"}}, "deferred_quote"),
        ({"beneficiary_value": "781112233"}, "E.164"),
        ({"amount_minor": 0}, "amount_minor"),
    ],
)
def test_deferred_cart_refuses_locally_what_the_bank_would_refuse(kwargs, match):
    resource = _resource()
    args = {"refusal": _refusal(), "beneficiary_value": PHONE, "amount_minor": 20_000}
    args.update(kwargs)
    with pytest.raises(ValueError, match=match):
        resource.build_deferred_cart_v02(_intent(resource), **args)


# ---------------------------------------------------------------------------
# deferred_transfers.send — quote_id / chain shapes
# ---------------------------------------------------------------------------


def _dt_resource():
    http = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "id": "dt-uuid-1", "status": "reserved", "branch": "hold_backed",
        "quote_id": QUOTE_ID, "settlement_rail": "bdk.internal",
        "fees_minor": {"orchestrator": 0, "bank": 0}, "fee_total_minor": 0,
        "total_debit_minor": 20_000, "sm_reference": "SM-7KQ4X-9TDB2",
    }
    http.post = AsyncMock(return_value=resp)
    resource = DeferredTransfersResource(http)
    resource._up3 = _resource()
    return resource, http


@pytest.mark.asyncio
async def test_send_with_a_quote_id_posts_the_quote_as_the_whole_instruction():
    resource, http = _dt_resource()
    out = await resource.send(client_transaction_id="ctid-q", quote_id=QUOTE_ID, user_id="user-1")
    body = http.post.call_args.kwargs["json"]
    assert body == {"client_transaction_id": "ctid-q", "currency": "XOF", "quote_id": QUOTE_ID}
    assert http.post.call_args.kwargs["user_id"] == "user-1"
    assert out["settlement_rail"] == "bdk.internal"


@pytest.mark.asyncio
async def test_send_with_a_chain_defaults_the_id_and_the_quote_to_the_cart():
    resource, http = _dt_resource()
    intent = _intent(resource._up3)
    cart = resource._up3.build_deferred_cart_v02(
        intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000
    )
    await resource.send(intent_mandate=intent, cart_mandate=cart, user_id="user-1")
    body = http.post.call_args.kwargs["json"]
    assert body["client_transaction_id"] == cart["id"]
    assert body["quote_id"] == QUOTE_ID
    assert body["intent_mandate"] is intent and body["cart_mandate"] is cart
    # nothing about the instruction travels beside the chain
    assert "recipient_handle" not in body and "amount_minor" not in body and "funding_source" not in body


@pytest.mark.asyncio
async def test_send_refuses_locally_a_body_that_contradicts_the_cart():
    resource, _ = _dt_resource()
    intent = _intent(resource._up3)
    cart = resource._up3.build_deferred_cart_v02(
        intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000
    )
    with pytest.raises(ValueError, match="cart.id"):
        await resource.send(client_transaction_id="other", intent_mandate=intent, cart_mandate=cart)
    with pytest.raises(ValueError, match="quote the cart signs"):
        await resource.send(quote_id="another-quote", intent_mandate=intent, cart_mandate=cart)
    with pytest.raises(ValueError, match="travel together"):
        await resource.send(client_transaction_id="x", cart_mandate=cart)


@pytest.mark.asyncio
async def test_send_without_a_quote_still_demands_the_full_instruction():
    resource, _ = _dt_resource()
    with pytest.raises(ValueError, match="recipient_handle, amount_minor required without quote_id"):
        await resource.send(client_transaction_id="x")
    with pytest.raises(ValueError, match="client_transaction_id is required"):
        await resource.send(recipient_handle=PHONE, amount_minor=1)


@pytest.mark.asyncio
async def test_send_with_mandates_builds_the_chain_and_posts_nothing_else():
    resource, http = _dt_resource()
    out = await resource.send_with_mandates(
        "user-1",
        user_ref="whatsapp:+221770000001",
        refusal=_refusal(),
        beneficiary_value=PHONE,
        amount_minor=20_000,
        hold_days=3,
        idempotency_seed="consent-jti-9",
        consent_token={"type": "service_attestation", "data": {"jti": "consent-jti-9"}},
        client_reference="wa-flow-42",
    )
    body = http.post.call_args.kwargs["json"]
    cart = body["cart_mandate"]
    assert set(body) == {"client_transaction_id", "currency", "quote_id", "intent_mandate", "cart_mandate", "client_reference"}
    assert body["client_transaction_id"] == cart["id"] == resource._up3.cart_id_for("consent-jti-9")
    assert body["quote_id"] == QUOTE_ID
    assert cart["payload"]["beneficiary"] == {"type": "msisdn", "value": PHONE}
    assert cart["payload"]["user_consent_evidence"]["data"] == {"jti": "consent-jti-9"}
    window = _parse_z(cart["payload"]["execute_before"]) - _parse_z(cart["payload"]["confirmed_at"])
    assert window == _dt.timedelta(days=3)
    assert body["intent_mandate"]["payload"]["max_amount_minor"] == 20_000
    assert verify(cart, secret=SECRET) is True
    assert out["sm_reference"] == "SM-7KQ4X-9TDB2"
    assert out["cart_mandate"] is cart and out["intent_mandate"] is body["intent_mandate"]


@pytest.mark.asyncio
async def test_send_with_mandates_posts_the_wording_only_when_given():
    """B-54: «loyer» goes in the body (the signed cart carries no wording) and is
    the intent's echo too; without it the body is unchanged."""
    resource, http = _dt_resource()
    await resource.send_with_mandates(
        "user-1", user_ref="whatsapp:+221770000001", refusal=_refusal(),
        beneficiary_value=PHONE, amount_minor=20_000, idempotency_seed="jti-w",
        description="loyer",
    )
    body = http.post.call_args.kwargs["json"]
    assert body["description"] == "loyer"
    assert body["intent_mandate"]["payload"]["description"] == "loyer"
    assert "description" not in body["cart_mandate"]["payload"]

    resource, http = _dt_resource()
    await resource.send_with_mandates(
        "user-1", user_ref="whatsapp:+221770000001", refusal=_refusal(),
        beneficiary_value=PHONE, amount_minor=20_000, idempotency_seed="jti-w2",
    )
    assert "description" not in http.post.call_args.kwargs["json"]


@pytest.mark.asyncio
async def test_send_with_mandates_needs_the_up3_resource_and_a_deferred_quote():
    resource, _ = _dt_resource()
    with pytest.raises(ValueError, match="deferred_quote"):
        await resource.send_with_mandates(
            "user-1", user_ref="whatsapp:+221770000001", refusal=_refusal(with_quote=False),
            beneficiary_value=PHONE, amount_minor=20_000,
        )
    resource._up3 = None
    with pytest.raises(RuntimeError, match="UP3 resource not wired"):
        await resource.send_with_mandates(
            "user-1", user_ref="whatsapp:+221770000001", refusal=_refusal(),
            beneficiary_value=PHONE, amount_minor=20_000,
        )


# ---------------------------------------------------------------------------
# execution_mode (bank B-40)
# ---------------------------------------------------------------------------


def test_execution_mode_is_absent_unless_asked_so_nothing_changes_for_existing_callers():
    resource = _resource()
    cart = resource.build_deferred_cart_v02(
        _intent(resource), refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000
    )
    assert "execution_mode" not in cart["payload"]


def test_a_best_effort_cart_signs_the_mode_and_validates_against_the_bank_schema():
    resource = _resource()
    cart = resource.build_deferred_cart_v02(
        _intent(resource),
        refusal=_refusal(),
        beneficiary_value=PHONE,
        amount_minor=20_000,
        execution_mode="deferred_best_effort",
    )
    assert cart["payload"]["execution_mode"] == "deferred_best_effort"
    assert verify(cart, secret=SECRET) is True
    schema = json.loads(_SCHEMA.read_text())
    assert "execution_mode" in schema["properties"]["payload"]["properties"]
    assert "execution_mode" not in schema["properties"]["payload"]["required"]
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(cart, schema)
    # the mode is under the signature: changing it breaks the cart
    cart["payload"]["execution_mode"] = "immediate"
    assert verify(cart, secret=SECRET) is False


def test_an_unknown_execution_mode_is_refused_before_signing():
    resource = _resource()
    with pytest.raises(ValueError, match="execution_mode"):
        resource.build_deferred_cart_v02(
            _intent(resource), refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000,
            execution_mode="best_effort",
        )
    with pytest.raises(ValueError, match="execution_mode"):
        resource.build_cart_v02(_intent(resource), quote={}, execution_mode="soon")


def test_the_immediate_cart_builder_carries_the_mode_too():
    resource = _resource()
    quote = {
        "quote": {"id": QUOTE_ID, "digest": DIGEST, "digest_alg": "sha256-jcs-v1"},
        "beneficiary": {"type": "msisdn", "value": PHONE},
        "amount_minor": 20_000,
        "currency": "XOF",
        "fees_minor": {"orchestrator": 0, "bank": 0},
        "display_name": "Moussa B.",
    }
    cart = resource.build_cart_v02(_intent(resource), quote=quote, execution_mode="immediate")
    assert cart["payload"]["execution_mode"] == "immediate"
    assert "execution_mode" not in resource.build_cart_v02(_intent(resource), quote=quote)["payload"]
