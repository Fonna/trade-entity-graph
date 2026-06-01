"""Import batch quality reporting queries."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import sqlite3
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


def import_errors_export_filename(run_id: str) -> str:
    """Return a filesystem-safe CSV filename for an import error export."""

    safe_run_id = re.sub(r"[^A-Za-z0-9_-]+", "_", run_id).strip("_")
    if not safe_run_id:
        safe_run_id = "import"
    return f"{safe_run_id}_import_errors.csv"


def _safe_limit(value: int, maximum: int) -> int:
    return max(1, min(int(value), maximum))


def _safe_offset(value: int) -> int:
    return max(0, int(value))


def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _ensure_import_batch_exists(connection: Any, run_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM import_batch WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown import batch: {run_id}")


def find_duplicate_import(
    sources: list[tuple[str, Path]],
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return the latest import batch with the same source-role file hashes."""

    if not sources:
        return None

    try:
        source_hash_by_role = {
            source_role: _source_sha256(Path(source_path))
            for source_role, source_path in sources
        }
    except OSError:
        return None
    source_roles = set(source_hash_by_role)

    try:
        with get_connection(db_path) as connection:
            batch_rows = connection.execute(
                """
                SELECT b.*
                FROM import_batch b
                JOIN import_source_file f ON f.run_id = b.run_id
                GROUP BY b.run_id
                ORDER BY b.imported_at DESC, b.run_id DESC
                """
            ).fetchall()
            for batch in batch_rows:
                file_rows = connection.execute(
                    """
                    SELECT *
                    FROM import_source_file
                    WHERE run_id = ?
                    ORDER BY source_role, file_name
                    """,
                    (batch["run_id"],),
                ).fetchall()
                files_by_role = {row["source_role"]: dict(row) for row in file_rows}
                if set(files_by_role) != source_roles:
                    continue
                if all(
                    files_by_role[source_role]["sha256"] == source_hash
                    for source_role, source_hash in source_hash_by_role.items()
                ):
                    return {
                        "run_id": batch["run_id"],
                        "source_file": batch["source_file"],
                        "source_path": batch["source_path"],
                        "imported_by": batch["imported_by"],
                        "imported_at": batch["imported_at"],
                        "source_files": list(files_by_role.values()),
                    }
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc).lower():
            raise

    return None


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
    row = connection.execute(
        """
        SELECT COUNT(DISTINCT entity_id) AS count
        FROM (
            SELECT entity_id FROM import_entity WHERE run_id = ?
            UNION
            SELECT entity_id FROM entity WHERE run_id = ?
            UNION
            SELECT entity_id FROM entity_alias WHERE run_id = ?
        )
        """,
        (run_id, run_id, run_id),
    ).fetchone()
    return row["count"]


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
            "curated_relationships": connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM curated_relationship
                WHERE substr(decision_source, 1, ?) = ?
                """,
                (len(f"{run_id}:"), f"{run_id}:"),
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
        _ensure_import_batch_exists(connection, run_id)
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


def _render_import_errors_csv_payload(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> tuple[bytes, int]:
    with get_connection(db_path) as connection:
        _ensure_import_batch_exists(connection, run_id)
        errors = _list_all_import_errors(connection, run_id)

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer, fieldnames=ERROR_EXPORT_COLUMNS, extrasaction="ignore"
    )
    writer.writeheader()
    writer.writerows(errors)
    return csv_buffer.getvalue().encode("utf-8-sig"), len(errors)


def render_import_errors_csv(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> bytes:
    """Render all import errors for a run as UTF-8-SIG CSV bytes."""

    content, _row_count = _render_import_errors_csv_payload(run_id, db_path=db_path)
    return content


def export_import_errors(
    run_id: str,
    *,
    output_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Export all import errors for a run as UTF-8-SIG CSV."""

    content, row_count = _render_import_errors_csv_payload(run_id, db_path=db_path)
    target = (
        Path(output_path)
        if output_path
        else Path("data") / "exports" / import_errors_export_filename(run_id)
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    return {"path": str(target), "row_count": row_count}
