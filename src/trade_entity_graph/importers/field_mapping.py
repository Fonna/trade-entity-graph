"""Field alias helpers for import sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trade_entity_graph.importers.models import ImportErrorRecord, ImportSourceRow

_MAPPING_PATH = Path(__file__).with_name("field_mappings") / "default.json"


def _load_default_mapping() -> dict[str, Any]:
    with _MAPPING_PATH.open("r", encoding="utf-8-sig") as mapping_file:
        return json.load(mapping_file)


DEFAULT_FIELD_MAPPING = _load_default_mapping()
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    field_name: tuple(aliases)
    for role_config in DEFAULT_FIELD_MAPPING["roles"].values()
    for field_name, aliases in role_config["fields"].items()
}


def normalize_key(value: str) -> str:
    """Normalize a source column name for alias matching."""

    normalized = value.replace("\N{IDEOGRAPHIC SPACE}", " ").strip().lower()
    return "".join(ch for ch in normalized if ch not in {" ", "_", "-"})


_ROLE_ALIAS_LOOKUPS: dict[str, dict[str, str]] = {
    role: {
        normalize_key(alias): field_name
        for field_name, aliases in role_config["fields"].items()
        for alias in aliases
    }
    for role, role_config in DEFAULT_FIELD_MAPPING["roles"].items()
}


def get_value(row: dict[str, Any], field_name: str, default: Any = None) -> Any:
    """Return a logical field value from a source row."""

    if field_name in row:
        return row[field_name]

    normalized_row = {normalize_key(key): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field_name]:
        normalized_alias = normalize_key(alias)
        if normalized_alias in normalized_row:
            return normalized_row[normalized_alias]
    return default


def resolve_rows_for_role(
    rows: list[ImportSourceRow], *, role: str, run_id: str
) -> tuple[list[ImportSourceRow], list[ImportErrorRecord]]:
    """Resolve source-row column aliases into canonical field names for one import role."""

    role_mappings = DEFAULT_FIELD_MAPPING["roles"]
    if role not in role_mappings:
        supported_roles = ", ".join(sorted(role_mappings))
        raise ValueError(
            f"Unsupported import file role: {role}. Supported roles: {supported_roles}"
        )

    role_config = role_mappings[role]
    required_fields = set(role_config["required"])
    alias_lookup = _ROLE_ALIAS_LOOKUPS[role]
    resolved_rows: list[ImportSourceRow] = []
    errors: list[ImportErrorRecord] = []
    has_blocking_error = False

    for row in rows:
        resolved_values: dict[str, Any] = {}
        matched_columns_by_field: dict[str, list[str]] = {}

        for column_name, raw_value in row.values.items():
            normalized_column = normalize_key(column_name)
            field_name = alias_lookup.get(normalized_column)
            if field_name is None:
                continue
            matched_columns_by_field.setdefault(field_name, []).append(column_name)
            if field_name not in resolved_values:
                resolved_values[field_name] = raw_value

        for field_name, matched_columns in matched_columns_by_field.items():
            if len(matched_columns) > 1:
                errors.append(
                    ImportErrorRecord(
                        run_id=run_id,
                        error_type="field_mapping_error",
                        severity="warning",
                        message=(
                            f"Multiple source columns map to {field_name}; "
                            f"using {matched_columns[0]}."
                        ),
                        file_role=role,
                        source_path=row.source_file,
                        sheet_name=row.source_sheet,
                        row_number=row.source_row,
                        column_name=matched_columns[0],
                        normalized_field=field_name,
                        raw_value=resolved_values.get(field_name),
                    )
                )

        for required_field in required_fields:
            if required_field not in resolved_values:
                has_blocking_error = True
                errors.append(
                    ImportErrorRecord(
                        run_id=run_id,
                        error_type="missing_required_field",
                        severity="blocking",
                        message=f"Missing required field: {required_field}.",
                        file_role=role,
                        source_path=row.source_file,
                        sheet_name=row.source_sheet,
                        row_number=row.source_row,
                        normalized_field=required_field,
                    )
                )

        resolved_rows.append(
            ImportSourceRow(
                source_file=row.source_file,
                source_sheet=row.source_sheet,
                source_row=row.source_row,
                values=resolved_values,
            )
        )

    if has_blocking_error:
        return [], errors
    return resolved_rows, errors
