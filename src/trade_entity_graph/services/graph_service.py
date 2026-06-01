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


def _all_visible_edges(connection: Any, *, include_rejected: bool) -> list[dict[str, Any]]:
    order_edges = connection.execute(
        """
        SELECT ore.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name
        FROM order_role_edge ore
        JOIN entity e1 ON e1.entity_id = ore.from_entity_id
        JOIN entity e2 ON e2.entity_id = ore.to_entity_id
        ORDER BY ore.order_id, ore.role_pair_type
        """
    ).fetchall()
    rejected_filter = "" if include_rejected else "AND cr.relation_status != 'rejected'"
    curated_sql = f"""
        SELECT cr.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name
        FROM curated_relationship cr
        JOIN entity e1 ON e1.entity_id = cr.from_entity_id
        JOIN entity e2 ON e2.entity_id = cr.to_entity_id
        WHERE cr.valid_to IS NULL
          AND cr.relation_status != 'deprecated'
          {rejected_filter}
        ORDER BY cr.created_at
    """
    curated_edges = connection.execute(curated_sql).fetchall()
    pending_status_placeholders = ", ".join("?" for _ in PENDING_CLAIM_STATUSES)
    claim_edges = connection.execute(
        f"""
        SELECT rc.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name
        FROM relationship_claim rc
        JOIN entity e1 ON e1.entity_id = rc.from_entity_id
        JOIN entity e2 ON e2.entity_id = rc.to_entity_id
        WHERE rc.relation_status IN ({pending_status_placeholders})
          AND NOT EXISTS (
              SELECT 1
              FROM curated_relationship cr
              WHERE cr.decision_source = rc.claim_id
        )
        ORDER BY rc.confidence_score DESC, rc.order_count DESC, rc.created_at
        """,
        PENDING_CLAIM_STATUSES,
    ).fetchall()

    edges = [_order_edge(row) for row in order_edges]
    edges.extend(_curated_edge(row) for row in curated_edges)
    edges.extend(_claim_edge(row) for row in claim_edges)
    return edges


def _edge_counts(edges: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidate_edge_count": sum(edge["record_type"] == "relationship_claim" for edge in edges),
        "curated_edge_count": sum(edge["record_type"] == "curated_relationship" for edge in edges),
        "order_edge_count": sum(edge["record_type"] == "order_role_edge" for edge in edges),
    }


def _entity_exists(connection: Any, entity_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM entity WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    return row is not None


def _fetch_entity_nodes(
    connection: Any,
    entity_ids: list[str],
    *,
    center_entity_id: str,
) -> list[dict[str, Any]]:
    if not entity_ids:
        return []
    placeholders = ", ".join("?" for _ in entity_ids)
    rows = connection.execute(
        f"""
        SELECT DISTINCT e.*
        FROM entity e
        WHERE e.entity_id IN ({placeholders})
        """,
        tuple(entity_ids),
    ).fetchall()
    nodes_by_id = {
        row["entity_id"]: _entity_node(row, center_entity_id=center_entity_id) for row in rows
    }
    return [nodes_by_id[entity_id] for entity_id in entity_ids if entity_id in nodes_by_id]


def _edge_priority(edge: dict[str, Any]) -> float:
    if edge["record_type"] == "curated_relationship":
        if edge["status"] == "verified":
            return 1.0
        return 0.9
    if edge["record_type"] == "relationship_claim":
        return 0.7
    return 0.5


def _path_score(edges: list[dict[str, Any]]) -> float:
    if not edges:
        return 1.0
    edge_score = sum(_edge_priority(edge) for edge in edges) / len(edges)
    return round(edge_score / len(edges), 4)


def _rank_edge(edge: dict[str, Any]) -> tuple[float, float, float, str]:
    return (
        -_edge_priority(edge),
        -(edge.get("order_count") or 0),
        -(edge.get("total_teu") or 0),
        str(edge["id"]),
    )


def get_ego_graph(
    center_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
    depth: int = 1,
    max_nodes: int = 50,
) -> dict[str, Any]:
    """Return bounded one-hop or two-hop nodes and edges around a center entity."""

    if depth not in (1, 2):
        raise ValueError("depth must be 1 or 2")
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")

    with get_connection(db_path) as connection:
        all_edges = _all_visible_edges(connection, include_rejected=include_rejected)
        visible_entity_ids = {center_entity_id}
        frontier = {center_entity_id}
        selected_edges = []
        truncated = False
        for _level in range(depth):
            next_frontier = set()
            for edge in all_edges:
                source = edge["source"]
                target = edge["target"]
                if source not in frontier and target not in frontier:
                    continue
                other_id = target if source in frontier else source
                if other_id not in visible_entity_ids and len(visible_entity_ids) >= max_nodes:
                    truncated = True
                    continue
                visible_entity_ids.add(other_id)
                next_frontier.add(other_id)
                if edge not in selected_edges:
                    selected_edges.append(edge)
            frontier = next_frontier
            if not frontier:
                break

        edges = [
            edge
            for edge in selected_edges
            if edge["source"] in visible_entity_ids and edge["target"] in visible_entity_ids
        ]
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
                **_edge_counts(edges),
                "depth": depth,
                "max_nodes": max_nodes,
                "truncated": truncated,
            },
        }


