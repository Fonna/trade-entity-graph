"""Persistence helpers for structured import errors."""

from __future__ import annotations

import sqlite3

from trade_entity_graph.importers.models import ImportErrorRecord
from trade_entity_graph.utils.ids import new_id


def write_import_errors(connection: sqlite3.Connection, records: list[ImportErrorRecord]) -> int:
    """Persist structured import errors and return inserted row count."""

    for record in records:
        payload = record.as_dict()
        connection.execute(
            """
            INSERT INTO import_error (
                error_id, run_id, source_file_id, file_role, source_path, sheet_name,
                row_number, column_name, normalized_field, raw_value, error_type,
                severity, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("IER"),
                payload["run_id"],
                payload["source_file_id"],
                payload["file_role"],
                payload["source_path"],
                payload["sheet_name"],
                payload["row_number"],
                payload["column_name"],
                payload["normalized_field"],
                payload["raw_value"],
                payload["error_type"],
                payload["severity"],
                payload["message"],
            ),
        )
    connection.commit()
    return len(records)
