"""One-hop graph query service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection


def _entity_node(row: Any) -> dict[str, Any]:
    return {
        "id": row["entity_id"],
        "label": row["canonical_name"],
        "entity_type": row["entity_type"],
        "tags": row["tags"],
    }


def get_ego_graph(
    center_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
) -> dict[str, Any]:
    """Return one-hop nodes and edges around a center entity."""

    with get_connection(db_path) as connection:
        entity_rows = connection.execute(
            """
            SELECT DISTINCT e.*
            FROM entity e
            WHERE e.entity_id = ?
               OR e.entity_id IN (
                    SELECT to_entity_id FROM order_role_edge WHERE from_entity_id = ?
                    UNION
                    SELECT from_entity_id FROM order_role_edge WHERE to_entity_id = ?
                    UNION
                    SELECT to_entity_id FROM curated_relationship WHERE from_entity_id = ?
                    UNION
                    SELECT from_entity_id FROM curated_relationship WHERE to_entity_id = ?
               )
            ORDER BY e.canonical_name
            """,
            (
                center_entity_id,
                center_entity_id,
                center_entity_id,
                center_entity_id,
                center_entity_id,
            ),
        ).fetchall()
        order_edges = connection.execute(
            """
            SELECT * FROM order_role_edge
            WHERE from_entity_id = ? OR to_entity_id = ?
            ORDER BY order_id, role_pair_type
            """,
            (center_entity_id, center_entity_id),
        ).fetchall()
        if include_rejected:
            curated_edges = connection.execute(
                """
                SELECT * FROM curated_relationship
                WHERE from_entity_id = ? OR to_entity_id = ?
                ORDER BY created_at
                """,
                (center_entity_id, center_entity_id),
            ).fetchall()
        else:
            curated_edges = connection.execute(
                """
                SELECT * FROM curated_relationship
                WHERE (from_entity_id = ? OR to_entity_id = ?)
                  AND relation_status != 'rejected'
                ORDER BY created_at
                """,
                (center_entity_id, center_entity_id),
            ).fetchall()

        edges = [
            {
                "id": row["edge_id"],
                "source": row["from_entity_id"],
                "target": row["to_entity_id"],
                "edge_type": "order_role_edge",
                "relation_type": row["role_pair_type"],
                "status": "evidence",
                "order_count": 1,
                "teu": row["teu"],
            }
            for row in order_edges
        ]
        edges.extend(
            {
                "id": row["relationship_id"],
                "source": row["from_entity_id"],
                "target": row["to_entity_id"],
                "edge_type": "curated_relationship",
                "relation_type": row["relation_type"],
                "status": row["relation_status"],
                "order_count": None,
                "teu": None,
            }
            for row in curated_edges
        )

        return {
            "center_entity_id": center_entity_id,
            "nodes": [_entity_node(row) for row in entity_rows],
            "edges": edges,
            "summary": {"node_count": len(entity_rows), "edge_count": len(edges)},
        }
