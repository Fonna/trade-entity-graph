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


@dataclass(frozen=True)
class ImportErrorRecord:
    """Structured import problem with source-row traceability."""

    run_id: str
    error_type: str
    severity: str
    message: str
    source_file_id: str | None = None
    file_role: str | None = None
    source_path: str | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    column_name: str | None = None
    normalized_field: str | None = None
    raw_value: Any | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_file_id": self.source_file_id,
            "file_role": self.file_role,
            "source_path": self.source_path,
            "sheet_name": self.sheet_name,
            "row_number": self.row_number,
            "column_name": self.column_name,
            "normalized_field": self.normalized_field,
            "raw_value": None if self.raw_value is None else str(self.raw_value),
            "error_type": self.error_type,
            "severity": self.severity,
            "message": self.message,
        }


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
    import_errors: list[dict[str, Any]] = field(default_factory=list)
    warning_count: int = 0
    error_count: int = 0
    quality_summary: dict[str, Any] = field(default_factory=dict)
