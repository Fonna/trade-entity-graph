from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.review_queue_service import list_review_queue


def _seed_review_queue(db_path) -> None:
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_QUEUE_A', 'queue-a.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_QUEUE_B', 'queue-b.csv', 'tester')
            """
        )
        entities = [
            ("ENT_A", "ACME TRADING"),
            ("ENT_B", "BETA FACTORY"),
            ("ENT_C", "CROWN BUYER"),
            ("ENT_D", "DELTA FACTORY"),
        ]
        connection.executemany(
            "INSERT INTO entity (entity_id, canonical_name, entity_type) VALUES (?, ?, 'company')",
            entities,
        )
        claims = [
            (
                "CLM_CONFLICT",
                "ENT_A",
                "ENT_B",
                "history_conflict",
                "high",
                0.91,
                8,
                32.5,
                "RUN_QUEUE_A",
                "conflicting historical rejection",
            ),
            (
                "CLM_MATCHED",
                "ENT_A",
                "ENT_C",
                "history_matched",
                "medium",
                0.65,
                4,
                12.0,
                "RUN_QUEUE_A",
                "matched historical relationship",
            ),
            (
                "CLM_CANDIDATE",
                "ENT_B",
                "ENT_C",
                "candidate",
                "high",
                0.82,
                6,
                20.0,
                "RUN_QUEUE_B",
                "new high confidence candidate",
            ),
            (
                "CLM_PENDING",
                "ENT_C",
                "ENT_D",
                "pending_verify",
                "low",
                0.3,
                1,
                1.5,
                "RUN_QUEUE_B",
                "needs more public information",
            ),
            (
                "CLM_FINALIZED",
                "ENT_A",
                "ENT_D",
                "candidate",
                "high",
                0.88,
                5,
                18.0,
                "RUN_QUEUE_A",
                "already reviewed",
            ),
            (
                "CLM_KEEP_HISTORY",
                "ENT_B",
                "ENT_D",
                "history_matched",
                "high",
                0.9,
                7,
                25.0,
                "RUN_QUEUE_A",
                "already kept history",
            ),
        ]
        connection.executemany(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, run_id, recommendation_reason
            )
            VALUES (?, ?, ?, 'trading_partner_candidate', ?, ?, ?, ?, ?, ?, ?)
            """,
            claims,
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, confidence_level, confidence_score, source_type,
                decision_source, decision_note, verified_by, verified_at
            )
            VALUES (
                'REL_FINALIZED', 'ENT_A', 'ENT_D', 'trading_partner',
                'verified', 'high', 0.88, 'claim', 'CLM_FINALIZED',
                'finalized', 'tester', CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_decision (
                decision_id, relationship_id, claim_id, action_type,
                before_relation_type, after_relation_type, before_status,
                after_status, reason, operator
            )
            VALUES (
                'DEC_KEEP_HISTORY', NULL, 'CLM_KEEP_HISTORY', 'keep_history',
                'trading_partner_candidate', 'trading_partner', 'history_matched',
                'history_matched', 'keep history', 'tester'
            )
            """
        )
        connection.commit()


def test_review_queue_lists_unfinalized_claims_by_priority(tmp_path) -> None:
    db_path = tmp_path / "review-queue.db"
    _seed_review_queue(db_path)

    queue = list_review_queue(db_path=db_path)

    assert [item["claim_id"] for item in queue["items"]] == [
        "CLM_CONFLICT",
        "CLM_MATCHED",
        "CLM_CANDIDATE",
        "CLM_PENDING",
    ]
    assert queue["summary"]["total_count"] == 4
    assert queue["summary"]["status_counts"] == {
        "history_conflict": 1,
        "history_matched": 1,
        "candidate": 1,
        "pending_verify": 1,
    }
    assert queue["items"][0]["from_name"] == "ACME TRADING"
    assert queue["items"][0]["review_action_hint"].startswith("优先复核历史冲突")


def test_review_queue_filters_by_run_status_confidence_and_keyword(tmp_path) -> None:
    db_path = tmp_path / "review-queue-filter.db"
    _seed_review_queue(db_path)

    queue = list_review_queue(
        db_path=db_path,
        statuses=("candidate", "pending_verify"),
        run_id="RUN_QUEUE_B",
        confidence_levels=("high",),
        keyword="beta",
    )

    assert [item["claim_id"] for item in queue["items"]] == ["CLM_CANDIDATE"]
    assert queue["summary"]["total_count"] == 1
