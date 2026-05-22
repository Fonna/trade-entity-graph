"""Shared import models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImportSourceRow:
    """One row read from a source workbook or CSV file."""

    source_file: str
    source_sheet: str
    source_row: int
    values: dict[str, Any]


@dataclass(frozen=True)
class ImportInputs:
    """Input files used by one import run."""

    orders_path: Path | None = None
    entities_path: Path | None = None
    relationships_path: Path | None = None
    imported_by: str = "local_user"


@dataclass
class ImportRunResult:
    """Summary returned after an import run."""

    run_id: str
    entity_count: int = 0
    alias_count: int = 0
    evidence_count: int = 0
    claim_count: int = 0
    skipped_rows: list[str] = field(default_factory=list)
    archived_files: list[dict[str, str | int]] = field(default_factory=list)
