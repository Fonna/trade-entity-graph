"""History relationship reuse classification for relationship candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection

CURRENT_EFFECTIVE_STATUSES = ("verified", "manual_only", "rejected")
POSITIVE_EFFECTIVE_STATUSES = ("verified", "manual_only")
REVIEWABLE_CLAIM_STATUSES = (
    "candidate",
    "history_matched",
    "history_conflict",
    "pending_verify",
)
CHALLENGE_REJECTED_CONFIDENCE_LEVELS = {"medium", "high"}
SYMMETRIC_RELATION_TYPES = {"same_entity", "same_group", "trading_partner"}
COMPATIBLE_RELATION_TYPES = {
    "trading_partner_candidate": {
        "trading_partner",
        "same_group",
        "subsidiary",
        "factory_node",
        "sales_center",
    },
    "factory_candidate": {"factory_node", "subsidiary", "same_group"},
    "sales_center_candidate": {"sales_center", "subsidiary", "same_group"},
    "same_group_candidate": {"same_group", "subsidiary", "same_entity"},
}


def _row_to_dict(row: Any | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _append_history_reason(current_reason: str | None, history_reason: str) -> str:
    current = (current_reason or "").strip()
    if current.startswith("history reuse:"):
        base = ""
    else:
        base = current.split(" | history reuse:", 1)[0].strip()
    suffix = f"history reuse: {history_reason}"
    return f"{base} | {suffix}" if base else suffix


def _fetch_claim(connection, claim_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    return _row_to_dict(row)


def _fetch_effective_history(connection, claim: dict[str, Any]) -> list[dict[str, Any]]:
    status_placeholders = ", ".join("?" for _ in CURRENT_EFFECTIVE_STATUSES)
    symmetric_placeholders = ", ".join("?" for _ in SYMMETRIC_RELATION_TYPES)
    rows = connection.execute(
        f"""
        SELECT cr.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name,
               CASE
                   WHEN cr.from_entity_id = ? AND cr.to_entity_id = ? THEN 0
                   ELSE 1
               END AS match_rank
        FROM curated_relationship cr
        JOIN entity e1 ON e1.entity_id = cr.from_entity_id
        JOIN entity e2 ON e2.entity_id = cr.to_entity_id
        WHERE cr.relation_status IN ({status_placeholders})
          AND cr.valid_to IS NULL
          AND (
              (cr.from_entity_id = ? AND cr.to_entity_id = ?)
              OR (
                  cr.from_entity_id = ?
                  AND cr.to_entity_id = ?
                  AND cr.relation_type IN ({symmetric_placeholders})
              )
          )
        ORDER BY match_rank, cr.verified_at DESC, cr.created_at DESC
        """,
        (
            claim["from_entity_id"],
            claim["to_entity_id"],
            *CURRENT_EFFECTIVE_STATUSES,
            claim["from_entity_id"],
            claim["to_entity_id"],
            claim["to_entity_id"],
            claim["from_entity_id"],
            *sorted(SYMMETRIC_RELATION_TYPES),
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def _is_compatible(candidate_relation_type: str, history_relation_type: str) -> bool:
    compatible_types = COMPATIBLE_RELATION_TYPES.get(candidate_relation_type, set())
    return history_relation_type in compatible_types


def _classify(claim: dict[str, Any], history: dict[str, Any]) -> tuple[str, str]:
    if history["relation_status"] == "rejected":
        confidence_level = claim["confidence_level"] or ""
        if confidence_level in CHALLENGE_REJECTED_CONFIDENCE_LEVELS:
            return (
                "history_conflict",
                (
                    "new medium/high confidence candidate challenges rejected history "
                    f"{history['relationship_id']}"
                ),
            )
        return (
            "history_matched",
            f"low confidence candidate keeps rejected history {history['relationship_id']}",
        )

    if _is_compatible(claim["candidate_relation_type"], history["relation_type"]):
        return (
            "history_matched",
            f"compatible historical relationship {history['relationship_id']} was found",
        )

    return (
        "history_conflict",
        (
            f"candidate type {claim['candidate_relation_type']} conflicts with historical "
            f"type {history['relation_type']} on {history['relationship_id']}"
        ),
    )


def classify_claim_against_history(
    connection,
    claim: dict[str, Any],
) -> dict[str, Any] | None:
    """Return history classification context for one claim."""

    histories = _fetch_effective_history(connection, claim)
    if not histories:
        return None

    history = histories[0]
    outcome, reason = _classify(claim, history)
    return {
        "claim_id": claim["claim_id"],
        "outcome": outcome,
        "reason": reason,
        "history_relationship": history,
    }


def get_history_context_for_claim(
    claim_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return the effective historical relationship context for a claim."""

    with get_connection(db_path) as connection:
        claim = _fetch_claim(connection, claim_id)
        if claim is None:
            return None
        return classify_claim_against_history(connection, claim)


def apply_history_reuse_to_claims(
    *,
    run_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    """Classify reviewable claims against current effective historical relationships."""

    counters = {"history_matched": 0, "history_conflict": 0, "unchanged": 0}
    status_placeholders = ", ".join("?" for _ in REVIEWABLE_CLAIM_STATUSES)
    params: list[Any] = [*REVIEWABLE_CLAIM_STATUSES]
    run_filter = ""
    if run_id:
        run_filter = "AND rc.run_id = ?"
        params.append(run_id)

    with get_connection(db_path) as connection:
        claims = connection.execute(
            f"""
            SELECT rc.*
            FROM relationship_claim rc
            WHERE rc.relation_status IN ({status_placeholders})
              {run_filter}
            ORDER BY rc.created_at
            """,
            tuple(params),
        ).fetchall()

        for claim_row in claims:
            claim = dict(claim_row)
            context = classify_claim_against_history(connection, claim)
            if context is None:
                counters["unchanged"] += 1
                continue

            outcome = context["outcome"]
            counters[outcome] += 1
            connection.execute(
                """
                UPDATE relationship_claim
                SET relation_status = ?,
                    recommendation_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE claim_id = ?
                """,
                (
                    outcome,
                    _append_history_reason(claim["recommendation_reason"], context["reason"]),
                    claim["claim_id"],
                ),
            )

        connection.commit()

    return counters
