"""Vendored UP3 protocol primitives.

These files are minimal copies of app/protocols/up3/{signing,errors}.py with:
  - No imports from app.* or starmoney_bank_service.*
  - No jsonschema / pydantic validators (those live in validators.py which is
    server-only; the SDK only needs sign + verify + error hierarchy).

When `pip install up3` is available (post-publication), replace these with:
    from up3 import sign, verify, canonicalize
    from up3.errors import UP3Error, ...

The API is intentionally identical so the swap is a one-line import change.
"""
