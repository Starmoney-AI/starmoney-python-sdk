"""SDK unit tests — UP3Resource: build_intent, build_cart, verify_payment_mandate.

Also tests the reference vector from SPEC.md §4.3 / docs/up3-chatbot-integration.md §4.3
to confirm byte-exact interop with the server-side signing implementation.
"""

from __future__ import annotations

import pytest
import re
import datetime

from starmoney.up3.resource import UP3Resource, _mandate_id
from starmoney.up3.vendor.signing import sign, verify, canonicalize
from starmoney.up3.vendor.errors import UP3SignatureInvalid


SECRET = b"test-secret-for-sdk-unit-tests"
ISSUER = "test-sdk"


# ---------------------------------------------------------------------------
# Reference vector — byte-exact interop check (SPEC.md §4.3)
# ---------------------------------------------------------------------------

REFERENCE_ENVELOPE = {
    "version": "0.1",
    "type": "intent",
    "id": "mnd_00000000000000000000000000",
    "issued_at": "2026-01-01T00:00:00Z",
    "expires_at": "2026-01-01T00:15:00Z",
    "issuer": "reference",
    "payload": {
        "user_ref": "whatsapp:+221770000000",
        "description": "reference vector",
        "max_amount_minor": 1000,
        "currency": "XOF",
        "beneficiary_hint": None,
        "rail_hint": None,
    },
}
REFERENCE_SECRET = b"reference-vector-secret-v0.1"
REFERENCE_HMAC_HEX = "6e95ae9de07a74b0b3456b6d3d08e9be4325b127b6080d3eace7c9559bf22c54"
REFERENCE_SIG_VALUE = "bpWuneB6dLCzRWttPQjpvkMlsSe2CA0-rOfJVZvyLFQ"


def test_reference_canonical_bytes_produce_correct_hmac():
    import hashlib
    import hmac as _hmac

    canonical = canonicalize(REFERENCE_ENVELOPE)
    mac = _hmac.new(REFERENCE_SECRET, canonical, hashlib.sha256)
    assert mac.hexdigest() == REFERENCE_HMAC_HEX


def test_reference_signature_value_matches():
    sig = sign(REFERENCE_ENVELOPE, secret=REFERENCE_SECRET)
    assert sig["value"] == REFERENCE_SIG_VALUE


def test_reference_full_signature_dict():
    sig = sign(REFERENCE_ENVELOPE, secret=REFERENCE_SECRET)
    assert sig["alg"] == "HS256-JCS"
    assert sig["key_id"] == "reference"
    assert sig["value"] == REFERENCE_SIG_VALUE


def test_verify_returns_true_for_valid_envelope():
    envelope = {**REFERENCE_ENVELOPE}
    envelope["signature"] = sign(envelope, secret=REFERENCE_SECRET)
    assert verify(envelope, secret=REFERENCE_SECRET) is True


def test_verify_returns_false_for_wrong_secret():
    envelope = {**REFERENCE_ENVELOPE}
    envelope["signature"] = sign(envelope, secret=REFERENCE_SECRET)
    assert verify(envelope, secret=b"wrong-secret") is False


def test_verify_returns_false_for_tampered_envelope():
    envelope = {**REFERENCE_ENVELOPE, "issuer": "tampered"}
    envelope["signature"] = sign(REFERENCE_ENVELOPE, secret=REFERENCE_SECRET)
    assert verify(envelope, secret=REFERENCE_SECRET) is False


# ---------------------------------------------------------------------------
# _mandate_id helper
# ---------------------------------------------------------------------------


def test_mandate_id_format():
    mid = _mandate_id()
    assert re.match(r"^mnd_[A-Z0-9]{26}$", mid), f"Bad format: {mid!r}"


def test_mandate_id_unique():
    ids = {_mandate_id() for _ in range(100)}
    assert len(ids) == 100


# ---------------------------------------------------------------------------
# build_intent
# ---------------------------------------------------------------------------


def test_build_intent_structure():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    intent = resource.build_intent(
        user_ref="whatsapp:+221770000001",
        description="send 5000 XOF to Fatou",
        max_amount_minor=5000,
        currency="XOF",
        beneficiary_hint="Fatou",
    )

    assert intent["version"] == "0.1"
    assert intent["type"] == "intent"
    assert intent["issuer"] == ISSUER
    assert re.match(r"^mnd_[A-Z0-9]{26}$", intent["id"])
    assert intent["issued_at"].endswith("Z")
    assert intent["expires_at"].endswith("Z")

    payload = intent["payload"]
    assert payload["user_ref"] == "whatsapp:+221770000001"
    assert payload["max_amount_minor"] == 5000
    assert payload["currency"] == "XOF"
    assert payload["beneficiary_hint"] == "Fatou"
    assert payload["rail_hint"] is None

    sig = intent["signature"]
    assert sig["alg"] == "HS256-JCS"
    assert sig["key_id"] == ISSUER


def test_build_intent_signature_verifies():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    intent = resource.build_intent(
        user_ref="whatsapp:+221770000001",
        description="test",
        max_amount_minor=1000,
        currency="XOF",
    )
    assert verify(intent, secret=SECRET) is True


def test_build_intent_ttl_capped_at_60():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    intent = resource.build_intent(
        user_ref="ref",
        description="test",
        max_amount_minor=100,
        currency="XOF",
        ttl_minutes=999,
    )
    issued = datetime.datetime.fromisoformat(intent["issued_at"].replace("Z", "+00:00"))
    expires = datetime.datetime.fromisoformat(intent["expires_at"].replace("Z", "+00:00"))
    delta_minutes = (expires - issued).total_seconds() / 60
    assert delta_minutes <= 60 + 1  # 1 min tolerance for clock advance


