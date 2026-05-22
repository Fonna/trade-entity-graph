import pandas as pd

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    generate_order_role_edges,
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