def find_entity_paths(
    from_entity_id: str,
    to_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
    max_depth: int = 3,
    max_paths: int = 5,
) -> dict[str, Any]:
    """Return explainable paths between two entities over the visible graph."""

    if max_depth < 1:
        raise ValueError("max_depth must be positive")
    if max_paths < 1:
        raise ValueError("max_paths must be positive")

    with get_connection(db_path) as connection:
        if not _entity_exists(connection, from_entity_id):
            raise ValueError(f"Unknown entity: {from_entity_id}")
        if not _entity_exists(connection, to_entity_id):
            raise ValueError(f"Unknown entity: {to_entity_id}")

        all_edges = _all_visible_edges(connection, include_rejected=include_rejected)
        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for edge in all_edges:
            adjacency.setdefault(edge["source"], []).append((edge["target"], edge))
            adjacency.setdefault(edge["target"], []).append((edge["source"], edge))
        for neighbors in adjacency.values():
            neighbors.sort(key=lambda item: (_rank_edge(item[1]), item[0]))

        queue: list[tuple[list[str], list[dict[str, Any]]]] = [([from_entity_id], [])]
        found_paths: list[tuple[list[str], list[dict[str, Any]]]] = []
        truncated = False
        while queue and len(found_paths) < max_paths:
            node_ids, path_edges = queue.pop(0)
            current_id = node_ids[-1]
            if len(path_edges) >= max_depth:
                continue
            for neighbor_id, edge in adjacency.get(current_id, []):
                if neighbor_id in node_ids:
                    continue
                next_node_ids = [*node_ids, neighbor_id]
                path_edge = dict(edge)
                path_edge["path_from"] = current_id
                path_edge["path_to"] = neighbor_id
                next_edges = [*path_edges, path_edge]
                if neighbor_id == to_entity_id:
                    found_paths.append((next_node_ids, next_edges))
                    if len(found_paths) >= max_paths:
                        truncated = True
                        break
                else:
                    queue.append((next_node_ids, next_edges))

        paths = []
        for node_ids, edges in sorted(
            found_paths,
            key=lambda item: (len(item[1]), -_path_score(item[1]), item[0]),
        ):
            paths.append(
                {
                    "node_ids": node_ids,
                    "nodes": _fetch_entity_nodes(
                        connection,
                        node_ids,
                        center_entity_id=from_entity_id,
                    ),
                    "edges": edges,
                    "score": _path_score(edges),
                    "explanation": (
                        f"{from_entity_id} connects to {to_entity_id} through "
                        f"{max(len(node_ids) - 2, 0)} intermediate entities."
                    ),
                }
            )

        return {
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "max_depth": max_depth,
            "max_paths": max_paths,
            "path_count": len(paths),
            "paths": paths,
            "summary": {
                "path_count": len(paths),
                "max_depth": max_depth,
                "max_paths": max_paths,
                "truncated": truncated,
            },
        }
