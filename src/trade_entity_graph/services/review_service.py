"""Manual review decisions and audit log writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.services.history_reuse_service import (
    SYMMETRIC_RELATION_TYPES,
    get_history_context_for_claim,
)
from trade_entity_graph.utils.ids import new_id

CURRENT_EFFECTIVE_STATUSES = ("verified", "manual_only", "rejected")
KEEP_HISTORY_CLAIM_STATUSES = ("history_conflict", "pending_verify")
MARK_PENDING_CLAIM_STATUSES = ("candidate", "history_conflict", "history_matched")
ORDINARY_DECISION_CLAIM_STATUSES = (
    "candidate",
    "pending_verify",
    "history_conflict",
    "history_matched",
)
SUPERSEDE_CLAIM_STATUSES = ("history_conflict",)


def _write_decision_and_audit(
    connection,
    *,
    relationship_id: str,
    claim_id: str | None,
    action_type: str,
    before_relation_type: str | None,
    after_relation_type: str,
    before_status: str | None,
    after_status: str,
    reason: str,
    operator: str,
) -> None:
    connection.execute(
        """
        INSERT INTO relationship_decision (
            decision_id, relationship_id, claim_id, action_type, before_relation_type,
            after_relation_type, before_status, after_status, reason, operator
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("DEC"),
            relationship_id,
            claim_id,
            action_type,
            before_relation_type,
            after_relation_type,
            before_status,
            after_status,
            reason,
            operator,
        ),
    )
    connection.execute(
        """
        INSERT INTO audit_log (
            audit_id, object_type, object_id, action_type, after_value, operator, reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("AUD"),
            "curated_relationship",
            relationship_id,
            action_type,
            after_status,
            operator,
            reason,
        ),
    )


def _write_claim_decision_and_audit(
    connection,
    *,
    claim: dict[str, Any],
    relationship_id: str | None,
    action_type: str,
    after_status: str,
    reason: str,
    operator: str,
    after_relation_type: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO relationship_decision (
            decision_id, relationship_id, claim_id, action_type, before_relation_type,
            after_relation_type, before_status, after_status, reason, operator
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("DEC"),
            relationship_id,
            claim["claim_id"],
            action_type,
            claim["candidate_relation_type"],
            after_relation_type or claim["candidate_relation_type"],
            claim["relation_status"],
            after_status,
            reason,
            operator,
        ),
    )
    connection.execute(
        """
        INSERT INTO audit_log (
            audit_id, object_type, object_id, action_type, before_value,
            after_value, operator, reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("AUD"),
            "relationship_claim",
            claim["claim_id"],
            action_type,
            claim["relation_status"],
            after_status,
            operator,
            reason,
        ),
    )


