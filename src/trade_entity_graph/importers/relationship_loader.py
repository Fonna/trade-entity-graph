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
    success_rows: int = 0
    skipped_rows: list[str] = field(default_factory=list)
    import_errors: list[ImportErrorRecord] = field(default_factory=list)


@dataclass
class ConfirmedRelationshipLoadResult:
    curated_relationship_count: int = 0
    success_rows: int = 0
    skipped_rows: list[str] = field(default_factory=list)
    import_errors: list[ImportErrorRecord] = field(default_factory=list)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value != value


def _clean_text(value: Any) -> str | None:
    if _is_blank(value):
        return None
    return str(value).strip()


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
    result: Any,
    row: ImportSourceRow,
    *,
    run_id: str,
    normalized_field: str,
    raw_value: Any,
    message: str,
    file_role: str = "relationships",
) -> None:
    result.import_errors.append(
        ImportErrorRecord(
            run_id=run_id,
            error_type="unknown_entity_reference",
            severity="blocking",
            message=message,
            file_role=file_role,
            source_path=row.source_file,
            sheet_name=row.source_sheet,
            row_number=row.source_row,
            normalized_field=normalized_field,
            raw_value=raw_value,
        )
    )


def _append_numeric_error(
    result: Any,
    row: ImportSourceRow,
    *,
    run_id: str,
    normalized_field: str,
    raw_value: Any,
    file_role: str = "relationships",
) -> None:
    result.import_errors.append(
        ImportErrorRecord(
            run_id=run_id,
            error_type="invalid_numeric_value",
            severity="blocking",
            message=f"{normalized_field} must be numeric.",
            file_role=file_role,
            source_path=row.source_file,
            sheet_name=row.source_sheet,
            row_number=row.source_row,
            normalized_field=normalized_field,
            raw_value=raw_value,
        )
    )


def _append_missing_required_error(
    result: Any,
    row: ImportSourceRow,
    *,
    run_id: str,
    normalized_field: str,
    file_role: str,
) -> None:
    result.import_errors.append(
        ImportErrorRecord(
            run_id=run_id,
            error_type="missing_required_field",
            severity="blocking",
            message=f"Missing required field: {normalized_field}.",
            file_role=file_role,
            source_path=row.source_file,
            sheet_name=row.source_sheet,
            row_number=row.source_row,
            normalized_field=normalized_field,
        )
    )


def _append_invalid_pair_error(
    result: Any,
    row: ImportSourceRow,
    *,
    run_id: str,
    normalized_field: str,
    raw_value: Any,
    file_role: str,
) -> None:
    result.import_errors.append(
        ImportErrorRecord(
            run_id=run_id,
            error_type="invalid_relationship_pair",
            severity="blocking",
            message="from_entity_id and to_entity_id must be different.",
            file_role=file_role,
            source_path=row.source_file,
            sheet_name=row.source_sheet,
            row_number=row.source_row,
            normalized_field=normalized_field,
            raw_value=raw_value,
        )
    )


def _confirmed_decision_source(run_id: str, row: ImportSourceRow) -> str:
    return f"{run_id}:{row.source_file}:{row.source_sheet}:{row.source_row}"


def _write_confirmed_decision_and_audit(
    connection: sqlite3.Connection,
    *,
    relationship_id: str,
    relation_type: str,
    relation_status: str,
    reason: str,
    operator: str,
) -> None:
    connection.execute(
        """
        INSERT INTO relationship_decision (
            decision_id, relationship_id, claim_id, action_type, before_relation_type,
            after_relation_type, before_status, after_status, reason, operator
        )
        VALUES (?, ?, NULL, 'import_confirmed', NULL, ?, NULL, ?, ?, ?)
        """,
        (
            new_id("DEC"),
            relationship_id,
            relation_type,
            relation_status,
            reason,
            operator,
        ),
    )
    connection.execute(
        """
        INSERT INTO audit_log (
            audit_id, object_type, object_id, action_type, after_value, operator, reason
        )
        VALUES (?, 'curated_relationship', ?, 'import_confirmed', ?, ?, ?)
        """,
        (
            new_id("AUD"),
            relationship_id,
            relation_status,
            operator,
            reason,
        ),
    )


