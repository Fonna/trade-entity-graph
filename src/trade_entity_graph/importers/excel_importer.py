"""Excel import entry points.

M2 will implement workbook parsing, field mapping, entity loading, evidence loading,
and order-role edge generation.
"""

from __future__ import annotations

from pathlib import Path


def inspect_workbook(path: str | Path) -> dict[str, object]:
    """Return basic workbook metadata for import pre-checks."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    return {"path": str(target), "name": target.name, "suffix": target.suffix}
