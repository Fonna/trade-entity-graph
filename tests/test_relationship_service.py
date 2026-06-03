import pandas as pd

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    create_external_evidence,
    generate_order_role_edges,
    get_relationship_evidence,
)
from trade_entity_graph.services.review_service import (
    create_manual_relationship,
    decide_relationship,
)


def _seed_import(tmp_path):
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.csv"
    db_path = tmp_path / "trade_entity_graph.db"

    pd.DataFrame(
        {
            "标准名": ["ACME TRADING", "BETA FACTORY", "OMEGA BUYER"],
            "原始名": ["Acme Trading Ltd", "Beta Factory Inc", "Omega Buyer LLC"],
            "清洗名": ["ACME TRADING LTD", "BETA FACTORY INC", "OMEGA BUYER LLC"],
        }
    ).to_csv(entities_path, index=False)
    pd.DataFrame(
        {
            "订单号": ["SO-1", "SO-2"],
            "下单客户": ["Acme Trading Ltd", "Acme Trading Ltd"],
            "发货人": ["Beta Factory Inc", "Beta Factory Inc"],
            "收货人": ["Omega Buyer LLC", "Omega Buyer LLC"],
            "通知人": ["Omega Buyer LLC", "SAME AS"],
            "TEU": [3.5, 4.0],
            "产品名称": ["Widget", "Widget"],
            "目的国": ["MX", "MX"],
        }
    ).to_csv(orders_path, index=False)
    result = run_import(
        ImportInputs(orders_path=orders_path, entities_path=entities_path, imported_by="tester"),
        db_path=db_path,
    )
    return db_path, result.run_id


def test_generate_order_role_edges_creates_p0_edges_and_filters_placeholders(tmp_path) -> None:
    db_path, run_id = _seed_import(tmp_path)

    result = generate_order_role_edges(db_path=db_path, run_id=run_id)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT order_id, role_pair_type
            FROM order_role_edge
            ORDER BY order_id, role_pair_type
            """
        ).fetchall()

    assert result["edge_count"] == 7
    assert [row["role_pair_type"] for row in rows if row["order_id"] == "SO-1"] == [
        "customer_to_consignee",
        "customer_to_notify",
        "customer_to_shipper",
        "shipper_to_consignee",
    ]
    assert [row["role_pair_type"] for row in rows if row["order_id"] == "SO-2"] == [
        "customer_to_consignee",
        "customer_to_shipper",
        "shipper_to_consignee",
    ]


def test_aggregate_relationship_claims_rolls_up_edges_with_confidence(tmp_path) -> None:
    db_path, run_id = _seed_import(tmp_path)
    generate_order_role_edges(db_path=db_path, run_id=run_id)

    result = aggregate_relationship_claims(db_path=db_path, run_id=run_id)

    with get_connection(db_path) as connection:
        claims = connection.execute(
            """
            SELECT e1.canonical_name AS source, e2.canonical_name AS target,
                   order_count, total_teu, confidence_level, role_pair_summary,
                   recommendation_reason
            FROM relationship_claim rc
            JOIN entity e1 ON e1.entity_id = rc.from_entity_id
            JOIN entity e2 ON e2.entity_id = rc.to_entity_id
            ORDER BY source, target
            """
        ).fetchall()

    assert result["claim_count"] == 3
    acme_beta = next(
        row for row in claims if row["source"] == "ACME TRADING" and row["target"] == "BETA FACTORY"
    )
    assert acme_beta["order_count"] == 2
    assert acme_beta["total_teu"] == 7.5
    assert acme_beta["confidence_level"] == "medium"
    assert acme_beta["role_pair_summary"] == "customer_to_shipper:2"
    assert "2 orders" in acme_beta["recommendation_reason"]
    assert "7.5 TEU" in acme_beta["recommendation_reason"]


def _first_claim_id(db_path) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT claim_id FROM relationship_claim ORDER BY confidence_score DESC LIMIT 1"
        ).fetchone()
    return row["claim_id"]


def _entity_id(db_path, canonical_name: str) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT entity_id FROM entity WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()
    return row["entity_id"]


def test_create_external_evidence_attaches_structured_evidence_to_claim(tmp_path) -> None:
    db_path, run_id = _seed_import(tmp_path)
    generate_order_role_edges(db_path=db_path, run_id=run_id)
    aggregate_relationship_claims(db_path=db_path, run_id=run_id)
    claim_id = _first_claim_id(db_path)

    created = create_external_evidence(
        claim_id,
        {
            "evidence_type": "public_web",
            "source_title": "Beta factory profile",
            "source_url": "https://example.com/beta",
            "source_name": "Example Registry",
            "evidence_summary": "Registry profile links Beta to Acme supplier onboarding.",
            "evidence_date": "2026-06-03",
            "confidence_level": "medium",
            "created_by": "tester",
        },
        db_path=db_path,
    )

    evidence = get_relationship_evidence(claim_id, db_path=db_path)
    external_rows = [
        row for row in evidence if row["evidence_record_type"] == "external_evidence"
    ]

    assert created["claim_id"] == claim_id
    assert created["relationship_id"] is None
    assert external_rows[0]["source_title"] == "Beta factory profile"
    assert external_rows[0]["source_url"] == "https://example.com/beta"


def test_decide_relationship_with_external_evidence_binds_claim_and_relationship(
    tmp_path,
) -> None:
    db_path, run_id = _seed_import(tmp_path)
    generate_order_role_edges(db_path=db_path, run_id=run_id)
    aggregate_relationship_claims(db_path=db_path, run_id=run_id)
    claim_id = _first_claim_id(db_path)

    relationship = decide_relationship(
        claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Confirmed with public evidence.",
        operator="tester",
        external_evidence={
            "evidence_type": "sales_feedback",
            "source_title": "Sales confirmation",
            "source_name": "Sales team",
            "evidence_summary": "Sales confirmed this supplier relationship.",
            "confidence_level": "high",
            "created_by": "tester",
        },
        db_path=db_path,
    )

    evidence = get_relationship_evidence(relationship["relationship_id"], db_path=db_path)
    external_rows = [
        row for row in evidence if row["evidence_record_type"] == "external_evidence"
    ]

    assert external_rows[0]["claim_id"] == claim_id
    assert external_rows[0]["relationship_id"] == relationship["relationship_id"]
    assert external_rows[0]["evidence_type"] == "sales_feedback"


def test_create_manual_relationship_with_external_evidence_binds_relationship(tmp_path) -> None:
    db_path, _run_id = _seed_import(tmp_path)
    from_entity_id = _entity_id(db_path, "ACME TRADING")
    to_entity_id = _entity_id(db_path, "BETA FACTORY")

    relationship = create_manual_relationship(
        from_entity_id,
        to_entity_id,
        relation_type="same_group",
        reason="Manual review.",
        operator="tester",
        external_evidence={
            "evidence_type": "business_document",
            "source_title": "Internal account note",
            "evidence_summary": "Account owner confirmed group relationship.",
            "confidence_level": "high",
            "created_by": "tester",
        },
        db_path=db_path,
    )

    evidence = get_relationship_evidence(relationship["relationship_id"], db_path=db_path)
    external_rows = [
        row for row in evidence if row["evidence_record_type"] == "external_evidence"
    ]

    assert external_rows[0]["relationship_id"] == relationship["relationship_id"]
    assert external_rows[0]["claim_id"] is None
    assert external_rows[0]["source_title"] == "Internal account note"
