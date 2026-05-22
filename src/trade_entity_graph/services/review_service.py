"""Manual review decisions and audit log writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.utils.ids import new_id


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
        claim = connection.execute(
            "SELECT * FROM relationship_claim WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        if not claim:
            raise ValueError(f"Unknown relationship claim: {claim_id}")

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
