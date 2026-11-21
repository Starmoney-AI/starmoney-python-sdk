"""
Per-turn correlation id.

The caller sets one id for a unit of work (e.g. one customer turn in a chat
bot); every SDK request made inside the block sends it as ``X-Correlation-ID``,
so the bank's request events (``corr``) line up with the caller's own trace.

The value lives in a ``contextvars.ContextVar``: concurrent asyncio tasks each
see their own value and never mix ids. It is a plain (sync) context manager,
usable inside async code.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

MAX_CORRELATION_ID_LENGTH = 128
_VALID = re.compile(r"[A-Za-z0-9._:-]+")

_current: ContextVar[Optional[str]] = ContextVar("starmoney_correlation_id", default=None)


def get_correlation_id() -> Optional[str]:
    """Return the correlation id set by the enclosing ``correlation_id`` block, or None."""
    return _current.get()


@contextmanager
def correlation_id(value: str) -> Iterator[str]:
    """
    Send ``value`` as ``X-Correlation-ID`` on every SDK request inside the block.

    Nesting is allowed: the inner value wins, the outer one is restored on exit.
    An explicit ``X-Correlation-ID`` header passed on a call still wins over it.

    Raises:
        ValueError: if value is empty, longer than 128 characters, or has
            characters outside ``[A-Za-z0-9._:-]``.
    """
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_CORRELATION_ID_LENGTH
        or _VALID.fullmatch(value) is None
    ):
        # Never echo the value: it may be derived from user data.
        raise ValueError(
            "correlation id must be 1-128 characters from [A-Za-z0-9._:-]"
        )
    token = _current.set(value)
    try:
        yield value
    finally:
        _current.reset(token)
