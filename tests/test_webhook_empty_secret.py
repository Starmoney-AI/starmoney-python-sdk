"""An empty webhook secret never validates a signature (fail closed)."""

import hashlib
import hmac

import pytest

from starmoney.webhooks.validator import WebhookValidator

BODY = b'{"event_type":"payment.received"}'


@pytest.mark.parametrize("secret", ["", None])
def test_an_empty_secret_refuses_a_body_signed_with_the_empty_key(secret):
    forged = hmac.new(b"", BODY, hashlib.sha256).hexdigest()
    assert WebhookValidator(webhook_secret=secret).verify_signature(BODY, f"sha256={forged}") is False


def test_a_missing_signature_header_is_refused():
    assert WebhookValidator(webhook_secret="s3cret").verify_signature(BODY, "") is False


def test_a_real_secret_still_verifies():
    good = hmac.new(b"s3cret", BODY, hashlib.sha256).hexdigest()
    assert WebhookValidator(webhook_secret="s3cret").verify_signature(BODY, f"sha256={good}")
