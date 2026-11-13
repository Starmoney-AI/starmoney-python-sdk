"""Shared test helper: a well-formed ``chat_session_pin_v1`` consent-evidence block (P19, 0.3.44)."""

from __future__ import annotations

import base64
import datetime as _dt
import os
from typing import Any, Optional


def _parse_z(value: str) -> _dt.datetime:
    return _dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)


def pin_evidence(
    confirmed_at: Optional[str] = None,
    *,
    age_seconds: int = 5,
    session_id_hash: Optional[str] = None,
) -> dict[str, Any]:
    """Build a ``chat_session_pin_v1`` block verified ``age_seconds`` before ``confirmed_at`` (or now)."""
    anchor = _parse_z(confirmed_at) if confirmed_at else _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    verified_at = (anchor - _dt.timedelta(seconds=age_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if session_id_hash is None:
        # 32 random bytes -> 43 base64url characters (no padding), fresh per call.
        session_id_hash = "sha256:" + base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    return {
        "type": "chat_session_pin_v1",
        "data": {
            "verified_at": verified_at,
            "attempt_count": 1,
            "session_id_hash": session_id_hash,
        },
    }
