"""One-hop graph query service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection

PENDING_CLAIM_STATUSES = ("candidate", "pending_verify", "history_conflict")


def _entity_node(row: Any, *, center_entity_id: str) -> dict[str, Any]:
    return {
        "id": row["entity_id"],
        "label": row["canonical_name"],
        "entity_type": row["entity_type"],
        "tags": row["tags"],
        "is_center": row["entity_id"] == center_entity_id,
    }


def _order_edge(row: Any) -> dict[str, Any]:
    return {
        "id": row["edge_id"],
        "source": row["from_entity_id"],
        "target": row["to_entity_id"],
        "source_label": row["from_name"],
        "target_label": row["to_name"],
        "edge_type": "order_role_edge",
        "record_type": "order_role_edge",
        "relation_type": row["role_pair_type"],
        "status": "evidence",
        "confidence_level": None,
        "confidence_score": None,
        "order_count": 1,
        "total_teu": row["teu"],
        "teu": row["teu"],
        "label": row["role_pair_type"],
    }


def _curated_edge(row: Any) -> dict[str, Any]:
    return {
        "id": row["relationship_id"],
        "source": row["from_entity_id"],
        "target": row["to_entity_id"],
        "source_label": row["from_name"],
        "target_label": row["to_name"],
        "edge_type": "curated_relationship",
        "record_type": "curated_relationship",
        "relation_type": row["relation_type"],
        "status": row["relation_status"],
        "confidence_level": row["confidence_level"],
        "confidence_score": row["confidence_score"],
        "order_count": None,
        "total_teu": None,
        "teu": None,
        "label": f"{row['relation_type']} / {row['relation_status']}",
    }


def _claim_edge(row: Any) -> dict[str, Any]:
    reason = row["recommendation_reason"] or ""
    order_count = row["order_count"] or 0
    total_teu = row["total_teu"] or 0
    label_parts = [row["candidate_relation_type"], f"{order_count} orders"]
    if total_teu:
        label_parts.append(f"{total_teu:g} TEU")
    return {
        "id": row["claim_id"],
        "source": row["from_entity_id"],
        "target": row["to_entity_id"],
        "source_label": row["from_name"],
        "target_label": row["to_name"],
        "edge_type": "relationship_claim",
        "record_type": "relationship_claim",
        "relation_type": row["candidate_relation_type"],
        "status": row["relation_status"],
        "confidence_level": row["confidence_level"],
        "confidence_score": row["confidence_score"],
        "order_count": order_count,
        "total_teu": total_teu,
        "teu": total_teu,
        "label": " / ".join(label_parts),
        "recommendation_reason": reason,
    }


def get_ego_graph(
    center_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
) -> dict[str, Any]:
    """Return one-hop nodes and edges around a center entity."""

    with get_connection(db_path) as connection:
        order_edges = connection.execute(
            """
            SELECT ore.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name
            FROM order_role_edge ore
            JOIN entity e1 ON e1.entity_id = ore.from_entity_id
            JOIN entity e2 ON e2.entity_id = ore.to_entity_id
            WHERE ore.from_entity_id = ? OR ore.to_entity_id = ?
            ORDER BY ore.order_id, ore.role_pair_type
            """,
            (center_entity_id, center_entity_id),
        ).fetchall()
        rejected_filter = "" if include_rejected else "AND cr.relation_status != 'rejected'"
        curated_sql = f"""
            SELECT cr.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name
            FROM curated_relationship cr
            JOIN entity e1 ON e1.entity_id = cr.from_entity_id
            JOIN entity e2 ON e2.entity_id = cr.to_entity_id
            WHERE (cr.from_entity_id = ? OR cr.to_entity_id = ?)
              AND cr.valid_to IS NULL
              AND cr.relation_status != 'deprecated'
              {rejected_filter}
            ORDER BY cr.created_at
        """
        curated_params = (center_entity_id, center_entity_id)
        curated_edges = connection.execute(curated_sql, curated_params).fetchall()
        pending_status_placeholders = ", ".join("?" for _ in PENDING_CLAIM_STATUSES)
        claim_edges = connection.execute(
            f"""
            SELECT rc.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name
            FROM relationship_claim rc
            JOIN entity e1 ON e1.entity_id = rc.from_entity_id
            JOIN entity e2 ON e2.entity_id = rc.to_entity_id
            WHERE (rc.from_entity_id = ? OR rc.to_entity_id = ?)
              AND rc.relation_status IN ({pending_status_placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM curated_relationship cr
                  WHERE cr.decision_source = rc.claim_id
            )
            ORDER BY rc.confidence_score DESC, rc.order_count DESC, rc.created_at
            """,
            (center_entity_id, center_entity_id, *PENDING_CLAIM_STATUSES),
        ).fetchall()

        edges = [_order_edge(row) for row in order_edges]
        edges.extend(_curated_edge(row) for row in curated_edges)
        edges.extend(_claim_edge(row) for row in claim_edges)

        visible_entity_ids = {center_entity_id}
        for edge in edges:
            visible_entity_ids.add(edge["source"])
            visible_entity_ids.add(edge["target"])
        entity_placeholders = ", ".join("?" for _ in visible_entity_ids)
        entity_rows = connection.execute(
            f"""
            SELECT DISTINCT e.*
            FROM entity e
            WHERE e.entity_id IN ({entity_placeholders})
            ORDER BY e.canonical_name
            """,
            tuple(visible_entity_ids),
        ).fetchall()

        return {
            "center_entity_id": center_entity_id,
            "nodes": [_entity_node(row, center_entity_id=center_entity_id) for row in entity_rows],
            "edges": edges,
            "summary": {
                "node_count": len(entity_rows),
                "edge_count": len(edges),
                "candidate_edge_count": len(claim_edges),
                "curated_edge_count": len(curated_edges),
                "order_edge_count": len(order_edges),
            },
        }
