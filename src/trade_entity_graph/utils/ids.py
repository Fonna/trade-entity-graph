"""Identifier helpers for MVP records."""

from __future__ import annotations

from uuid import uuid4


def new_id(prefix: str) -> str:
    """Return a prefixed, compact unique identifier."""

    return f"{prefix}_{uuid4().hex[:12].upper()}"
