"""P19 (0.3.44): every send carries customer-present proof; the SDK refuses to build one without.

``consent_evidence`` is a required keyword on the three cart builders and ``consent_token`` on both
``send_with_mandates``. A ``service_attestation`` (the old default) is refused locally, before any
HTTP call, with the same code the server would answer (UP3_TYPE_NOT_ACCEPTED).
"""

from __future__ import annotations

import pytest

from starmoney.up3 import resource as up3_resource_module
from starmoney.up3.resource import CHAT_SESSION_PIN_V1

from ._evidence import pin_evidence
from .test_up3_cart_v02 import _intent, _payments, _quote_response, _resource
from .test_up3_deferred_cart_v02 import PHONE, _dt_resource, _refusal
from .test_up3_deferred_cart_v02 import _intent as _dt_intent
from .test_up3_deferred_cart_v02 import _resource as _dt_cart_resource

SERVICE_ATTESTATION = {"type": "service_attestation", "data": {}}


def _v01_kwargs() -> dict:
    return {
        "amount_minor": 1_000,
        "beneficiary_iban": "SN12K00100152000025690007542",
        "beneficiary_name": "Rec",
        "rail": "BDK",
    }


def _builders() -> list:
    """(label, callable(consent_evidence=...)) for each of the three builders."""
    resource = _resource()
    intent = _intent(resource)
    quote = _quote_response()
    dt_resource = _dt_cart_resource()
    dt_intent = _dt_intent(dt_resource)

    def v01(**kw):
        return resource.build_cart(intent, **_v01_kwargs(), **kw)

    def v02(**kw):
        return resource.build_cart_v02(intent, quote=quote, **kw)

    def deferred(**kw):
        return dt_resource.build_deferred_cart_v02(
            dt_intent, refusal=_refusal(), beneficiary_value=PHONE, amount_minor=20_000, **kw
        )

    return [("build_cart", v01), ("build_cart_v02", v02), ("build_deferred_cart_v02", deferred)]


BUILDER_IDS = ["build_cart", "build_cart_v02", "build_deferred_cart_v02"]


@pytest.mark.parametrize("index", range(3), ids=BUILDER_IDS)
def test_builder_refuses_when_consent_evidence_is_omitted(index):
    _, build = _builders()[index]
    with pytest.raises((TypeError, ValueError)):
        build()


@pytest.mark.parametrize("index", range(3), ids=BUILDER_IDS)
def test_builder_refuses_none_and_malformed_evidence(index):
    _, build = _builders()[index]
    for bad in (None, "chat_session_pin_v1", {}, {"data": {}}):
        with pytest.raises(ValueError):
            build(consent_evidence=bad)
    with pytest.raises(ValueError, match="data"):
        build(consent_evidence={"type": CHAT_SESSION_PIN_V1, "data": "not-an-object"})


@pytest.mark.parametrize("index", range(3), ids=BUILDER_IDS)
def test_builder_refuses_service_attestation(index):
    _, build = _builders()[index]
    with pytest.raises(ValueError, match="UP3_TYPE_NOT_ACCEPTED"):
        build(consent_evidence=dict(SERVICE_ATTESTATION))


@pytest.mark.parametrize("index", range(3), ids=BUILDER_IDS)
def test_pin_block_passes_through_untouched_into_the_cart(index):
    _, build = _builders()[index]
    evidence = pin_evidence()
    snapshot = {"type": evidence["type"], "data": dict(evidence["data"])}
    cart = build(consent_evidence=evidence)
    assert cart["payload"]["user_consent_evidence"] == snapshot
    assert evidence == snapshot  # the caller's dict is not mutated


@pytest.mark.asyncio
async def test_payments_send_with_mandates_refuses_service_attestation_before_any_http_call():
    resource, http = _payments()
    with pytest.raises(ValueError, match="UP3_TYPE_NOT_ACCEPTED"):
        await resource.send_with_mandates(
            user_id="user-1",
            user_ref="whatsapp:+221770000001",
            quote=_quote_response(),
            description="loyer",
            idempotency_seed="consent-jti-1",
            consent_token=dict(SERVICE_ATTESTATION),
        )
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_payments_send_with_mandates_refuses_a_missing_consent_token():
    resource, http = _payments()
    with pytest.raises((TypeError, ValueError)):
        await resource.send_with_mandates(
            user_id="user-1",
            user_ref="whatsapp:+221770000001",
            quote=_quote_response(),
            description="loyer",
            idempotency_seed="consent-jti-1",
        )
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_deferred_send_with_mandates_refuses_service_attestation_before_any_http_call():
    resource, http = _dt_resource()
    with pytest.raises(ValueError, match="UP3_TYPE_NOT_ACCEPTED"):
        await resource.send_with_mandates(
            "user-1",
            user_ref="whatsapp:+221770000001",
            refusal=_refusal(),
            beneficiary_value=PHONE,
            amount_minor=20_000,
            idempotency_seed="consent-jti-1",
            consent_token=dict(SERVICE_ATTESTATION),
        )
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_deferred_send_with_mandates_refuses_a_missing_consent_token():
    resource, http = _dt_resource()
    with pytest.raises((TypeError, ValueError)):
        await resource.send_with_mandates(
            "user-1",
            user_ref="whatsapp:+221770000001",
            refusal=_refusal(),
            beneficiary_value=PHONE,
            amount_minor=20_000,
            idempotency_seed="consent-jti-1",
        )
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_a_pin_block_travels_to_the_wire_inside_the_signed_cart():
    resource, http = _payments()
    evidence = pin_evidence()
    await resource.send_with_mandates(
        user_id="user-1",
        user_ref="whatsapp:+221770000001",
        quote=_quote_response(),
        description="loyer",
        idempotency_seed="consent-jti-1",
        consent_token=evidence,
    )
    cart = http.post.call_args.kwargs["json"]["cart_mandate"]
    assert cart["payload"]["user_consent_evidence"] == evidence


def test_chat_session_pin_constant_value():
    assert CHAT_SESSION_PIN_V1 == "chat_session_pin_v1"
    assert up3_resource_module.CHAT_SESSION_PIN_V1 == "chat_session_pin_v1"


def test_the_helper_block_has_the_documented_shape():
    import re

    block = pin_evidence()
    assert block["type"] == CHAT_SESSION_PIN_V1
    assert block["data"]["attempt_count"] == 1
    assert re.fullmatch(r"sha256:[A-Za-z0-9_-]{43}", block["data"]["session_id_hash"])
    assert pin_evidence()["data"]["session_id_hash"] != block["data"]["session_id_hash"]
