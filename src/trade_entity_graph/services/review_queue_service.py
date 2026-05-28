"""Global review queue queries for relationship claims."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection

REVIEW_QUEUE_STATUSES: tuple[str, ...] = (
    "history_conflict",
    "history_matched",
    "candidate",
    "pending_verify",
)
REVIEW_QUEUE_CONFIDENCE_LEVELS: tuple[str, ...] = ("high", "medium", "low")

_FINAL_HISTORY_ACTIONS = ("keep_history", "supersede")


def _normalized_values(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    return tuple(value.strip() for value in values if value and value.strip())


def _review_action_hint(status: str) -> str:
    if status == "history_conflict":
        return "优先复核历史冲突，可沿用历史或替代历史"
    if status == "history_matched":
        return "建议确认是否沿用历史结论"
    if status == "pending_verify":
        return "等待补充公开信息或业务判断"
    return "普通候选，可确认、否定或修改关系类型"


def _placeholders(values: tuple[str, ...]) -> str:
    return ", ".join("?" for _ in values)


def _queue_where_clause(
    *,
    statuses: tuple[str, ...],
    run_id: str | None,
    keyword: str | None,
    confidence_levels: tuple[str, ...] | None,
) -> tuple[str, list[Any]]:
    clauses = [
        f"rc.relation_status IN ({_placeholders(statuses)})",
        """
        NOT EXISTS (
            SELECT 1
            FROM curated_relationship cr
            WHERE cr.decision_source = rc.claim_id
        )
        """,
        f"""
        NOT EXISTS (
            SELECT 1
            FROM relationship_decision rd
            WHERE rd.claim_id = rc.claim_id
              AND rd.action_type IN ({_placeholders(_FINAL_HISTORY_ACTIONS)})
        )
        """,
    ]
    params: list[Any] = [*statuses, *_FINAL_HISTORY_ACTIONS]

    if run_id:
        clauses.append("rc.run_id = ?")
        params.append(run_id)

    if confidence_levels:
        clauses.append(f"rc.confidence_level IN ({_placeholders(confidence_levels)})")
        params.extend(confidence_levels)

    if keyword:
        pattern = f"%{keyword.upper()}%"
        clauses.append(
            """
            (
                UPPER(rc.claim_id) LIKE ?
                OR UPPER(e1.canonical_name) LIKE ?
                OR UPPER(e2.canonical_name) LIKE ?
                OR UPPER(rc.recommendation_reason) LIKE ?
            )
            """
        )
        params.extend([pattern, pattern, pattern, pattern])

    return "\n          AND ".join(clauses), params


def list_review_queue(
    *,
    db_path: str | Path | None = None,
    statuses: tuple[str, ...] | list[str] | None = None,
    run_id: str | None = None,
    keyword: str | None = None,
    confidence_levels: tuple[str, ...] | list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return reviewable relationship claims across all entities."""

    normalized_statuses = _normalized_values(statuses) or REVIEW_QUEUE_STATUSES
    normalized_confidence = _normalized_values(confidence_levels)
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))

    where_clause, params = _queue_where_clause(
        statuses=normalized_statuses,
        run_id=run_id.strip() if run_id else None,
        keyword=keyword.strip() if keyword else None,
        confidence_levels=normalized_confidence,
    )
    priority_case = """
        CASE rc.relation_status
            WHEN 'history_conflict' THEN 0
            WHEN 'history_matched' THEN 1
            WHEN 'candidate' THEN 2
            WHEN 'pending_verify' THEN 3
            ELSE 9
        END
    """

    with get_connection(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                rc.claim_id,
                rc.from_entity_id,
                e1.canonical_name AS from_name,
                rc.to_entity_id,
                e2.canonical_name AS to_name,
                rc.candidate_relation_type,
                rc.relation_status,
                rc.confidence_level,
                rc.confidence_score,
                rc.order_count,
                rc.total_teu,
                rc.role_pair_summary,
                rc.destination_summary,
                rc.product_summary,
                rc.recommendation_reason,
                rc.run_id,
                ib.source_file,
                ib.imported_at,
                rc.created_at,
                rc.updated_at,
                COALESCE(MAX(rd.operated_at), rc.updated_at, rc.created_at) AS last_activity_at,
                {priority_case} AS queue_priority
            FROM relationship_claim rc
            JOIN entity e1 ON e1.entity_id = rc.from_entity_id
            JOIN entity e2 ON e2.entity_id = rc.to_entity_id
            LEFT JOIN import_batch ib ON ib.run_id = rc.run_id
            LEFT JOIN relationship_decision rd ON rd.claim_id = rc.claim_id
            WHERE {where_clause}
            GROUP BY rc.claim_id
            ORDER BY
                queue_priority ASC,
                rc.confidence_score DESC,
                rc.order_count DESC,
                rc.total_teu DESC,
                last_activity_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, safe_limit, safe_offset),
        ).fetchall()

        total_count = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM relationship_claim rc
            JOIN entity e1 ON e1.entity_id = rc.from_entity_id
            JOIN entity e2 ON e2.entity_id = rc.to_entity_id
            LEFT JOIN import_batch ib ON ib.run_id = rc.run_id
            WHERE {where_clause}
            """,
            params,
        ).fetchone()["count"]

        status_rows = connection.execute(
            f"""
            SELECT rc.relation_status, COUNT(*) AS count
            FROM relationship_claim rc
            JOIN entity e1 ON e1.entity_id = rc.from_entity_id
            JOIN entity e2 ON e2.entity_id = rc.to_entity_id
            LEFT JOIN import_batch ib ON ib.run_id = rc.run_id
            WHERE {where_clause}
            GROUP BY rc.relation_status
            """,
            params,
        ).fetchall()

    items = [dict(row) for row in rows]
    for item in items:
        item["review_action_hint"] = _review_action_hint(str(item["relation_status"]))

    status_counts = {status: 0 for status in REVIEW_QUEUE_STATUSES}
    status_counts.update({row["relation_status"]: row["count"] for row in status_rows})
    return {
        "items": items,
        "summary": {
            "total_count": total_count,
            "returned_count": len(items),
            "offset": safe_offset,
            "limit": safe_limit,
            "status_counts": status_counts,
        },
    }