# ---------------------------------------------------------------------------
# build_cart
# ---------------------------------------------------------------------------


def test_build_cart_structure_and_chain():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    intent = resource.build_intent(
        user_ref="whatsapp:+221770000001",
        description="send 5000 XOF to Fatou",
        max_amount_minor=5000,
        currency="XOF",
    )
    confirmed_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cart = resource.build_cart(
        intent,
        amount_minor=5000,
        beneficiary_iban="SN12K00100152000025690000754",
        beneficiary_name="Fatou Ndiaye",
        rail="BDK_RTGS",
        fees_minor={"orchestrator": 50},
        confirmed_at=confirmed_at,
    )

    assert cart["type"] == "cart"
    assert cart["issuer"] == ISSUER
    payload = cart["payload"]
    assert payload["intent_mandate_id"] == intent["id"]
    assert payload["user_ref"] == "whatsapp:+221770000001"
    assert payload["amount_minor"] == 5000
    assert payload["currency"] == "XOF"
    assert payload["beneficiary_iban"] == "SN12K00100152000025690000754"
    assert payload["rail"] == "BDK_RTGS"
    assert payload["fees_minor"] == {"orchestrator": 50}
    assert payload["confirmed_at"] == confirmed_at
    # v0.1 default
    assert payload["user_consent_evidence"]["type"] == "service_attestation"
    assert payload["user_consent_evidence"]["data"] == {}


def test_build_cart_signature_verifies():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    intent = resource.build_intent(
        user_ref="ref",
        description="test",
        max_amount_minor=1000,
        currency="XOF",
    )
    cart = resource.build_cart(
        intent,
        amount_minor=1000,
        beneficiary_iban="SN12K00100152000025690000754",
        beneficiary_name="Rec",
        rail="BDK_RTGS",
    )
    assert verify(cart, secret=SECRET) is True


def test_build_cart_default_service_attestation():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    intent = resource.build_intent(
        user_ref="ref",
        description="test",
        max_amount_minor=1000,
        currency="XOF",
    )
    cart = resource.build_cart(
        intent,
        amount_minor=500,
        beneficiary_iban="SN12K00100152000025690000754",
        beneficiary_name="Rec",
        rail="BDK_RTGS",
    )
    ev = cart["payload"]["user_consent_evidence"]
    assert ev["type"] == "service_attestation"
    assert ev["data"] == {}


# ---------------------------------------------------------------------------
# verify_payment_mandate
# ---------------------------------------------------------------------------


def _build_fake_payment_mandate(resource: UP3Resource, cart_id: str) -> dict:
    from starmoney.up3.resource import _mandate_id, _now_z, _future_z
    from starmoney.up3.vendor.signing import sign as _sign

    pm_id = _mandate_id()
    envelope: dict = {
        "version": "0.1",
        "type": "payment",
        "id": pm_id,
        "revision": 1,
        "issued_at": _now_z(),
        "expires_at": _future_z(60),
        "issuer": ISSUER,
        "payload": {
            "cart_mandate_id": cart_id,
            "client_transaction_id": cart_id,
            "rail": "BDK_RTGS",
            "amount_minor": 5000,
            "currency": "XOF",
            "beneficiary_iban": "SN12K00100152000025690000754",
            "submitted_at": _now_z(),
            "status": "submitted",
            "rail_transaction_id": None,
            "rail_status_code": None,
            "settled_at": None,
        },
    }
    envelope["signature"] = _sign(envelope, secret=SECRET)
    return envelope


def test_verify_payment_mandate_returns_true_for_valid():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    pm = _build_fake_payment_mandate(resource, "mnd_CARTID0000000000000000000")
    assert resource.verify_payment_mandate(pm) is True


def test_verify_payment_mandate_returns_false_for_wrong_secret():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    pm = _build_fake_payment_mandate(resource, "mnd_CARTID0000000000000000000")
    other_resource = UP3Resource(secret=b"other-secret-bytes-longer-than-16", issuer=ISSUER)
    assert other_resource.verify_payment_mandate(pm) is False


def test_verify_payment_mandate_strict_raises_on_failure():
    resource = UP3Resource(secret=SECRET, issuer=ISSUER)
    pm = _build_fake_payment_mandate(resource, "mnd_CARTID0000000000000000000")
    other = UP3Resource(secret=b"wrong-secret-bytes-longer-than-16", issuer=ISSUER)
    with pytest.raises(UP3SignatureInvalid):
        other.verify_payment_mandate_strict(pm)


# ---------------------------------------------------------------------------
# Client wiring
# ---------------------------------------------------------------------------


def test_client_exposes_up3_property():
    from starmoney.client import StarmoneyClient

    client = StarmoneyClient(
        jwt_secret="test-jwt-secret-at-least-32-chars",
        issuer="test",
        up3_secret="test-up3-secret-at-least-32-chars",
    )
    assert isinstance(client.up3, UP3Resource)


def test_client_wires_up3_into_payments():
    from starmoney.client import StarmoneyClient

    client = StarmoneyClient(
        jwt_secret="test-jwt-secret-at-least-32-chars",
        issuer="test",
    )
    payments = client.payments
    assert payments._up3 is client.up3