def _fetch_claim_or_raise(connection, claim_id: str) -> dict[str, Any]:
    claim = connection.execute(
        "SELECT * FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if not claim:
        raise ValueError(f"Unknown relationship claim: {claim_id}")
    return dict(claim)


def _fetch_relationship_or_raise(connection, relationship_id: str) -> dict[str, Any]:
    relationship = connection.execute(
        "SELECT * FROM curated_relationship WHERE relationship_id = ?",
        (relationship_id,),
    ).fetchone()
    if not relationship:
        raise ValueError(f"Unknown curated relationship: {relationship_id}")
    return dict(relationship)


def _fetch_current_effective_history_for_claim(
    connection,
    *,
    claim: dict[str, Any],
    relationship_id: str,
) -> dict[str, Any]:
    status_placeholders = ", ".join("?" for _ in CURRENT_EFFECTIVE_STATUSES)
    symmetric_placeholders = ", ".join("?" for _ in SYMMETRIC_RELATION_TYPES)
    relationship = connection.execute(
        f"""
        SELECT *
        FROM curated_relationship
        WHERE relationship_id = ?
          AND relation_status IN ({status_placeholders})
          AND valid_to IS NULL
          AND (
              (from_entity_id = ? AND to_entity_id = ?)
              OR (
                  from_entity_id = ?
                  AND to_entity_id = ?
                  AND relation_type IN ({symmetric_placeholders})
              )
          )
        """,
        (
            relationship_id,
            *CURRENT_EFFECTIVE_STATUSES,
            claim["from_entity_id"],
            claim["to_entity_id"],
            claim["to_entity_id"],
            claim["from_entity_id"],
            *sorted(SYMMETRIC_RELATION_TYPES),
        ),
    ).fetchone()
    if not relationship:
        raise ValueError(
            "Superseded relationship must be current-effective and match the claim pair"
        )
    return dict(relationship)


def _validate_supersede_claim_state(claim: dict[str, Any]) -> None:
    if claim["relation_status"] not in SUPERSEDE_CLAIM_STATUSES:
        raise ValueError("Claim must be in history_conflict status to supersede history")


def _validate_claim_state(
    claim: dict[str, Any],
    *,
    allowed_statuses: tuple[str, ...],
    action: str,
) -> None:
    if claim["relation_status"] not in allowed_statuses:
        allowed = ", ".join(allowed_statuses)
        raise ValueError(f"Claim must be in one of ({allowed}) to {action}")


def _ensure_claim_has_no_curated_relationship(connection, claim_id: str) -> None:
    existing = connection.execute(
        """
        SELECT relationship_id
        FROM curated_relationship
        WHERE decision_source = ?
        LIMIT 1
        """,
        (claim_id,),
    ).fetchone()
    if existing:
        raise ValueError(f"Claim already has a reviewed relationship: {claim_id}")


def _ensure_claim_has_no_history_final_decision(connection, claim_id: str) -> None:
    existing = connection.execute(
        """
        SELECT decision_id
        FROM relationship_decision
        WHERE claim_id = ?
          AND action_type IN ('keep_history', 'supersede')
        LIMIT 1
        """,
        (claim_id,),
    ).fetchone()
    if existing:
        raise ValueError(f"Claim already finalized by history review: {claim_id}")


def _resolve_history_relationship_id(
    claim_id: str,
    *,
    old_relationship_id: str | None,
    db_path: str | Path | None,
) -> str:
    if old_relationship_id is not None:
        return old_relationship_id

    context = get_history_context_for_claim(claim_id, db_path=db_path)
    if context is None:
        raise ValueError(f"No historical relationship found for claim: {claim_id}")
    return context["history_relationship"]["relationship_id"]


def decide_relationship(
    claim_id: str,
    *,
    action_type: str,
    relation_type: str,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a curated relationship from a candidate review decision."""

    status_by_action = {"confirm": "verified", "modify": "verified", "reject": "rejected"}
    if action_type not in status_by_action:
        raise ValueError(f"Unsupported action_type: {action_type}")

    with get_connection(db_path) as connection:
        claim = _fetch_claim_or_raise(connection, claim_id)
        _validate_claim_state(
            claim,
            allowed_statuses=ORDINARY_DECISION_CLAIM_STATUSES,
            action="decide relationship",
        )
        _ensure_claim_has_no_curated_relationship(connection, claim_id)
        _ensure_claim_has_no_history_final_decision(connection, claim_id)

        relationship_id = new_id("REL")
        after_status = status_by_action[action_type]
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, confidence_level, confidence_score, source_type,
                decision_source, decision_note, verified_by, verified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                relationship_id,
                claim["from_entity_id"],
                claim["to_entity_id"],
                relation_type,
                after_status,
                claim["confidence_level"],
                claim["confidence_score"],
                "claim",
                claim_id,
                reason,
                operator,
            ),
        )
        _write_decision_and_audit(
            connection,
            relationship_id=relationship_id,
            claim_id=claim_id,
            action_type=action_type,
            before_relation_type=claim["candidate_relation_type"],
            after_relation_type=relation_type,
            before_status=claim["relation_status"],
            after_status=after_status,
            reason=reason,
            operator=operator,
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM curated_relationship WHERE relationship_id = ?",
            (relationship_id,),
        ).fetchone()
        return dict(row)


def keep_history_for_claim(
    claim_id: str,
    *,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Keep the effective historical relationship and mark the claim as matched."""

    with get_connection(db_path) as connection:
        claim = _fetch_claim_or_raise(connection, claim_id)
        _validate_claim_state(
            claim,
            allowed_statuses=KEEP_HISTORY_CLAIM_STATUSES,
            action="keep history",
        )
        _ensure_claim_has_no_curated_relationship(connection, claim_id)
        history_relationship_id = _resolve_history_relationship_id(
            claim_id,
            old_relationship_id=None,
            db_path=db_path,
        )
        history = _fetch_relationship_or_raise(connection, history_relationship_id)
        after_status = "history_matched"
        status_placeholders = ", ".join("?" for _ in KEEP_HISTORY_CLAIM_STATUSES)
        cursor = connection.execute(
            f"""
            UPDATE relationship_claim
            SET relation_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE claim_id = ?
              AND relation_status IN ({status_placeholders})
            """,
            (after_status, claim_id, *KEEP_HISTORY_CLAIM_STATUSES),
        )
        if cursor.rowcount != 1:
            raise ValueError("Claim must be in an allowed state to keep history")
        _write_claim_decision_and_audit(
            connection,
            claim=claim,
            relationship_id=history_relationship_id,
            action_type="keep_history",
            after_relation_type=history["relation_type"],
            after_status=after_status,
            reason=reason,
            operator=operator,
        )
        connection.commit()
        return {
            "claim_id": claim_id,
            "relation_status": after_status,
            "history_relationship_id": history_relationship_id,
        }


def supersede_history_with_claim(
    claim_id: str,
    *,
    old_relationship_id: str | None = None,
    relation_type: str,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Deprecate the historical relationship and create a verified replacement."""

    relationship_id = new_id("REL")
    with get_connection(db_path) as connection:
        claim = _fetch_claim_or_raise(connection, claim_id)
        _validate_supersede_claim_state(claim)
        _ensure_claim_has_no_curated_relationship(connection, claim_id)
        history_relationship_id = _resolve_history_relationship_id(
            claim_id,
            old_relationship_id=old_relationship_id,
            db_path=db_path,
        )
        old_relationship = _fetch_current_effective_history_for_claim(
            connection,
            claim=claim,
            relationship_id=history_relationship_id,
        )
        status_placeholders = ", ".join("?" for _ in CURRENT_EFFECTIVE_STATUSES)
        symmetric_placeholders = ", ".join("?" for _ in SYMMETRIC_RELATION_TYPES)
        cursor = connection.execute(
            f"""
            UPDATE curated_relationship
            SET relation_status = 'deprecated',
                valid_to = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE relationship_id = ?
              AND relation_status IN ({status_placeholders})
              AND valid_to IS NULL
              AND (
                  (from_entity_id = ? AND to_entity_id = ?)
                  OR (
                      from_entity_id = ?
                      AND to_entity_id = ?
                      AND relation_type IN ({symmetric_placeholders})
                  )
              )
            """,
            (
                history_relationship_id,
                *CURRENT_EFFECTIVE_STATUSES,
                claim["from_entity_id"],
                claim["to_entity_id"],
                claim["to_entity_id"],
                claim["from_entity_id"],
                *sorted(SYMMETRIC_RELATION_TYPES),
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError(
                "Superseded relationship must be current-effective and match the claim pair"
            )
        connection.execute(
            """
            INSERT INTO audit_log (
                audit_id, object_type, object_id, action_type, before_value,
                after_value, operator, reason
            )
            VALUES (?, 'curated_relationship', ?, 'deprecated', ?, ?, ?, ?)
            """,
            (
                new_id("AUD"),
                history_relationship_id,
                old_relationship["relation_status"],
                "deprecated",
                operator,
                reason,
            ),
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, confidence_level, confidence_score, source_type,
                decision_source, decision_note, verified_by, verified_at,
                valid_from, supersedes_relationship_id
            )
            VALUES (?, ?, ?, ?, 'verified', ?, ?, 'reviewed_claim', ?, ?, ?,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            """,
            (
                relationship_id,
                claim["from_entity_id"],
                claim["to_entity_id"],
                relation_type,
                claim["confidence_level"],
                claim["confidence_score"],
                claim_id,
                reason,
                operator,
                history_relationship_id,
            ),
        )
        connection.execute(
            """
            UPDATE relationship_claim
            SET relation_status = 'verified', updated_at = CURRENT_TIMESTAMP
            WHERE claim_id = ?
            """,
            (claim_id,),
        )
        _write_decision_and_audit(
            connection,
            relationship_id=relationship_id,
            claim_id=claim_id,
            action_type="supersede",
            before_relation_type=old_relationship["relation_type"],
            after_relation_type=relation_type,
            before_status=old_relationship["relation_status"],
            after_status="verified",
            reason=reason,
            operator=operator,
        )
        connection.execute(
            """
            INSERT INTO audit_log (
                audit_id, object_type, object_id, action_type, before_value,
                after_value, operator, reason
            )
            VALUES (?, 'relationship_claim', ?, 'supersede', ?, 'verified', ?, ?)
            """,
            (
                new_id("AUD"),
                claim_id,
                claim["relation_status"],
                operator,
                reason,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM curated_relationship WHERE relationship_id = ?",
            (relationship_id,),
        ).fetchone()
        result = dict(row)
        result["history_relationship_id"] = history_relationship_id
        return result


def mark_claim_pending_verify(
    claim_id: str,
    *,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Mark a claim for further verification without changing history."""

    with get_connection(db_path) as connection:
        claim = _fetch_claim_or_raise(connection, claim_id)
        _validate_claim_state(
            claim,
            allowed_statuses=MARK_PENDING_CLAIM_STATUSES,
            action="mark pending verify",
        )
        _ensure_claim_has_no_curated_relationship(connection, claim_id)
        _ensure_claim_has_no_history_final_decision(connection, claim_id)
        after_status = "pending_verify"
        status_placeholders = ", ".join("?" for _ in MARK_PENDING_CLAIM_STATUSES)
        cursor = connection.execute(
            f"""
            UPDATE relationship_claim
            SET relation_status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE claim_id = ?
              AND relation_status IN ({status_placeholders})
            """,
            (after_status, claim_id, *MARK_PENDING_CLAIM_STATUSES),
        )
        if cursor.rowcount != 1:
            raise ValueError("Claim must be in an allowed state to mark pending verify")
        _write_claim_decision_and_audit(
            connection,
            claim=claim,
            relationship_id=None,
            action_type="mark_pending_verify",
            after_status=after_status,
            reason=reason,
            operator=operator,
        )
        connection.commit()
        return {"claim_id": claim_id, "relation_status": after_status}


def create_manual_relationship(
    from_entity_id: str,
    to_entity_id: str,
    *,
    relation_type: str,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a manual curated relationship."""

    relationship_id = new_id("REL")
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                relationship_id,
                from_entity_id,
                to_entity_id,
                relation_type,
                "manual_only",
                "manual",
                reason,
                operator,
            ),
        )
        _write_decision_and_audit(
            connection,
            relationship_id=relationship_id,
            claim_id=None,
            action_type="manual_create",
            before_relation_type=None,
            after_relation_type=relation_type,
            before_status=None,
            after_status="manual_only",
            reason=reason,
            operator=operator,
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM curated_relationship WHERE relationship_id = ?",
            (relationship_id,),
        ).fetchone()
        return dict(row)
