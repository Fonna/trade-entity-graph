"""Import batch quality reporting queries."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection

ERROR_EXPORT_COLUMNS: tuple[str, ...] = (
    "error_id",
    "run_id",
    "source_file_id",
    "file_role",
    "source_path",
    "sheet_name",
    "row_number",
    "column_name",
    "normalized_field",
    "raw_value",
    "error_type",
    "severity",
    "message",
    "created_at",
)


def _safe_limit(value: int, maximum: int) -> int:
    return max(1, min(int(value), maximum))


def _safe_offset(value: int) -> int:
    return max(0, int(value))


def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _import_error_order_by() -> str:
    return """
        CASE severity WHEN 'blocking' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
        created_at,
        error_id
    """


def _list_all_import_errors(connection: Any, run_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        f"""
        SELECT *
        FROM import_error
        WHERE run_id = ?
        ORDER BY {_import_error_order_by()}
        """,
        (run_id,),
    ).fetchall()
    return _rows_to_dicts(rows)


def _quality_summary(connection: Any, run_id: str) -> dict[str, Any]:
    severity_rows = connection.execute(
        """
        SELECT severity, COUNT(*) AS count
        FROM import_error
        WHERE run_id = ?
        GROUP BY severity
        ORDER BY severity
        """,
        (run_id,),
    ).fetchall()
    type_rows = connection.execute(
        """
        SELECT error_type, COUNT(*) AS count
        FROM import_error
        WHERE run_id = ?
        GROUP BY error_type
        ORDER BY error_type
        """,
        (run_id,),
    ).fetchall()

    severity_counts = {row["severity"]: row["count"] for row in severity_rows}
    return {
        "blocking_error_count": severity_counts.get("blocking", 0),
        "warning_count": severity_counts.get("warning", 0),
        "error_count_by_type": {row["error_type"]: row["count"] for row in type_rows},
        "error_count_by_severity": severity_counts,
    }


def _entity_count(connection: Any, run_id: str) -> int:
    rows = connection.execute(
        """
        SELECT entity_id
        FROM entity_alias
        WHERE run_id = ?
        GROUP BY entity_id
        """,
        (run_id,),
    ).fetchall()
    return len(rows)


def _batch_status_sql() -> str:
    return """
        CASE
            WHEN COALESCE(q.blocking_error_count, 0) > 0 THEN 'failed'
            WHEN COALESCE(b.error_rows, 0) > 0 THEN 'failed'
            WHEN COALESCE(q.warning_count, 0) > 0 THEN 'warning'
            ELSE 'success'
        END
    """


def list_import_batches(
    *,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """List import batches with compact quality counts."""

    safe_limit = _safe_limit(limit, 200)
    safe_offset = _safe_offset(offset)
    status_value = status.strip() if status else None
    status_sql = _batch_status_sql()
    where_clause = "WHERE import_status = ?" if status_value else ""
    params: list[Any] = [status_value] if status_value else []

    query = f"""
        WITH q AS (
            SELECT
                run_id,
                SUM(CASE WHEN severity = 'blocking' THEN 1 ELSE 0 END) AS blocking_error_count,
                SUM(CASE WHEN severity = 'warning' THEN 1 ELSE 0 END) AS warning_count
            FROM import_error
            GROUP BY run_id
        ),
        batches AS (
            SELECT
                b.*,
                COALESCE(q.blocking_error_count, 0) AS blocking_error_count,
                COALESCE(q.warning_count, 0) AS warning_count,
                {status_sql} AS import_status
            FROM import_batch b
            LEFT JOIN q ON q.run_id = b.run_id
        )
        SELECT *
        FROM batches
        {where_clause}
        ORDER BY imported_at DESC, run_id DESC
        LIMIT ? OFFSET ?
    """
    count_query = f"""
        WITH q AS (
            SELECT
                run_id,
                SUM(CASE WHEN severity = 'blocking' THEN 1 ELSE 0 END) AS blocking_error_count,
                SUM(CASE WHEN severity = 'warning' THEN 1 ELSE 0 END) AS warning_count
            FROM import_error
            GROUP BY run_id
        ),
        batches AS (
            SELECT
                b.run_id,
                {status_sql} AS import_status
            FROM import_batch b
            LEFT JOIN q ON q.run_id = b.run_id
        )
        SELECT COUNT(*) AS count
        FROM batches
        {where_clause}
    """

    with get_connection(db_path) as connection:
        rows = connection.execute(query, (*params, safe_limit, safe_offset)).fetchall()
        total_count = connection.execute(count_query, params).fetchone()["count"]

    return {
        "summary": {
            "total_count": total_count,
            "returned_count": len(rows),
            "offset": safe_offset,
            "limit": safe_limit,
        },
        "items": _rows_to_dicts(rows),
    }


def get_import_batch_detail(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return batch metadata, archived files, imported counts, and quality summary."""

    with get_connection(db_path) as connection:
        batch = connection.execute(
            "SELECT * FROM import_batch WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if batch is None:
            raise ValueError(f"Unknown import batch: {run_id}")

        archived_files = connection.execute(
            """
            SELECT *
            FROM import_source_file
            WHERE run_id = ?
            ORDER BY source_role, file_name
            """,
            (run_id,),
        ).fetchall()
        counts = {
            "entities": _entity_count(connection, run_id),
            "aliases": connection.execute(
                "SELECT COUNT(*) AS count FROM entity_alias WHERE run_id = ?",
                (run_id,),
            ).fetchone()["count"],
            "order_evidence": connection.execute(
                "SELECT COUNT(*) AS count FROM order_evidence WHERE run_id = ?",
                (run_id,),
            ).fetchone()["count"],
            "order_role_edges": connection.execute(
                "SELECT COUNT(*) AS count FROM order_role_edge WHERE run_id = ?",
                (run_id,),
            ).fetchone()["count"],
            "relationship_claims": connection.execute(
                "SELECT COUNT(*) AS count FROM relationship_claim WHERE run_id = ?",
                (run_id,),
            ).fetchone()["count"],
        }
        quality_summary = _quality_summary(connection, run_id)

    return {
        "batch": dict(batch),
        "archived_files": _rows_to_dicts(archived_files),
        "counts": counts,
        "quality_summary": quality_summary,
    }


def list_import_errors(
    run_id: str,
    *,
    severity: str | None = None,
    error_type: str | None = None,
    limit: int = 200,
    offset: int = 0,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """List import errors for a run, optionally filtered by severity or type."""

    safe_limit = _safe_limit(limit, 1000)
    safe_offset = _safe_offset(offset)
    clauses = ["run_id = ?"]
    params: list[Any] = [run_id]
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if error_type:
        clauses.append("error_type = ?")
        params.append(error_type)
    where_clause = " AND ".join(clauses)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM import_error
            WHERE {where_clause}
            ORDER BY {_import_error_order_by()}
            LIMIT ? OFFSET ?
            """,
            (*params, safe_limit, safe_offset),
        ).fetchall()
        total_count = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM import_error
            WHERE {where_clause}
            """,
            params,
        ).fetchone()["count"]

    return {
        "summary": {
            "total_count": total_count,
            "returned_count": len(rows),
            "offset": safe_offset,
            "limit": safe_limit,
        },
        "items": _rows_to_dicts(rows),
    }


def get_import_quality_report(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return batch detail plus all import errors for a run."""

    detail = get_import_batch_detail(run_id, db_path=db_path)
    with get_connection(db_path) as connection:
        errors = _list_all_import_errors(connection, run_id)
    return {
        **detail,
        "errors": errors,
        "error_summary": {
            "total_count": len(errors),
            "returned_count": len(errors),
            "offset": 0,
            "limit": len(errors),
        },
    }


def export_import_errors(
    run_id: str,
    *,
    output_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Export all import errors for a run as UTF-8-SIG CSV."""

    get_import_batch_detail(run_id, db_path=db_path)
    target = (
        Path(output_path)
        if output_path
        else Path("data") / "exports" / f"{run_id}_import_errors.csv"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as connection:
        errors = _list_all_import_errors(connection, run_id)

    with target.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=ERROR_EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(errors)

    return {"path": str(target), "row_count": len(errors)}
