"""Name normalization helpers."""

from __future__ import annotations

import re

_SPACES = re.compile(r"\s+")


def normalize_company_name(value: str | None) -> str:
    """Normalize whitespace and casing for basic entity search."""

    if not value:
        return ""
    return _SPACES.sub(" ", value.strip()).upper()
