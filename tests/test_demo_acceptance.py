from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_demo_data import write_demo_data
from scripts.import_demo_data import import_demo_data
from trade_entity_graph.db.connection import get_connection


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
