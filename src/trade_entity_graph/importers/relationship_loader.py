"""Relationship candidate loading for imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from trade_entity_graph.importers.entity_loader import find_entity_id_by_name
from trade_entity_graph.importers.field_mapping import get_value
from trade_entity_graph.importers.models import ImportErrorRecord, ImportSourceRow
from trade_entity_graph.utils.ids import new_id


@dataclass
class RelationshipClaimLoadResult:
    claim_count: int = 0
    skipped_rows: list[str] = field(default_factory=list)
    import_errors: list[ImportErrorRecord] = field(default_factory=list)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def _entity_id_exists(connection: sqlite3.Connection, entity_id: Any) -> bool:
    if not entity_id:
        return False
    row = connection.execute(
        "SELECT 1 FROM entity WHERE entity_id = ?",
        (str(entity_id),),
    ).fetchone()
    return row is not None


def _resolve_endpoint(
    connection: sqlite3.Connection,
    row: ImportSourceRow,
    *,
    id_field: str,
    name_field: str,
) -> tuple[str | None, str, Any]:
    raw_id = get_value(row.values, id_field)
    if raw_id:
        entity_id = str(raw_id)
        return (entity_id if _entity_id_exists(connection, entity_id) else None, id_field, raw_id)

    raw_name = get_value(row.values, name_field)
    return find_entity_id_by_name(connection, raw_name), name_field, raw_name


def _append_endpoint_error(
    result: RelationshipClaimLoadResult,
    row: ImportSourceRow,
    *,
    run_id: str,
    normalized_field: str,
    raw_value: Any,
    message: str,
) -> None:
    result.import_errors.append(
        ImportErrorRecord(
            run_id=run_id,
            error_type="unknown_entity_reference",
            severity="blocking",
            message=message,
            file_role="relationships",
            source_path=row.source_file,
            sheet_name=row.source_sheet,
            row_number=row.source_row,
            normalized_field=normalized_field,
            raw_value=raw_value,
        )
    )


def load_relationship_claims(
    connection: sqlite3.Connection,
    rows: list[ImportSourceRow],
    *,
    run_id: str,
) -> RelationshipClaimLoadResult:
    """Load existing candidate relationship rows."""

    result = RelationshipClaimLoadResult()
    for row in rows:
        from_entity_id, from_field, from_raw_value = _resolve_endpoint(
            connection,
            row,
            id_field="from_entity_id",
            name_field="from_entity_name",
        )
        to_entity_id, to_field, to_raw_value = _resolve_endpoint(
            connection,
            row,
            id_field="to_entity_id",
            name_field="to_entity_name",
        )
        has_endpoint_error = False
        if not from_entity_id:
            has_endpoint_error = True
            _append_endpoint_error(
                result,
                row,
                run_id=run_id,
                normalized_field=from_field,
                raw_value=from_raw_value,
                message="起点企业无法匹配到主体库",
            )
        if not to_entity_id:
            has_endpoint_error = True
            _append_endpoint_error(
                result,
                row,
                run_id=run_id,
                normalized_field=to_field,
                raw_value=to_raw_value,
                message="终点企业无法匹配到主体库",
            )
        if has_endpoint_error:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: unknown relationship endpoint"
            )
            continue

        if from_entity_id == to_entity_id:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: invalid self relationship"
            )
            result.import_errors.append(
                ImportErrorRecord(
                    run_id=run_id,
                    error_type="invalid_relationship_pair",
                    severity="blocking",
                    message="起点企业和终点企业不能相同",
                    file_role="relationships",
                    source_path=row.source_file,
                    sheet_name=row.source_sheet,
                    row_number=row.source_row,
                    normalized_field="to_entity_id",
                    raw_value=to_raw_value,
                )
            )
            continue

        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                confidence_level, confidence_score, order_count, total_teu,
                recommendation_reason, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("CLM"),
                from_entity_id,
                to_entity_id,
                get_value(row.values, "candidate_relation_type", "trading_partner_candidate"),
                get_value(row.values, "confidence_level"),
                _to_float(get_value(row.values, "confidence_score")),
                _to_int(get_value(row.values, "order_count")),
                _to_float(get_value(row.values, "total_teu")) or 0,
                get_value(row.values, "recommendation_reason"),
                run_id,
            ),
        )
        result.claim_count += 1

    connection.commit()
    return result
