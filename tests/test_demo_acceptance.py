from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.generate_demo_data import write_demo_data
from scripts.import_demo_data import import_demo_data
from scripts.seed_demo_reviews import seed_demo_reviews
from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.services.export_service import export_relationship_rows
from trade_entity_graph.services.graph_service import get_ego_graph
from trade_entity_graph.services.relationship_service import get_relationship_evidence
from trade_entity_graph.services.review_service import decide_relationship


def test_generate_demo_data_writes_importable_files(tmp_path) -> None:
    output_dir = tmp_path / "demo"

    result = write_demo_data(output_dir)

    entities_path = output_dir / "demo_entities.csv"
    orders_path = output_dir / "demo_orders.csv"
    candidates_path = output_dir / "demo_relationship_candidates.csv"
    readme_path = output_dir / "README.md"

    assert result["entity_count"] == 50
    assert 80 <= result["order_count"] <= 120
    assert result["supplemental_candidate_count"] >= 6
    assert entities_path.exists()
    assert orders_path.exists()
    assert candidates_path.exists()
    assert readme_path.exists()
    readme_text = readme_path.read_text(encoding="utf-8")
    assert "scripts\\start_demo.ps1" in readme_text
    assert "-PrepareDemoData" in readme_text
    assert "data/processed/logs/" in readme_text

    entities = pd.read_csv(entities_path)
    orders = pd.read_csv(orders_path)
    candidates = pd.read_csv(candidates_path)

    assert set(
        [
            "canonical_name",
            "original_name",
            "clean_name",
            "alias_name",
            "country",
            "entity_type",
        ]
    ).issubset(entities.columns)
    assert set(
        [
            "order_id",
            "customer_name",
            "shipper_name",
            "consignee_name",
            "notify_name",
            "teu",
            "product_name",
            "function_category",
            "destination_country",
            "destination_port",
            "order_date",
        ]
    ).issubset(orders.columns)
    assert set(
        [
            "from_canonical_name",
            "to_canonical_name",
            "candidate_relation_type",
            "confidence_level",
            "confidence_score",
            "order_count",
            "total_teu",
            "recommendation_reason",
        ]
    ).issubset(candidates.columns)
    assert entities["entity_type"].nunique() >= 7
    assert orders["customer_name"].nunique() >= 10
    assert orders["destination_country"].nunique() >= 8
    assert orders["product_name"].nunique() >= 6
    assert {"SAME AS", "TO ORDER", "YQN LOGISTICS"} & set(orders["notify_name"])


def test_import_demo_data_loads_sources_edges_claims_and_supplemental_candidates(
    tmp_path, monkeypatch
) -> None:
    output_dir = tmp_path / "demo"
    db_path = tmp_path / "trade_entity_graph.db"
    archive_root = tmp_path / "archives"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(archive_root))
    write_demo_data(output_dir)

    result = import_demo_data(output_dir=output_dir, db_path=db_path)

    with get_connection(db_path) as connection:
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        alias_count = connection.execute("SELECT COUNT(*) FROM entity_alias").fetchone()[0]
        evidence_count = connection.execute("SELECT COUNT(*) FROM order_evidence").fetchone()[0]
        edge_count = connection.execute("SELECT COUNT(*) FROM order_role_edge").fetchone()[0]
        claim_count = connection.execute("SELECT COUNT(*) FROM relationship_claim").fetchone()[0]
        confidence_levels = {
            row["confidence_level"]
            for row in connection.execute(
                "SELECT DISTINCT confidence_level FROM relationship_claim"
            ).fetchall()
        }
        archived_roles = {
            row["source_role"]
            for row in connection.execute("SELECT source_role FROM import_source_file").fetchall()
        }
        supplemental = connection.execute(
            """
            SELECT COUNT(*)
            FROM relationship_claim
            WHERE candidate_relation_type IN (
                'same_group_candidate',
                'subsidiary_candidate',
                'logistics_service_candidate',
                'unknown_candidate'
            )
            """
        ).fetchone()[0]

    assert result["run_id"].startswith("RUN_")
    assert entity_count == 50
    assert alias_count >= 100
    assert evidence_count == result["evidence_count"]
    assert 80 <= evidence_count <= 120
    assert edge_count == result["edge_count"]
    assert edge_count > evidence_count * 2
    assert claim_count == result["claim_count"] + result["supplemental_candidate_count"]
    assert {"high", "medium", "low"}.issubset(confidence_levels)
    assert archived_roles == {"entities", "orders"}
    assert supplemental == result["supplemental_candidate_count"]


def _entity_id(db_path: Path, canonical_name: str) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT entity_id FROM entity WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()
    assert row is not None
    return row["entity_id"]


