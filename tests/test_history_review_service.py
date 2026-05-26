from __future__ import annotations

import pytest

import trade_entity_graph.services.review_service as review_service_module
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
from trade_entity_graph.services.relationship_service import get_relationship_detail
from trade_entity_graph.services.review_service import (
    decide_relationship,
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
    relation_type: str = "trading_partner",
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
        VALUES (?, ?, ?, ?, ?, 'manual',
                'Historical relationship', 'reviewer', CURRENT_TIMESTAMP, ?)
        """,
        (
            relationship_id,
            from_entity_id,
            to_entity_id,
            relation_type,
            relation_status,
            valid_to,
        ),
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


def _insert_decision(
    connection,
    claim_id: str,
    relationship_id: str | None,
    *,
    action_type: str,
) -> None:
    connection.execute(
        """
        INSERT INTO relationship_decision (
            decision_id, relationship_id, claim_id, action_type,
            before_status, after_status, reason, operator
        )
        VALUES (?, ?, ?, ?, 'history_conflict', 'history_matched',
                'Pre-existing final decision', 'tester')
        """,
        (new_id("DEC"), relationship_id, claim_id, action_type),
    )


def _insert_reviewed_relationship_for_claim(connection, claim_id: str) -> str:
    claim = connection.execute(
        "SELECT * FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    relationship_id = new_id("REL")
    connection.execute(
        """
        INSERT INTO curated_relationship (
            relationship_id, from_entity_id, to_entity_id, relation_type,
            relation_status, confidence_level, confidence_score, source_type,
            decision_source, decision_note, verified_by, verified_at
        )
        VALUES (?, ?, ?, 'trading_partner', 'verified', ?, ?, 'claim', ?,
                'Pre-existing ordinary review', 'tester', CURRENT_TIMESTAMP)
        """,
        (
            relationship_id,
            claim["from_entity_id"],
            claim["to_entity_id"],
            claim["confidence_level"],
            claim["confidence_score"],
            claim_id,
        ),
    )
    return relationship_id


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


def _seed_candidate_with_effective_history(db_path) -> tuple[str, str]:
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_high_confidence_claim(connection, acme, beta)
        history_id = _insert_history(
            connection,
            acme,
            beta,
            relation_status="rejected",
        )
        connection.commit()
        return claim_id, history_id


def _seed_fresh_candidate(db_path) -> str:
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_high_confidence_claim(connection, acme, beta)
        connection.commit()
        return claim_id


def _fetch_one(db_path, query: str, params: tuple = ()):
    with get_connection(db_path) as connection:
        row = connection.execute(query, params).fetchone()
        return dict(row) if row is not None else None


def _fetch_all(db_path, query: str, params: tuple = ()) -> list[dict]:
    with get_connection(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


class _RecordingConnection:
    def __init__(self, connection, statements: list[str]) -> None:
        self._connection = connection
        self._statements = statements

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._connection.__exit__(exc_type, exc_value, traceback)

    def execute(self, sql, parameters=()):
        self._statements.append(" ".join(sql.split()).upper())
        return self._connection.execute(sql, parameters)

    def __getattr__(self, name):
        return getattr(self._connection, name)


def test_decide_relationship_starts_immediate_transaction_before_reads(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id = _seed_fresh_candidate(db_path)
    statements: list[str] = []
    original_get_connection = review_service_module.get_connection

    def recording_get_connection(path=None):
        return _RecordingConnection(original_get_connection(path), statements)

    monkeypatch.setattr(review_service_module, "get_connection", recording_get_connection)

    decide_relationship(
        claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Ordinary review with transaction lock",
        operator="tester",
        db_path=db_path,
    )

    assert statements[0] == "BEGIN IMMEDIATE"


def test_decide_relationship_rejects_history_conflict_without_curated_row(
    tmp_path,
) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, _history_id = _seed_history_conflict(db_path)

    with pytest.raises(ValueError, match="candidate"):
        decide_relationship(
            claim_id,
            action_type="confirm",
            relation_type="trading_partner",
            reason="Ordinary review must not bypass historical supersede",
            operator="tester",
            db_path=db_path,
        )

    claim_relationship_count = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM curated_relationship
        WHERE decision_source = ?
        """,
        (claim_id,),
    )
    relationship_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) AS count FROM curated_relationship",
    )

    assert claim_relationship_count == {"count": 0}
    assert relationship_count == {"count": 1}


