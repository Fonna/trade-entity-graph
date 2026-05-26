from __future__ import annotations

import pytest

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
from trade_entity_graph.services.review_service import (
    keep_history_for_claim,
    mark_claim_pending_verify,
    supersede_history_with_claim,
)
from trade_entity_graph.utils.ids import new_id


def _insert_batch(connection, run_id: str = "RUN_HISTORY_REVIEW") -> None:
    connection.execute(
        """
        INSERT INTO import_batch (run_id, source_file, imported_by)
        VALUES (?, 'history-review.csv', 'tester')
        """,
        (run_id,),
    )


def _insert_entity(connection, name: str) -> str:
    entity_id = new_id("ENT")
    connection.execute(
        """
        INSERT INTO entity (entity_id, canonical_name, entity_type)
        VALUES (?, ?, 'company')
        """,
        (entity_id, name),
    )
    return entity_id


def _insert_rejected_history(connection, from_entity_id: str, to_entity_id: str) -> str:
    relationship_id = new_id("REL")
    connection.execute(
        """
        INSERT INTO curated_relationship (
            relationship_id, from_entity_id, to_entity_id, relation_type,
            relation_status, source_type, decision_note, verified_by, verified_at
        )
        VALUES (?, ?, ?, 'trading_partner', 'rejected', 'manual',
                'Historical rejection', 'reviewer', CURRENT_TIMESTAMP)
        """,
        (relationship_id, from_entity_id, to_entity_id),
    )
    return relationship_id


def _insert_history(
    connection,
    from_entity_id: str,
    to_entity_id: str,
    *,
    relation_status: str,
    valid_to: str | None = None,
) -> str:
    relationship_id = new_id("REL")
    connection.execute(
        """
        INSERT INTO curated_relationship (
            relationship_id, from_entity_id, to_entity_id, relation_type,
            relation_status, source_type, decision_note, verified_by, verified_at, valid_to
        )
        VALUES (?, ?, ?, 'trading_partner', ?, 'manual',
                'Historical relationship', 'reviewer', CURRENT_TIMESTAMP, ?)
        """,
        (relationship_id, from_entity_id, to_entity_id, relation_status, valid_to),
    )
    return relationship_id


def _insert_high_confidence_claim(connection, from_entity_id: str, to_entity_id: str) -> str:
    claim_id = new_id("CLM")
    connection.execute(
        """
        INSERT INTO relationship_claim (
            claim_id, from_entity_id, to_entity_id, candidate_relation_type,
            relation_status, confidence_level, confidence_score, order_count,
            total_teu, recommendation_reason, run_id
        )
        VALUES (?, ?, ?, 'trading_partner_candidate', 'candidate', 'high', 0.88,
                5, 21.5, '5 orders, 21.5 TEU', 'RUN_HISTORY_REVIEW')
        """,
        (claim_id, from_entity_id, to_entity_id),
    )
    return claim_id


def _seed_history_conflict(db_path) -> tuple[str, str]:
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_high_confidence_claim(connection, acme, beta)
        history_id = _insert_rejected_history(connection, acme, beta)
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY_REVIEW", db_path=db_path)

    assert result == {"history_matched": 0, "history_conflict": 1, "unchanged": 0}
    return claim_id, history_id


def _fetch_one(db_path, query: str, params: tuple = ()):
    with get_connection(db_path) as connection:
        row = connection.execute(query, params).fetchone()
        return dict(row) if row is not None else None


def _fetch_all(db_path, query: str, params: tuple = ()) -> list[dict]:
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def test_keep_history_for_claim_reuses_history_without_duplicate_relationship(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)

    result = keep_history_for_claim(
        claim_id,
        reason="Keep prior rejection",
        operator="tester",
        db_path=db_path,
    )

    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )
    decisions = _fetch_all(
        db_path,
        "SELECT * FROM relationship_decision WHERE claim_id = ?",
        (claim_id,),
    )
    claim_audits = _fetch_all(
        db_path,
        """
        SELECT * FROM audit_log
        WHERE object_type = 'relationship_claim' AND object_id = ?
        """,
        (claim_id,),
    )
    relationship_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) AS count FROM curated_relationship",
    )

    assert result["claim_id"] == claim_id
    assert result["history_relationship_id"] == history_id
    assert claim == {"relation_status": "history_matched"}
    assert relationship_count == {"count": 1}
    assert [decision["action_type"] for decision in decisions] == ["keep_history"]
    assert decisions[0]["relationship_id"] == history_id
    assert [audit["action_type"] for audit in claim_audits] == ["keep_history"]


