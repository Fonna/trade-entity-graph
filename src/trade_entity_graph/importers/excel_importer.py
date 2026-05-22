"""Excel and CSV import entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from trade_entity_graph.importers.models import ImportSourceRow

EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
CSV_SUFFIXES = {".csv"}


def _clean_cell(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value


def _dataframe_to_rows(frame: pd.DataFrame, path: Path, sheet_name: str) -> list[ImportSourceRow]:
    rows: list[ImportSourceRow] = []
    for offset, record in enumerate(frame.to_dict(orient="records"), start=2):
        values = {str(key): _clean_cell(value) for key, value in record.items()}
        rows.append(ImportSourceRow(path.name, sheet_name, offset, values))
    return rows


def inspect_workbook(path: str | Path) -> dict[str, object]:
    """Return workbook metadata for import pre-checks."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)

    suffix = target.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        workbook = pd.ExcelFile(target)
        sheets = []
        for sheet_name in workbook.sheet_names:
            frame = workbook.parse(sheet_name=sheet_name)
            sheets.append(
                {
                    "name": sheet_name,
                    "rows": int(len(frame)),
                    "columns": [str(column) for column in frame.columns],
                }
            )
    elif suffix in CSV_SUFFIXES:
        frame = pd.read_csv(target)
        sheets = [
            {
                "name": target.stem,
                "rows": int(len(frame)),
                "columns": [str(column) for column in frame.columns],
            }
        ]
    else:
        raise ValueError(f"Unsupported import file suffix: {target.suffix}")

    return {"path": str(target), "name": target.name, "suffix": target.suffix, "sheets": sheets}


def read_tabular_rows(path: str | Path, sheet_name: str | None = None) -> list[ImportSourceRow]:
    """Read an Excel sheet or CSV file into source rows."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)

    suffix = target.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        workbook = pd.ExcelFile(target)
        selected_sheet = sheet_name or workbook.sheet_names[0]
        frame = workbook.parse(sheet_name=selected_sheet)
        return _dataframe_to_rows(frame, target, selected_sheet)

    if suffix in CSV_SUFFIXES:
        frame = pd.read_csv(target)
        return _dataframe_to_rows(frame, target, target.stem)

    raise ValueError(f"Unsupported import file suffix: {target.suffix}")