def test_decide_relationship_rejects_candidate_with_unapplied_effective_history(
    tmp_path,
) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_candidate_with_effective_history(db_path)

    with pytest.raises(ValueError, match="history-aware review action"):
        decide_relationship(
            claim_id,
            action_type="confirm",
            relation_type="trading_partner",
            reason="Ordinary review must not bypass unapplied historical supersede",
            operator="tester",
            db_path=db_path,
        )

    claim_relationship_count = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM curated_relationship
        WHERE decision_source = ?
        """,
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

    assert claim_relationship_count == {"count": 0}
    assert old_relationship == {"relation_status": "rejected", "valid_to": None}


def test_decide_relationship_accepts_fresh_candidate_without_effective_history(
    tmp_path,
) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id = _seed_fresh_candidate(db_path)

    result = decide_relationship(
        claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Ordinary review for fresh evidence",
        operator="tester",
        db_path=db_path,
    )

    assert result["decision_source"] == claim_id
    assert result["relation_status"] == "verified"


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


def test_keep_history_for_claim_accepts_history_matched_claim(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_high_confidence_claim(connection, acme, beta)
        history_id = _insert_history(
            connection,
            acme,
            beta,
            relation_status="verified",
        )
        connection.commit()

    reuse_result = apply_history_reuse_to_claims(
        run_id="RUN_HISTORY_REVIEW",
        db_path=db_path,
    )
    result = keep_history_for_claim(
        claim_id,
        reason="Keep compatible verified history",
        operator="tester",
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="already finalized|unfinalized"):
        keep_history_for_claim(
            claim_id,
            reason="Duplicate keep history",
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
        """
        SELECT action_type, relationship_id
        FROM relationship_decision
        WHERE claim_id = ?
        """,
        (claim_id,),
    )
    relationship_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) AS count FROM curated_relationship",
    )

    assert reuse_result == {"history_matched": 1, "history_conflict": 0, "unchanged": 0}
    assert result["relation_status"] == "history_matched"
    assert result["history_relationship_id"] == history_id
    assert claim == {"relation_status": "history_matched"}
    assert decisions == [{"action_type": "keep_history", "relationship_id": history_id}]
    assert relationship_count == {"count": 1}


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
    assert new_relationships[0]["source_type"] == "reviewed_claim"
    supersede_decision = next(
        decision for decision in decisions if decision["action_type"] == "supersede"
    )
    assert supersede_decision["relationship_id"] == new_relationships[0]["relationship_id"]
    assert (history_id, "deprecated") in {
        (audit["object_id"], audit["action_type"]) for audit in relationship_audits
    }
    assert (new_relationships[0]["relationship_id"], "supersede") in {
        (audit["object_id"], audit["action_type"]) for audit in relationship_audits
    }


def test_supersede_history_with_claim_accepts_history_matched_claim(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_high_confidence_claim(connection, acme, beta)
        history_id = _insert_history(
            connection,
            acme,
            beta,
            relation_type="trading_partner",
            relation_status="verified",
        )
        connection.commit()

    reuse_result = apply_history_reuse_to_claims(
        run_id="RUN_HISTORY_REVIEW",
        db_path=db_path,
    )
    claim_after_reuse = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )

    assert reuse_result == {"history_matched": 1, "history_conflict": 0, "unchanged": 0}
    assert claim_after_reuse == {"relation_status": "history_matched"}

    replacement = supersede_history_with_claim(
        claim_id,
        old_relationship_id=history_id,
        relation_type="trading_partner",
        reason="New import is correct; prior history match was wrong",
        operator="tester",
        db_path=db_path,
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
    new_relationship = _fetch_one(
        db_path,
        """
        SELECT relation_status, supersedes_relationship_id
        FROM curated_relationship
        WHERE relationship_id = ?
        """,
        (replacement["relationship_id"],),
    )
    claim_after_supersede = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )

    assert old_relationship["relation_status"] == "deprecated"
    assert old_relationship["valid_to"] is not None
    assert new_relationship == {
        "relation_status": "verified",
        "supersedes_relationship_id": history_id,
    }
    assert claim_after_supersede == {"relation_status": "verified"}

    with pytest.raises(ValueError):
        supersede_history_with_claim(
            claim_id,
            old_relationship_id=history_id,
            relation_type="trading_partner",
            reason="Do not allow duplicate finalization",
            operator="tester",
            db_path=db_path,
        )
    reviewed_relationship_count = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM curated_relationship
        WHERE decision_source = ?
        """,
        (claim_id,),
    )

    assert reviewed_relationship_count == {"count": 1}


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


