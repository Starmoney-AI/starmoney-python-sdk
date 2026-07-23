"""StarMoney SDK — UP3 surface.

Wraps the signing + mandate-building primitives vendored from
app/protocols/up3/ (the co-evolving reference implementation).

The `UP3Resource` is exposed as `client.up3` and also drives the
`payments.send_with_mandates()` one-call helper.

Public re-exports match the 13 UP3_* error codes from `app/protocols/up3/errors.py`
so SDK callers can catch typed exceptions without importing from app/.
"""

from .resource import UP3Resource
from .vendor.errors import (
    UP3AmountExceedsIntent,
    UP3BeneficiaryDrift,
    UP3ChainBroken,
    UP3Error,
    UP3Expired,
    UP3KeyNotRegistered,
    UP3RailDrift,
    UP3Replay,
    UP3RevisionFieldDrift,
    UP3RevisionRegression,
    UP3SchemaInvalid,
    UP3SignatureInvalid,
    UP3StatusInvalid,
    UP3TypeNotAccepted,
)

__all__ = [
    "UP3Resource",
    "UP3Error",
    "UP3AmountExceedsIntent",
    "UP3BeneficiaryDrift",
    "UP3ChainBroken",
    "UP3Expired",
    "UP3KeyNotRegistered",
    "UP3RailDrift",
    "UP3Replay",
    "UP3RevisionFieldDrift",
    "UP3RevisionRegression",
    "UP3SchemaInvalid",
    "UP3SignatureInvalid",
    "UP3StatusInvalid",
    "UP3TypeNotAccepted",
]
