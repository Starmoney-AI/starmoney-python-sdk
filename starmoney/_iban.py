"""IBAN validation helpers (self-contained, no server imports).

Mirrors the server's ``app.utils.validators.IBANValidator`` rules so the SDK
can reject a bad IBAN client-side — before the round-trip — when adding a
beneficiary. The server remains the source of truth and re-validates; this is
a fast-fail convenience so callers (e.g. the chatbot) get an immediate,
distinguishable ``InvalidIBANError`` instead of a generic API failure.
"""

from __future__ import annotations

import re

_IBAN_REGEX = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}([A-Z0-9]?){0,16}$")


def normalize_iban(iban: str) -> str:
    """Strip spaces/hyphens and uppercase."""
    return (iban or "").replace(" ", "").replace("-", "").upper()


def is_valid_iban(iban: str) -> bool:
    """Return True iff ``iban`` is structurally well-formed AND passes mod-97.

    Combines format/length validation with the full ISO 13616 (ISO 7064
    MOD 97-10) check-digit test, so a well-formed but mistyped IBAN (a
    transposed or wrong digit) is rejected.
    """
    if not iban:
        return False
    normalized = normalize_iban(iban)
    if not _IBAN_REGEX.match(normalized):
        return False
    rearranged = normalized[4:] + normalized[:4]
    # A=10..Z=35, digits map to themselves; regex guarantees only [0-9A-Z].
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1