def test_mark_pending_verify_keeps_history_context_available(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)

    mark_claim_pending_verify(
        claim_id,
        reason="Needs more evidence",
        operator="tester",
        db_path=db_path,
    )

    detail = get_relationship_detail(claim_id, db_path=db_path)

    assert detail is not None
    assert detail["relation_status"] == "pending_verify"
    assert detail["history_context"]["history_relationship"]["relationship_id"] == history_id


def test_supersede_history_with_claim_accepts_pending_verify_history_claim(
    tmp_path,
) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    mark_claim_pending_verify(
        claim_id,
        reason="Needs more evidence before replacing history",
        operator="tester",
        db_path=db_path,
    )

    result = supersede_history_with_claim(
        claim_id,
        relation_type="factory_node",
        reason="New evidence now supersedes history",
        operator="tester",
        db_path=db_path,
    )

    old_relationship = _fetch_one(
        db_path,
        "SELECT relation_status, valid_to FROM curated_relationship WHERE relationship_id = ?",
        (history_id,),
    )
    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )

    assert result["history_relationship_id"] == history_id
    assert result["supersedes_relationship_id"] == history_id
    assert old_relationship["relation_status"] == "deprecated"
    assert old_relationship["valid_to"] is not None
    assert claim == {"relation_status": "verified"}


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

    with pytest.raises(ValueError, match="current-effective and match the claim pair"):
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

    with pytest.raises(ValueError, match="current-effective and match the claim pair"):
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