def load_confirmed_relationships(
    connection: sqlite3.Connection,
    rows: list[ImportSourceRow],
    *,
    run_id: str,
    imported_by: str,
) -> ConfirmedRelationshipLoadResult:
    """Load already-confirmed relationship rows as final curated records."""

    result = ConfirmedRelationshipLoadResult()
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
                message="Confirmed relationship source entity could not be resolved.",
                file_role="confirmed_relationships",
            )
        if not to_entity_id:
            has_endpoint_error = True
            _append_endpoint_error(
                result,
                row,
                run_id=run_id,
                normalized_field=to_field,
                raw_value=to_raw_value,
                message="Confirmed relationship target entity could not be resolved.",
                file_role="confirmed_relationships",
            )
        if has_endpoint_error:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: unknown confirmed relationship endpoint"
            )
            continue

        if from_entity_id == to_entity_id:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: invalid self relationship"
            )
            _append_invalid_pair_error(
                result,
                row,
                run_id=run_id,
                normalized_field="to_entity_id",
                raw_value=to_raw_value,
                file_role="confirmed_relationships",
            )
            continue

        relation_type = _clean_text(get_value(row.values, "relation_type"))
        if relation_type is None:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: missing confirmed relation type"
            )
            _append_missing_required_error(
                result,
                row,
                run_id=run_id,
                normalized_field="relation_type",
                file_role="confirmed_relationships",
            )
            continue

        raw_confidence_score = get_value(row.values, "confidence_score")
        try:
            confidence_score = _to_float(raw_confidence_score)
        except (TypeError, ValueError):
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: invalid confirmed relationship numeric value"
            )
            _append_numeric_error(
                result,
                row,
                run_id=run_id,
                normalized_field="confidence_score",
                raw_value=raw_confidence_score,
                file_role="confirmed_relationships",
            )
            continue

        relationship_id = new_id("REL")
        relation_status = _clean_text(get_value(row.values, "relation_status")) or "verified"
        source_type = _clean_text(get_value(row.values, "source_type")) or "imported_confirmed"
        decision_note = (
            _clean_text(get_value(row.values, "decision_note"))
            or "imported confirmed relationship"
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, confidence_level, confidence_score, source_type,
                decision_source, decision_note, verified_by, verified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                relationship_id,
                from_entity_id,
                to_entity_id,
                relation_type,
                relation_status,
                _clean_text(get_value(row.values, "confidence_level")),
                confidence_score,
                source_type,
                _confirmed_decision_source(run_id, row),
                decision_note,
                imported_by,
            ),
        )
        _write_confirmed_decision_and_audit(
            connection,
            relationship_id=relationship_id,
            relation_type=relation_type,
            relation_status=relation_status,
            reason=decision_note,
            operator=imported_by,
        )
        result.curated_relationship_count += 1
        result.success_rows += 1

    connection.commit()
    return result


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

        raw_confidence_score = get_value(row.values, "confidence_score")
        raw_order_count = get_value(row.values, "order_count")
        raw_total_teu = get_value(row.values, "total_teu")
        numeric_values: dict[str, float | int | None] = {}
        has_numeric_error = False
        for field_name, raw_value, parser in (
            ("confidence_score", raw_confidence_score, _to_float),
            ("order_count", raw_order_count, _to_int),
            ("total_teu", raw_total_teu, _to_float),
        ):
            try:
                numeric_values[field_name] = parser(raw_value)
            except (TypeError, ValueError):
                has_numeric_error = True
                _append_numeric_error(
                    result,
                    row,
                    run_id=run_id,
                    normalized_field=field_name,
                    raw_value=raw_value,
                )
        if has_numeric_error:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: invalid relationship numeric value"
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
                numeric_values["confidence_score"],
                numeric_values["order_count"],
                numeric_values["total_teu"] or 0,
                get_value(row.values, "recommendation_reason"),
                run_id,
            ),
        )
        result.claim_count += 1
        result.success_rows += 1

    connection.commit()
    return result
