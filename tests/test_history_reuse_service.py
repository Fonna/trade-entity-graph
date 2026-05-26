from __future__ import annotations

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.history_reuse_service import (
    apply_history_reuse_to_claims,
    get_history_context_for_claim,
)
from trade_entity_graph.utils.ids import new_id


def _insert_batch(connection, run_id: str = "RUN_HISTORY") -> None:
    connection.execute(
        """
        INSERT INTO import_batch (run_id, source_file, imported_by)
        VALUES (?, 'history.csv', 'tester')
        """,
        (run_id,),
    )


def _insert_entity(connection, name: str) -> str:
    entity_id = new_id("ENT")
    connection.execute(
        """
        INSERT INTO entity (entity_id, canonical_name, entity_type)
        VALUES (?, ?, ?)
        """,
        (entity_id, name, "company"),
    )
    return entity_id


def _insert_claim(
    connection,
    from_entity_id: str,
    to_entity_id: str,
    *,
    candidate_relation_type: str = "trading_partner_candidate",
    confidence_level: str = "medium",
    confidence_score: float = 0.55,
    recommendation_reason: str | None = "3 orders, 12.5 TEU",
    run_id: str = "RUN_HISTORY",
) -> str:
    claim_id = new_id("CLM")
    connection.execute(
        """
        INSERT INTO relationship_claim (
            claim_id, from_entity_id, to_entity_id, candidate_relation_type,
            relation_status, confidence_level, confidence_score, order_count,
            total_teu, recommendation_reason, run_id
        )
        VALUES (?, ?, ?, ?, 'candidate', ?, ?, 3, 12.5, ?, ?)
        """,
        (
            claim_id,
            from_entity_id,
            to_entity_id,
            candidate_relation_type,
            confidence_level,
            confidence_score,
            recommendation_reason,
            run_id,
        ),
    )
    return claim_id


def _insert_history(
    connection,
    from_entity_id: str,
    to_entity_id: str,
    *,
    relation_type: str,
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
        VALUES (?, ?, ?, ?, ?, 'manual', 'Historical review', 'reviewer', CURRENT_TIMESTAMP, ?)
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


def _read_claim_status(db_path, claim_id: str) -> str:
    with get_connection(db_path) as connection:
        return connection.execute(
            "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()["relation_status"]


def _read_claim_reason(db_path, claim_id: str) -> str:
    with get_connection(db_path) as connection:
        return connection.execute(
            "SELECT recommendation_reason FROM relationship_claim WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()["recommendation_reason"]


def test_compatible_positive_history_marks_claim_as_history_matched(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_claim(connection, acme, beta)
        history_id = _insert_history(
            connection,
            acme,
            beta,
            relation_type="trading_partner",
            relation_status="verified",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)
    context = get_history_context_for_claim(claim_id, db_path=db_path)

    assert result == {"history_matched": 1, "history_conflict": 0, "unchanged": 0}
    assert _read_claim_status(db_path, claim_id) == "history_matched"
    assert context is not None
    assert context["claim_id"] == claim_id
    assert context["outcome"] == "history_matched"
    assert context["history_relationship"]["relationship_id"] == history_id
    assert "compatible historical relationship" in context["reason"]
    assert "history reuse:" in _read_claim_reason(db_path, claim_id)


def test_rejected_history_with_high_confidence_candidate_marks_conflict(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        omega = _insert_entity(connection, "OMEGA BUYER")
        claim_id = _insert_claim(connection, acme, omega, confidence_level="high")
        _insert_history(
            connection,
            acme,
            omega,
            relation_type="trading_partner",
            relation_status="rejected",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)
    context = get_history_context_for_claim(claim_id, db_path=db_path)

    assert result == {"history_matched": 0, "history_conflict": 1, "unchanged": 0}
    assert _read_claim_status(db_path, claim_id) == "history_conflict"
    assert context is not None
    assert context["outcome"] == "history_conflict"
    assert "challenges rejected history" in context["reason"]


def test_rejected_history_with_low_confidence_candidate_marks_history_matched(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        omega = _insert_entity(connection, "OMEGA BUYER")
        claim_id = _insert_claim(
            connection,
            acme,
            omega,
            confidence_level="low",
            confidence_score=0.3,
        )
        _insert_history(
            connection,
            acme,
            omega,
            relation_type="trading_partner",
            relation_status="rejected",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert result == {"history_matched": 1, "history_conflict": 0, "unchanged": 0}
    assert _read_claim_status(db_path, claim_id) == "history_matched"


def test_deprecated_history_is_ignored_and_candidate_stays_candidate(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_claim(connection, acme, beta)
        _insert_history(
            connection,
            acme,
            beta,
            relation_type="trading_partner",
            relation_status="deprecated",
            valid_to="2026-05-01 00:00:00",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert result == {"history_matched": 0, "history_conflict": 0, "unchanged": 1}
    assert _read_claim_status(db_path, claim_id) == "candidate"


def test_symmetric_history_types_match_reverse_pair(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_claim(connection, acme, beta)
        _insert_history(
            connection,
            beta,
            acme,
            relation_type="same_group",
            relation_status="verified",
        )
        connection.commit()

    apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert _read_claim_status(db_path, claim_id) == "history_matched"


def test_subsidiary_candidate_matches_subsidiary_history(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        parent = _insert_entity(connection, "PARENT GROUP")
        child = _insert_entity(connection, "CHILD FACTORY")
        claim_id = _insert_claim(
            connection,
            parent,
            child,
            candidate_relation_type="subsidiary_candidate",
        )
        _insert_history(
            connection,
            parent,
            child,
            relation_type="subsidiary",
            relation_status="verified",
        )
        connection.commit()

    apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert _read_claim_status(db_path, claim_id) == "history_matched"


def test_directional_history_types_do_not_match_reverse_pair(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        parent = _insert_entity(connection, "PARENT GROUP")
        child = _insert_entity(connection, "CHILD FACTORY")
        claim_id = _insert_claim(
            connection,
            child,
            parent,
            candidate_relation_type="factory_candidate",
        )
        _insert_history(
            connection,
            parent,
            child,
            relation_type="subsidiary",
            relation_status="verified",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert result == {"history_matched": 0, "history_conflict": 0, "unchanged": 1}
    assert _read_claim_status(db_path, claim_id) == "candidate"


def test_empty_reason_rerun_does_not_duplicate_history_reuse_note(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        _insert_batch(connection)
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_claim(connection, acme, beta, recommendation_reason=None)
        _insert_history(
            connection,
            acme,
            beta,
            relation_type="trading_partner",
            relation_status="verified",
        )
        connection.commit()

    apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)
    apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    reason = _read_claim_reason(db_path, claim_id)
    assert reason.count("history reuse:") == 1