def test_supersede_history_with_claim_cannot_be_repeated_for_verified_claim(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    first = supersede_history_with_claim(
        claim_id,
        old_relationship_id=history_id,
        relation_type="factory_node",
        reason="New evidence supersedes old rejection",
        operator="tester",
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="history_conflict"):
        supersede_history_with_claim(
            claim_id,
            relation_type="sales_center",
            reason="Repeated supersede should not create a chain",
            operator="tester",
            db_path=db_path,
        )

    verified_replacements = _fetch_all(
        db_path,
        """
        SELECT relationship_id, supersedes_relationship_id
        FROM curated_relationship
        WHERE relation_status = 'verified'
        """,
    )
    chained_replacements = _fetch_all(
        db_path,
        """
        SELECT relationship_id
        FROM curated_relationship
        WHERE supersedes_relationship_id = ?
        """,
        (first["relationship_id"],),
    )

    assert verified_replacements == [
        {
            "relationship_id": first["relationship_id"],
            "supersedes_relationship_id": history_id,
        }
    ]
    assert chained_replacements == []


def test_supersede_history_with_claim_rejects_existing_claim_relationship(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    with get_connection(db_path) as connection:
        existing_id = _insert_reviewed_relationship_for_claim(connection, claim_id)
        connection.commit()

    with pytest.raises(ValueError, match="already has a reviewed relationship"):
        supersede_history_with_claim(
            claim_id,
            old_relationship_id=history_id,
            relation_type="factory_node",
            reason="Should not duplicate reviewed claim output",
            operator="tester",
            db_path=db_path,
        )

    old_relationship = _fetch_one(
        db_path,
        "SELECT relation_status, valid_to FROM curated_relationship WHERE relationship_id = ?",
        (history_id,),
    )
    claim_relationships = _fetch_all(
        db_path,
        """
        SELECT relationship_id, source_type
        FROM curated_relationship
        WHERE decision_source = ?
        ORDER BY relationship_id
        """,
        (claim_id,),
    )

    assert old_relationship == {"relation_status": "rejected", "valid_to": None}
    assert claim_relationships == [
        {"relationship_id": existing_id, "source_type": "claim"}
    ]


def test_supersede_history_with_claim_rejects_existing_final_history_decision(
    tmp_path,
) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    with get_connection(db_path) as connection:
        _insert_decision(connection, claim_id, history_id, action_type="keep_history")
        connection.commit()

    with pytest.raises(ValueError, match="already finalized"):
        supersede_history_with_claim(
            claim_id,
            old_relationship_id=history_id,
            relation_type="factory_node",
            reason="Should not supersede after final history decision",
            operator="tester",
            db_path=db_path,
        )

    old_relationship = _fetch_one(
        db_path,
        "SELECT relation_status, valid_to FROM curated_relationship WHERE relationship_id = ?",
        (history_id,),
    )
    claim_relationship_count = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM curated_relationship
        WHERE decision_source = ?
        """,
        (claim_id,),
    )

    assert old_relationship == {"relation_status": "rejected", "valid_to": None}
    assert claim_relationship_count == {"count": 0}


def test_keep_history_for_claim_rejects_claim_with_ordinary_decision(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    with get_connection(db_path) as connection:
        existing_id = _insert_reviewed_relationship_for_claim(connection, claim_id)
        connection.commit()

    with pytest.raises(ValueError, match="already has a reviewed relationship"):
        keep_history_for_claim(
            claim_id,
            reason="Should not keep history after ordinary review",
            operator="tester",
            db_path=db_path,
        )

    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )
    claim_relationships = _fetch_all(
        db_path,
        """
        SELECT relationship_id
        FROM curated_relationship
        WHERE decision_source = ?
        """,
        (claim_id,),
    )
    keep_decisions = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM relationship_decision
        WHERE claim_id = ? AND action_type = 'keep_history'
        """,
        (claim_id,),
    )
    keep_audits = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM audit_log
        WHERE object_type = 'relationship_claim'
          AND object_id = ?
          AND action_type = 'keep_history'
        """,
        (claim_id,),
    )
    old_relationship = _fetch_one(
        db_path,
        "SELECT relation_status, valid_to FROM curated_relationship WHERE relationship_id = ?",
        (history_id,),
    )

    assert claim == {"relation_status": "history_conflict"}
    assert claim_relationships == [{"relationship_id": existing_id}]
    assert keep_decisions == {"count": 0}
    assert keep_audits == {"count": 0}
    assert old_relationship == {"relation_status": "rejected", "valid_to": None}


def test_mark_claim_pending_verify_rejects_claim_with_ordinary_decision(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, _history_id = _seed_history_conflict(db_path)
    with get_connection(db_path) as connection:
        existing_id = _insert_reviewed_relationship_for_claim(connection, claim_id)
        connection.commit()

    with pytest.raises(ValueError, match="already has a reviewed relationship"):
        mark_claim_pending_verify(
            claim_id,
            reason="Should not mark pending after ordinary review",
            operator="tester",
            db_path=db_path,
        )

    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )
    claim_relationships = _fetch_all(
        db_path,
        """
        SELECT relationship_id
        FROM curated_relationship
        WHERE decision_source = ?
        """,
        (claim_id,),
    )
    pending_decisions = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM relationship_decision
        WHERE claim_id = ? AND action_type = 'mark_pending_verify'
        """,
        (claim_id,),
    )

    assert claim == {"relation_status": "history_conflict"}
    assert claim_relationships == [{"relationship_id": existing_id}]
    assert pending_decisions == {"count": 0}