def test_demo_acceptance_flow_imports_reviews_graphs_and_exports(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "demo"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))
    write_demo_data(output_dir)
    import_demo_data(output_dir=output_dir, db_path=db_path)

    seed_result = seed_demo_reviews(db_path=db_path)

    with get_connection(db_path) as connection:
        curated_count = connection.execute("SELECT COUNT(*) FROM curated_relationship").fetchone()[
            0
        ]
        decision_count = connection.execute(
            "SELECT COUNT(*) FROM relationship_decision"
        ).fetchone()[0]
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        relation_types = {
            row["relation_type"]
            for row in connection.execute(
                "SELECT DISTINCT relation_type FROM curated_relationship"
            ).fetchall()
        }
        statuses = {
            row["relation_status"]
            for row in connection.execute(
                "SELECT DISTINCT relation_status FROM curated_relationship"
            ).fetchall()
        }
        pending_claims = connection.execute(
            """
            SELECT COUNT(*)
            FROM relationship_claim rc
            WHERE NOT EXISTS (
                SELECT 1
                FROM curated_relationship cr
                WHERE cr.decision_source = rc.claim_id
            )
            """
        ).fetchone()[0]
        center_id = _entity_id(db_path, "APEX OUTDOOR USA")
        rejected_relationship_id = connection.execute(
            """
            SELECT relationship_id
            FROM curated_relationship
            WHERE relation_status = 'rejected'
              AND (from_entity_id = ? OR to_entity_id = ?)
            LIMIT 1
            """,
            (center_id, center_id),
        ).fetchone()["relationship_id"]

    assert seed_result["created_relationship_count"] >= 12
    assert curated_count == seed_result["created_relationship_count"]
    assert decision_count == curated_count
    assert audit_count == curated_count
    assert {
        "same_group",
        "subsidiary",
        "factory_node",
        "sales_center",
        "trading_partner",
        "logistics_service",
        "rejected_relation",
    }.issubset(relation_types)
    assert {"verified", "rejected", "manual_only"}.issubset(statuses)
    assert pending_claims >= 10

    graph = get_ego_graph(center_id, db_path=db_path)
    graph_with_rejected = get_ego_graph(center_id, db_path=db_path, include_rejected=True)
    exported = export_relationship_rows(center_id, db_path=db_path)
    evidence = []
    for row in exported:
        evidence = get_relationship_evidence(row["relationship_id"], db_path=db_path)
        if evidence:
            break

    assert graph["summary"]["node_count"] >= 5
    assert graph["summary"]["edge_count"] >= 10
    assert all(edge["status"] != "rejected" for edge in graph["edges"])
    assert any(edge["id"] == rejected_relationship_id for edge in graph_with_rejected["edges"])
    assert exported
    assert evidence

    second_seed = seed_demo_reviews(db_path=db_path)
    assert second_seed["skipped"] is True


def test_demo_pending_candidate_is_visible_then_hidden_after_review(
    tmp_path, monkeypatch
) -> None:
    output_dir = tmp_path / "demo"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))
    write_demo_data(output_dir)
    import_demo_data(output_dir=output_dir, db_path=db_path)
    seed_demo_reviews(db_path=db_path)

    with get_connection(db_path) as connection:
        pending_claim = connection.execute(
            """
            SELECT *
            FROM relationship_claim rc
            WHERE rc.relation_status = 'candidate'
              AND NOT EXISTS (
                SELECT 1
                FROM curated_relationship cr
                WHERE cr.decision_source = rc.claim_id
              )
              AND NOT EXISTS (
                SELECT 1
                FROM curated_relationship history
                WHERE history.relation_status IN ('verified', 'manual_only', 'rejected')
                  AND history.valid_to IS NULL
                  AND (
                    (
                      history.from_entity_id = rc.from_entity_id
                      AND history.to_entity_id = rc.to_entity_id
                    )
                    OR (
                      history.from_entity_id = rc.to_entity_id
                      AND history.to_entity_id = rc.from_entity_id
                      AND history.relation_type IN (
                        'same_entity', 'same_group', 'trading_partner'
                      )
                    )
                  )
              )
            ORDER BY rc.confidence_score DESC, rc.order_count DESC
            LIMIT 1
            """
        ).fetchone()

    assert pending_claim is not None
    center_id = pending_claim["from_entity_id"]
    claim_id = pending_claim["claim_id"]

    graph = get_ego_graph(center_id, db_path=db_path)
    pending_graph_claims = {
        edge["id"]
        for edge in graph["edges"]
        if edge["edge_type"] == "relationship_claim"
    }

    assert claim_id in pending_graph_claims

    reviewed = decide_relationship(
        claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Demo candidate confirmed from graph",
        operator="tester",
        db_path=db_path,
    )
    graph_after_review = get_ego_graph(center_id, db_path=db_path)
    pending_after_review = {
        edge["id"]
        for edge in graph_after_review["edges"]
        if edge["edge_type"] == "relationship_claim"
    }
    curated_after_review = {
        edge["id"]
        for edge in graph_after_review["edges"]
        if edge["edge_type"] == "curated_relationship"
    }

    assert claim_id not in pending_after_review
    assert reviewed["relationship_id"] in curated_after_review
