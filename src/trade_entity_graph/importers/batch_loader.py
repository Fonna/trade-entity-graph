"""Import batch persistence."""

from __future__ import annotations

import sqlite3

from trade_entity_graph.utils.ids import new_id


def create_import_batch(
    connection: sqlite3.Connection,
    *,
    source_file: str,
    source_path: str | None,
    imported_by: str,
    field_mapping_version: str,
    rule_version: str,
) -> str:
    """Insert one import batch and return its run id."""

    run_id = new_id("RUN")
    connection.execute(
        """
        INSERT INTO import_batch (
            run_id, source_file, source_path, imported_by, field_mapping_version, rule_version
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, source_file, source_path, imported_by, field_mapping_version, rule_version),
    )
    connection.commit()
    return run_id


def finish_import_batch(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    success_rows: int,
    error_rows: int,
    warning_rows: int = 0,
    error_summary: str | None = None,
) -> None:
    """Update import row counts after loaders finish."""

    connection.execute(
        """
        UPDATE import_batch
        SET success_rows = ?, error_rows = ?, warning_rows = ?, error_summary = ?
        WHERE run_id = ?
        """,
        (success_rows, error_rows, warning_rows, error_summary, run_id),
    )
    connection.commit()
