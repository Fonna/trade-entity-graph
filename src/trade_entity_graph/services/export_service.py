"""CSV and Excel export operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection


def export_relationship_rows(
    center_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
) -> list[dict[str, Any]]:
    """Return relationship rows for export around a center entity."""

    status_filter = "" if include_rejected else "AND cr.relation_status != 'rejected'"
    with get_connection(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT cr.relationship_id, cr.from_entity_id, e1.canonical_name AS from_name,
                   cr.to_entity_id, e2.canonical_name AS to_name, cr.relation_type,
                   cr.relation_status, cr.confidence_level, cr.confidence_score,
                   cr.source_type, cr.decision_note, cr.verified_by, cr.verified_at
            FROM curated_relationship cr
            JOIN entity e1 ON e1.entity_id = cr.from_entity_id
            JOIN entity e2 ON e2.entity_id = cr.to_entity_id
            WHERE (cr.from_entity_id = ? OR cr.to_entity_id = ?)
              AND cr.valid_to IS NULL
              AND cr.relation_status != 'deprecated'
            {status_filter}
            ORDER BY e1.canonical_name, e2.canonical_name
            """,
            (center_entity_id, center_entity_id),
        ).fetchall()
        return [dict(row) for row in rows]
