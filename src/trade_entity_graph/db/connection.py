"""SQLite connection and initialization helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from trade_entity_graph.config import get_settings


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Create a SQLite connection with row access by column name."""

    path = Path(db_path) if db_path else get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(
    db_path: str | Path | None = None,
    schema_path: str | Path | None = None,
) -> Path:
    """Initialize a SQLite database from the project schema."""

    schema = Path(schema_path) if schema_path else Path(__file__).with_name("schema.sql")
    target = Path(db_path) if db_path else get_settings().database_path
    with get_connection(target) as connection:
        connection.executescript(schema.read_text(encoding="utf-8"))
    return target