def test_supersede_history_with_claim_deprecates_old_and_creates_verified_relationship(
    tmp_path,
) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)

    result = supersede_history_with_claim(
        claim_id,
        old_relationship_id=history_id,
        relation_type="factory_node",
        reason="New evidence supersedes old rejection",
        operator="tester",
        db_path=db_path,
    )

    old_relationship = _fetch_one(
        db_path,
        "SELECT relation_status, valid_to FROM curated_relationship WHERE relationship_id = ?",
        (history_id,),
    )
    new_relationships = _fetch_all(
        db_path,
        """
        SELECT * FROM curated_relationship
        WHERE supersedes_relationship_id = ?
        """,
        (history_id,),
    )
    decisions = _fetch_all(
        db_path,
        "SELECT * FROM relationship_decision WHERE claim_id = ?",
        (claim_id,),
    )
    relationship_audits = _fetch_all(
        db_path,
        """
        SELECT object_id, action_type
        FROM audit_log
        WHERE object_type = 'curated_relationship'
        ORDER BY operated_at, audit_id
        """,
    )

    assert result["history_relationship_id"] == history_id
    assert result["relationship_id"] == new_relationships[0]["relationship_id"]
    assert old_relationship["relation_status"] == "deprecated"
    assert old_relationship["valid_to"] is not None
    assert len(new_relationships) == 1
    assert new_relationships[0]["relation_status"] == "verified"
    assert new_relationships[0]["relation_type"] == "factory_node"
    assert decisions[-1]["action_type"] == "supersede"
    assert decisions[-1]["relationship_id"] == new_relationships[0]["relationship_id"]
    assert (history_id, "deprecated") in {
        (audit["object_id"], audit["action_type"]) for audit in relationship_audits
    }
    assert (new_relationships[0]["relationship_id"], "supersede") in {
        (audit["object_id"], audit["action_type"]) for audit in relationship_audits
    }


def test_mark_claim_pending_verify_leaves_history_unchanged(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)

    result = mark_claim_pending_verify(
        claim_id,
        reason="Needs more evidence",
        operator="tester",
        db_path=db_path,
    )

    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )
    old_relationship = _fetch_one(
        db_path,
        """
        SELECT relation_status, valid_to
        FROM curated_relationship
        WHERE relationship_id = ?
        """,
        (history_id,),
    )
    decisions = _fetch_all(
        db_path,
        "SELECT * FROM relationship_decision WHERE claim_id = ?",
        (claim_id,),
    )

    assert result["claim_id"] == claim_id
    assert result["relation_status"] == "pending_verify"
    assert claim == {"relation_status": "pending_verify"}
    assert old_relationship == {"relation_status": "rejected", "valid_to": None}
    assert [decision["action_type"] for decision in decisions] == ["mark_pending_verify"]


def test_supersede_history_with_claim_rejects_unrelated_old_relationship(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, _history_id = _seed_history_conflict(db_path)
    with get_connection(db_path) as connection:
        gamma = _insert_entity(connection, "GAMMA EXPORTS")
        delta = _insert_entity(connection, "DELTA BUYER")
        unrelated_id = _insert_history(
            connection,
            gamma,
            delta,
            relation_status="rejected",
        )
        connection.commit()

    with pytest.raises(ValueError):
        supersede_history_with_claim(
            claim_id,
            old_relationship_id=unrelated_id,
            relation_type="factory_node",
            reason="Wrong relationship should not be touched",
            operator="tester",
            db_path=db_path,
        )

    unrelated = _fetch_one(
        db_path,
        """
        SELECT relation_status, valid_to
        FROM curated_relationship
        WHERE relationship_id = ?
        """,
        (unrelated_id,),
    )
    relationship_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) AS count FROM curated_relationship",
    )

    assert unrelated == {"relation_status": "rejected", "valid_to": None}
    assert relationship_count == {"count": 2}


def test_supersede_history_with_claim_rejects_deprecated_old_relationship(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, _history_id = _seed_history_conflict(db_path)
    with get_connection(db_path) as connection:
        claim = connection.execute(
            "SELECT from_entity_id, to_entity_id FROM relationship_claim WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        deprecated_id = _insert_history(
            connection,
            claim["from_entity_id"],
            claim["to_entity_id"],
            relation_status="deprecated",
            valid_to="2026-05-01 00:00:00",
        )
        connection.commit()

    with pytest.raises(ValueError):
        supersede_history_with_claim(
            claim_id,
            old_relationship_id=deprecated_id,
            relation_type="factory_node",
            reason="Deprecated relationship should not be touched",
            operator="tester",
            db_path=db_path,
        )

    deprecated = _fetch_one(
        db_path,
        """
        SELECT relation_status, valid_to
        FROM curated_relationship
        WHERE relationship_id = ?
        """,
        (deprecated_id,),
    )
    relationship_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) AS count FROM curated_relationship",
    )

    assert deprecated == {
        "relation_status": "deprecated",
        "valid_to": "2026-05-01 00:00:00",
    }
    assert relationship_count == {"count": 2}


def test_keep_history_for_claim_unknown_claim_raises_unknown_claim_error(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    initialize_database(db_path)

    with pytest.raises(ValueError, match="Unknown relationship claim"):
        keep_history_for_claim(
            "CLM_MISSING",
            reason="Cannot keep history for unknown claim",
            operator="tester",
            db_path=db_path,
        )
