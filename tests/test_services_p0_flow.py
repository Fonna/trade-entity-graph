import pandas as pd

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.entity_service import get_entity_detail, search_entities
from trade_entity_graph.services.export_service import export_relationship_rows
from trade_entity_graph.services.graph_service import get_ego_graph
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    generate_order_role_edges,
    get_relationship_detail,
)
from trade_entity_graph.services.review_service import (
    create_manual_relationship,
    decide_relationship,
)


def _seed_p0_flow(tmp_path):
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.csv"
    db_path = tmp_path / "trade_entity_graph.db"

    pd.DataFrame(
        {
            "标准名": ["ACME TRADING", "BETA FACTORY", "OMEGA BUYER"],
            "原始名": ["Acme Trading Ltd", "Beta Factory Inc", "Omega Buyer LLC"],
            "清洗名": ["ACME TRADING LTD", "BETA FACTORY INC", "OMEGA BUYER LLC"],
            "主体类型": ["customer", "factory", "buyer"],
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
    generate_order_role_edges(db_path=db_path, run_id=result.run_id)
    aggregate_relationship_claims(db_path=db_path, run_id=result.run_id)
    return db_path


def _entity_id(db_path, canonical_name: str) -> str:
    with get_connection(db_path) as connection:
        return connection.execute(
            "SELECT entity_id FROM entity WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()["entity_id"]


def _claim_id(db_path, source: str, target: str) -> str:
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT claim_id
            FROM relationship_claim rc
            JOIN entity e1 ON e1.entity_id = rc.from_entity_id
            JOIN entity e2 ON e2.entity_id = rc.to_entity_id
            WHERE e1.canonical_name = ? AND e2.canonical_name = ?
            """,
            (source, target),
        ).fetchone()["claim_id"]


def test_entity_search_detail_graph_review_and_export_p0_flow(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    beta_id = _entity_id(db_path, "BETA FACTORY")
    omega_id = _entity_id(db_path, "OMEGA BUYER")

    matches = search_entities("acme", db_path=db_path)
    detail = get_entity_detail(acme_id, db_path=db_path)

    assert matches[0]["entity_id"] == acme_id
    assert detail["canonical_name"] == "ACME TRADING"
    assert detail["alias_count"] == 2
    assert detail["order_edge_count"] == 5

    confirmed = decide_relationship(
        _claim_id(db_path, "ACME TRADING", "BETA FACTORY"),
        action_type="confirm",
        relation_type="trading_partner",
        reason="Confirmed by sales",
        operator="tester",
        db_path=db_path,
    )
    rejected = decide_relationship(
        _claim_id(db_path, "ACME TRADING", "OMEGA BUYER"),
        action_type="reject",
        relation_type="rejected_relation",
        reason="Notify party is not related",
        operator="tester",
        db_path=db_path,
    )
    modified = decide_relationship(
        _claim_id(db_path, "BETA FACTORY", "OMEGA BUYER"),
        action_type="modify",
        relation_type="factory_node",
        reason="Factory supplies buyer",
        operator="tester",
        db_path=db_path,
    )
    manual = create_manual_relationship(
        beta_id,
        acme_id,
        relation_type="sales_center",
        reason="Manual business knowledge",
        operator="tester",
        db_path=db_path,
    )

    assert confirmed["relation_status"] == "verified"
    assert rejected["relation_status"] == "rejected"
    assert modified["relation_type"] == "factory_node"
    assert manual["source_type"] == "manual"

    graph = get_ego_graph(acme_id, db_path=db_path)
    exported = export_relationship_rows(acme_id, db_path=db_path)

    assert {node["id"] for node in graph["nodes"]} == {acme_id, beta_id, omega_id}
    assert any(edge["edge_type"] == "order_role_edge" for edge in graph["edges"])
    assert any(edge["id"] == confirmed["relationship_id"] for edge in graph["edges"])
    assert all(edge["status"] != "rejected" for edge in graph["edges"])
    assert any(row["relationship_id"] == confirmed["relationship_id"] for row in exported)

    with get_connection(db_path) as connection:
        decision_count = connection.execute(
            "SELECT COUNT(*) FROM relationship_decision"
        ).fetchone()[0]
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    assert decision_count == 4
    assert audit_count == 4


def test_ego_graph_includes_pending_claims_and_hides_reviewed_claims(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    beta_claim_id = _claim_id(db_path, "ACME TRADING", "BETA FACTORY")

    graph = get_ego_graph(acme_id, db_path=db_path)

    pending_claim_edges = [
        edge for edge in graph["edges"] if edge["edge_type"] == "relationship_claim"
    ]
    pending_claim_ids = {edge["id"] for edge in pending_claim_edges}

    assert beta_claim_id in pending_claim_ids
    beta_claim_edge = next(edge for edge in pending_claim_edges if edge["id"] == beta_claim_id)
    assert beta_claim_edge["record_type"] == "relationship_claim"
    assert beta_claim_edge["relation_type"] == "trading_partner_candidate"
    assert beta_claim_edge["status"] == "candidate"
    assert beta_claim_edge["confidence_level"] == "medium"
    assert beta_claim_edge["confidence_score"] == 0.55
    assert beta_claim_edge["order_count"] == 2
    assert beta_claim_edge["total_teu"] == 7.5
    assert beta_claim_edge["source_label"] == "ACME TRADING"
    assert beta_claim_edge["target_label"] == "BETA FACTORY"
    assert "2 orders" in beta_claim_edge["label"]

    beta_claim_detail = get_relationship_detail(beta_claim_id, db_path=db_path)

    assert beta_claim_detail is not None
    assert beta_claim_detail["from_name"] == "ACME TRADING"
    assert beta_claim_detail["to_name"] == "BETA FACTORY"

    reviewed = decide_relationship(
        beta_claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Confirmed by graph review",
        operator="tester",
        db_path=db_path,
    )
    reviewed_graph = get_ego_graph(acme_id, db_path=db_path)

    reviewed_pending_ids = {
        edge["id"]
        for edge in reviewed_graph["edges"]
        if edge["edge_type"] == "relationship_claim"
    }
    curated_ids = {
        edge["id"]
        for edge in reviewed_graph["edges"]
        if edge["edge_type"] == "curated_relationship"
    }

    assert beta_claim_id not in reviewed_pending_ids
    assert reviewed["relationship_id"] in curated_ids


def test_deprecated_relationship_is_hidden_from_graph_export_and_entity_counts(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    claim_id = _claim_id(db_path, "ACME TRADING", "BETA FACTORY")
    confirmed = decide_relationship(
        claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Confirmed by sales",
        operator="tester",
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE curated_relationship
            SET relation_status = 'deprecated',
                valid_to = CURRENT_TIMESTAMP
            WHERE relationship_id = ?
            """,
            (confirmed["relationship_id"],),
        )
        connection.commit()

    graph = get_ego_graph(acme_id, db_path=db_path, include_rejected=True)
    exported = export_relationship_rows(acme_id, db_path=db_path, include_rejected=True)
    detail = get_entity_detail(acme_id, db_path=db_path)

    assert all(edge["id"] != confirmed["relationship_id"] for edge in graph["edges"])
    assert all(row["relationship_id"] != confirmed["relationship_id"] for row in exported)
    assert detail is not None
    assert detail["curated_relationship_count"] == 0


def test_ego_graph_includes_history_conflict_claim_edges(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    beta_claim_id = _claim_id(db_path, "ACME TRADING", "BETA FACTORY")

    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE relationship_claim
            SET relation_status = 'history_conflict'
            WHERE claim_id = ?
            """,
            (beta_claim_id,),
        )
        connection.commit()

    graph = get_ego_graph(acme_id, db_path=db_path)
    history_conflict_edge = next(
        edge for edge in graph["edges"] if edge["id"] == beta_claim_id
    )

    assert history_conflict_edge["edge_type"] == "relationship_claim"
    assert history_conflict_edge["status"] == "history_conflict"


def test_ego_graph_hides_rejected_relationship_nodes_by_default(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    omega_id = _entity_id(db_path, "OMEGA BUYER")
    rejected = decide_relationship(
        _claim_id(db_path, "ACME TRADING", "OMEGA BUYER"),
        action_type="reject",
        relation_type="rejected_relation",
        reason="Rejected by graph review",
        operator="tester",
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        connection.execute(
            """
            DELETE FROM order_role_edge
            WHERE (from_entity_id = ? AND to_entity_id = ?)
               OR (from_entity_id = ? AND to_entity_id = ?)
            """,
            (acme_id, omega_id, omega_id, acme_id),
        )
        connection.commit()

    graph = get_ego_graph(acme_id, db_path=db_path)
    graph_with_rejected = get_ego_graph(acme_id, db_path=db_path, include_rejected=True)

    assert omega_id not in {node["id"] for node in graph["nodes"]}
    assert all(edge["id"] != rejected["relationship_id"] for edge in graph["edges"])
    assert omega_id in {node["id"] for node in graph_with_rejected["nodes"]}
    assert any(edge["id"] == rejected["relationship_id"] for edge in graph_with_rejected["edges"])
