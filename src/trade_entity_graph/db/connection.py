"""SQLite connection and initialization helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from trade_entity_graph.config import get_settings

SCHEMA_COLUMN_MIGRATIONS: dict[str, dict[str, str]] = {
    "import_batch": {
        "warning_rows": "INTEGER DEFAULT 0",
    },
    "entity": {
        "run_id": "TEXT REFERENCES import_batch(run_id)",
    },
    "order_evidence": {
        "customer_name": "TEXT",
        "shipper_name": "TEXT",
        "consignee_name": "TEXT",
        "notify_name": "TEXT",
    },
}


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Create a SQLite connection with row access by column name."""

    path = Path(db_path) if db_path else get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _apply_column_migrations(connection: sqlite3.Connection) -> None:
    """Add columns that older local SQLite databases may be missing."""

    for table_name, required_columns in SCHEMA_COLUMN_MIGRATIONS.items():
        existing = _existing_columns(connection, table_name)
        if not existing:
            continue
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                connection.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )


def initialize_database(
    db_path: str | Path | None = None,
    schema_path: str | Path | None = None,
) -> Path:
    """Initialize a SQLite database from the project schema."""

    schema = Path(schema_path) if schema_path else Path(__file__).with_name("schema.sql")
    target = Path(db_path) if db_path else get_settings().database_path
    with get_connection(target) as connection:
        connection.executescript(schema.read_text(encoding="utf-8"))
        _apply_column_migrations(connection)
    return target