def test_decide_relationship_rejects_claim_after_keep_history(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, _history_id = _seed_history_conflict(db_path)
    keep_history_for_claim(
        claim_id,
        reason="Keep prior rejection",
        operator="tester",
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="candidate"):
        decide_relationship(
            claim_id,
            action_type="confirm",
            relation_type="trading_partner",
            reason="Stale ordinary review should fail",
            operator="tester",
            db_path=db_path,
        )

    claim_relationship_count = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM curated_relationship
        WHERE decision_source = ?
        """,
        (claim_id,),
    )

    assert claim_relationship_count == {"count": 0}


def test_decide_relationship_rejects_claim_after_supersede(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    existing = supersede_history_with_claim(
        claim_id,
        old_relationship_id=history_id,
        relation_type="factory_node",
        reason="New evidence supersedes old rejection",
        operator="tester",
        db_path=db_path,
    )

    allowed_status_pattern = "candidate|pending_verify|history_conflict|history_matched"
    with pytest.raises(ValueError, match=allowed_status_pattern):
        decide_relationship(
            claim_id,
            action_type="confirm",
            relation_type="trading_partner",
            reason="Stale ordinary review should fail",
            operator="tester",
            db_path=db_path,
        )

    claim_relationships = _fetch_all(
        db_path,
        """
        SELECT relationship_id
        FROM curated_relationship
        WHERE decision_source = ?
        """,
        (claim_id,),
    )

    assert claim_relationships == [{"relationship_id": existing["relationship_id"]}]


def test_keep_history_for_claim_rejects_verified_claim_after_supersede(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    supersede_history_with_claim(
        claim_id,
        old_relationship_id=history_id,
        relation_type="factory_node",
        reason="New evidence supersedes old rejection",
        operator="tester",
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="history_conflict|pending_verify"):
        keep_history_for_claim(
            claim_id,
            reason="Should not regress finalized claim",
            operator="tester",
            db_path=db_path,
        )

    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )

    assert claim == {"relation_status": "verified"}


def test_mark_claim_pending_verify_rejects_verified_claim_after_supersede(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, history_id = _seed_history_conflict(db_path)
    supersede_history_with_claim(
        claim_id,
        old_relationship_id=history_id,
        relation_type="factory_node",
        reason="New evidence supersedes old rejection",
        operator="tester",
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="candidate|history_conflict|history_matched"):
        mark_claim_pending_verify(
            claim_id,
            reason="Should not regress finalized claim",
            operator="tester",
            db_path=db_path,
        )

    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )

    assert claim == {"relation_status": "verified"}


def test_mark_claim_pending_verify_rejects_claim_after_keep_history(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, _history_id = _seed_history_conflict(db_path)
    keep_history_for_claim(
        claim_id,
        reason="Keep prior rejection",
        operator="tester",
        db_path=db_path,
    )

    with pytest.raises(ValueError, match="already finalized"):
        mark_claim_pending_verify(
            claim_id,
            reason="Should not reopen finalized keep-history claim",
            operator="tester",
            db_path=db_path,
        )

    claim = _fetch_one(
        db_path,
        "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )
    pending_decisions = _fetch_one(
        db_path,
        """
        SELECT COUNT(*) AS count
        FROM relationship_decision
        WHERE claim_id = ? AND action_type = 'mark_pending_verify'
        """,
        (claim_id,),
    )

    assert claim == {"relation_status": "history_matched"}
    assert pending_decisions == {"count": 0}


def test_apply_history_reuse_does_not_reprocess_keep_history_claim(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    claim_id, _history_id = _seed_history_conflict(db_path)
    keep_history_for_claim(
        claim_id,
        reason="Keep prior rejection",
        operator="tester",
        db_path=db_path,
    )
    reason_before = _fetch_one(
        db_path,
        "SELECT recommendation_reason FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    )

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY_REVIEW", db_path=db_path)

    claim = _fetch_one(
        db_path,
        """
        SELECT relation_status, recommendation_reason
        FROM relationship_claim
        WHERE claim_id = ?
        """,
        (claim_id,),
    )

    assert result == {"history_matched": 0, "history_conflict": 0, "unchanged": 1}
    assert claim == {
        "relation_status": "history_matched",
        "recommendation_reason": reason_before["recommendation_reason"],
    }


def test_supersede_history_with_claim_accepts_reversed_symmetric_history(tmp_path) -> None:
    db_path = tmp_path / "history-review.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_high_confidence_claim(connection, acme, beta)
        history_id = _insert_history(
            connection,
            beta,
            acme,
            relation_type="trading_partner",
            relation_status="rejected",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY_REVIEW", db_path=db_path)
    claim = _fetch_one(
        db_path,
        """
        SELECT from_entity_id, to_entity_id, relation_status
        FROM relationship_claim
        WHERE claim_id = ?
        """,
        (claim_id,),
    )

    assert result == {"history_matched": 0, "history_conflict": 1, "unchanged": 0}
    assert claim["relation_status"] == "history_conflict"

    replacement = supersede_history_with_claim(
        claim_id,
        old_relationship_id=history_id,
        relation_type="trading_partner",
        reason="Reversed symmetric history is superseded by new evidence",
        operator="tester",
        db_path=db_path,
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
    new_relationship = _fetch_one(
        db_path,
        """
        SELECT from_entity_id, to_entity_id, relation_status, supersedes_relationship_id
        FROM curated_relationship
        WHERE relationship_id = ?
        """,
        (replacement["relationship_id"],),
    )

    assert old_relationship["relation_status"] == "deprecated"
    assert old_relationship["valid_to"] is not None
    assert new_relationship == {
        "from_entity_id": claim["from_entity_id"],
        "to_entity_id": claim["to_entity_id"],
        "relation_status": "verified",
        "supersedes_relationship_id": history_id,
    }


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
