import sqlite3

from trade_entity_graph.db.connection import get_connection, initialize_database

EXPECTED_TABLES = {
    "audit_log",
    "curated_relationship",
    "entity",
    "entity_alias",
    "import_batch",
    "import_source_file",
    "order_evidence",
    "order_role_edge",
    "relationship_claim",
    "relationship_decision",
}

EXPECTED_INDEXES = {
    "idx_curated_relationship_pair",
    "idx_curated_relationship_status",
    "idx_entity_alias_name",
    "idx_entity_canonical_name",
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


def test_get_connection_enables_foreign_keys(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        pragma = connection.execute("PRAGMA foreign_keys").fetchone()

    assert pragma[0] == 1
