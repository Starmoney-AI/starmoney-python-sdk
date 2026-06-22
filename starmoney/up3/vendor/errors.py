"""UP3 error hierarchy — vendored from app/protocols/up3/errors.py.

Byte-identical to the server-side module. Maps to SPEC.md §6.1 error taxonomy.
The 13 error codes are stable across v0.x.

IMPORTANT: This module MUST NOT import from app/ or starmoney_bank_service/.
"""

from __future__ import annotations


class UP3Error(Exception):
    """Base class for all UP3 protocol errors."""

    code: str = "UP3_UNKNOWN"

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}" if self.message else self.code


class UP3SignatureInvalid(UP3Error):
    code = "UP3_SIG_INVALID"


class UP3KeyNotRegistered(UP3Error):
    code = "UP3_KEY_NOT_REGISTERED"


class UP3ChainBroken(UP3Error):
    code = "UP3_CHAIN_BROKEN"


class UP3Expired(UP3Error):
    code = "UP3_EXPIRED"


class UP3Replay(UP3Error):
    code = "UP3_REPLAY"


class UP3AmountExceedsIntent(UP3Error):
    code = "UP3_AMOUNT_EXCEEDS_INTENT"


class UP3SchemaInvalid(UP3Error):
    code = "UP3_SCHEMA_INVALID"


class UP3TypeNotAccepted(UP3Error):
    code = "UP3_TYPE_NOT_ACCEPTED"


class UP3RevisionFieldDrift(UP3Error):
    code = "UP3_REVISION_FIELD_DRIFT"


class UP3StatusInvalid(UP3Error):
    code = "UP3_STATUS_INVALID"


class UP3BeneficiaryDrift(UP3Error):
    code = "UP3_BENEFICIARY_DRIFT"


class UP3RailDrift(UP3Error):
    code = "UP3_RAIL_DRIFT"


class UP3RevisionRegression(UP3Error):
    code = "UP3_REVISION_REGRESSION"


__all__ = [
    "UP3Error",
    "UP3SignatureInvalid",
    "UP3KeyNotRegistered",
    "UP3ChainBroken",
    "UP3Expired",
    "UP3Replay",
    "UP3AmountExceedsIntent",
    "UP3SchemaInvalid",
    "UP3TypeNotAccepted",
    "UP3RevisionFieldDrift",
    "UP3StatusInvalid",
    "UP3BeneficiaryDrift",
    "UP3RailDrift",
    "UP3RevisionRegression",
]
