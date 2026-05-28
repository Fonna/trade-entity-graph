import sqlite3

import pytest

from trade_entity_graph.db.connection import get_connection, initialize_database

EXPECTED_TABLES = {
    "audit_log",
    "curated_relationship",
    "entity",
    "entity_alias",
    "import_batch",
    "import_error",
    "import_source_file",
    "order_evidence",
    "order_role_edge",
    "relationship_claim",
    "relationship_decision",
}

EXPECTED_INDEXES = {
    "idx_curated_relationship_pair",
    "idx_curated_relationship_decision_source_unique",
    "idx_curated_relationship_status",
    "idx_entity_alias_name",
    "idx_entity_canonical_name",
    "idx_import_error_run",
    "idx_import_error_severity",
    "idx_import_error_type",
    "idx_import_source_file_run",
    "idx_order_role_edge_from",
    "idx_order_role_edge_role_pair",
    "idx_order_role_edge_to",
    "idx_relationship_claim_pair",
}


def _sqlite_objects(connection: sqlite3.Connection, object_type: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'",
        (object_type,),
    ).fetchall()
    return {row["name"] for row in rows}


def test_initialize_database_creates_core_tables(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        assert EXPECTED_TABLES.issubset(_sqlite_objects(connection, "table"))


def test_initialize_database_creates_common_indexes(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        assert EXPECTED_INDEXES.issubset(_sqlite_objects(connection, "index"))


def test_import_error_schema_has_traceability_columns(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(import_error)")
        }

    assert {
        "error_id", "run_id", "source_file_id", "file_role", "source_path",
        "sheet_name", "row_number", "column_name", "normalized_field", "raw_value",
        "error_type", "severity", "message", "created_at",
    }.issubset(columns)


def test_entity_schema_has_run_id_for_import_traceability(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(entity)")}

    assert "run_id" in columns


def test_initialize_database_adds_missing_entity_run_id_column(tmp_path) -> None:
    db_path = tmp_path / "legacy_trade_entity_graph.db"
    with get_connection(db_path) as connection:
        connection.execute(
            "CREATE TABLE import_batch (run_id TEXT PRIMARY KEY, source_file TEXT NOT NULL)"
        )
        connection.execute(
            """
            CREATE TABLE entity (
                entity_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                country TEXT,
                entity_type TEXT,
                tags TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    initialize_database(db_path)

    with get_connection(db_path) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(entity)")}

    assert "run_id" in columns


def test_get_connection_enables_foreign_keys(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        pragma = connection.execute("PRAGMA foreign_keys").fetchone()

    assert pragma[0] == 1


def test_initialize_database_adds_missing_order_evidence_role_columns(tmp_path) -> None:
    db_path = tmp_path / "legacy_trade_entity_graph.db"
    with get_connection(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE order_evidence (
                evidence_id TEXT PRIMARY KEY,
                order_id TEXT,
                teu REAL,
                product_name TEXT,
                function_category TEXT,
                destination_country TEXT,
                destination_port TEXT,
                order_date TEXT,
                source_file TEXT,
                source_sheet TEXT,
                source_row INTEGER,
                run_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    initialize_database(db_path)

    with get_connection(db_path) as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(order_evidence)")
        }

    assert {"customer_name", "shipper_name", "consignee_name", "notify_name"}.issubset(columns)


def test_curated_relationship_decision_source_is_unique_when_present(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_A', 'ACME', 'company'), ('ENT_B', 'BETA', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, decision_source
            )
            VALUES
                ('REL_NULL_1', 'ENT_A', 'ENT_B', 'trading_partner', 'verified', NULL),
                ('REL_NULL_2', 'ENT_B', 'ENT_A', 'trading_partner', 'verified', NULL),
                ('REL_CLAIM_1', 'ENT_A', 'ENT_B', 'trading_partner', 'verified', 'CLM_1')
            """
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO curated_relationship (
                    relationship_id, from_entity_id, to_entity_id, relation_type,
                    relation_status, decision_source
                )
                VALUES ('REL_CLAIM_2', 'ENT_B', 'ENT_A', 'trading_partner', 'verified', 'CLM_1')
                """
            )
