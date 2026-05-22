"""Entity search and detail operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection


def search_entities(
    query: str, *, db_path: str | Path | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Search entities by canonical name or alias."""

    pattern = f"%{query.strip().upper()}%"
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT e.entity_id, e.canonical_name, e.country,
                   e.entity_type, e.tags, e.status
            FROM entity e
            LEFT JOIN entity_alias a ON a.entity_id = e.entity_id
            WHERE UPPER(e.canonical_name) LIKE ? OR UPPER(a.alias_name) LIKE ?
            ORDER BY e.canonical_name
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def get_entity_detail(
    entity_id: str, *, db_path: str | Path | None = None
) -> dict[str, Any] | None:
    """Return entity details, aliases, and simple statistics."""

    with get_connection(db_path) as connection:
        entity = connection.execute(
            "SELECT * FROM entity WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        if not entity:
            return None

        aliases = connection.execute(
            "SELECT alias_name, alias_type, source FROM entity_alias WHERE entity_id = ?",
            (entity_id,),
        ).fetchall()
        order_edge_count = connection.execute(
            """
            SELECT COUNT(*) FROM order_role_edge
            WHERE from_entity_id = ? OR to_entity_id = ?
            """,
            (entity_id, entity_id),
        ).fetchone()[0]
        curated_count = connection.execute(
            """
            SELECT COUNT(*) FROM curated_relationship
            WHERE from_entity_id = ? OR to_entity_id = ?
            """,
            (entity_id, entity_id),
        ).fetchone()[0]

        result = dict(entity)
        result["aliases"] = [dict(row) for row in aliases]
        result["alias_count"] = len(aliases)
        result["order_edge_count"] = order_edge_count
        result["curated_relationship_count"] = curated_count
        return result
