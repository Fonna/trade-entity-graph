from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.opportunity_service import analyze_graph_opportunities


def seed_m11_opportunity_graph(tmp_path):
    db_path = initialize_database(tmp_path / "m11-opportunities.db")
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_M11', 'm11.csv', 'tester')
            """
        )
        connection.executemany(
            """
            INSERT INTO entity (entity_id, canonical_name, country, entity_type, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("ENT_A", "ACME MARKET", "US", "customer", "key_customer"),
                ("ENT_B", "ORBIT ASIA HUB", "SG", "sales_center", "[]"),
                ("ENT_C", "VIETNAM FACTORY", "VN", "factory", "[]"),
                ("ENT_D", "EURO BUYER", "DE", "buyer", "[]"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUN_M11')
            """,
            [
                (
                    "CLM_AB",
                    "ENT_A",
                    "ENT_B",
                    "sales_center_candidate",
                    "candidate",
                    "high",
                    0.86,
                    6,
                    32.0,
                    "6 orders, 32 TEU, possible sales hub",
                ),
                (
                    "CLM_BC",
                    "ENT_B",
                    "ENT_C",
                    "factory_candidate",
                    "pending_verify",
                    "medium",
                    0.62,
                    3,
                    12.0,
                    "3 orders, 12 TEU, possible factory node",
                ),
            ],
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, confidence_level, confidence_score
            )
            VALUES (
                'REL_BD', 'ENT_B', 'ENT_D', 'trading_partner',
                'verified', 'high', 0.92
            )
            """
        )
        connection.commit()
    return db_path


def seed_rejected_relationship_pair(db_path):
    with get_connection(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO entity (entity_id, canonical_name, country, entity_type, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("ENT_X", "REJECTED SOURCE", "US", "customer", "[]"),
                ("ENT_Y", "REJECTED TARGET", "US", "consignee", "[]"),
            ],
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, confidence_level, confidence_score
            )
            VALUES (
                'REL_XY_REJECTED', 'ENT_X', 'ENT_Y', 'trading_partner',
                'rejected', 'low', 0.2
            )
            """
        )
        connection.commit()


def test_analyze_graph_opportunities_finds_relationships_bridges_and_customers(tmp_path):
    db_path = seed_m11_opportunity_graph(tmp_path)

    result = analyze_graph_opportunities(db_path=db_path, limit=10)

    assert result["summary"]["entity_count"] == 4
    assert result["summary"]["cluster_count"] == 1
    assert result["summary"]["relationship_opportunity_count"] == 2
    assert result["relationship_opportunities"][0]["claim_id"] == "CLM_AB"
    assert result["relationship_opportunities"][0]["opportunity_score"] == 1.0

    bridge = result["bridge_entities"][0]
    assert bridge["entity_id"] == "ENT_B"
    assert bridge["is_articulation_point"] is True
    assert bridge["candidate_edge_count"] == 2

    customer = result["customer_opportunities"][0]
    assert customer["entity_id"] == "ENT_A"
    assert customer["direct_neighbor_count"] == 1
    assert customer["second_hop_entity_count"] == 2
    assert customer["overseas_node_count"] == 3

    cluster = result["clusters"][0]
    assert cluster["entity_count"] == 4
    assert cluster["candidate_edge_count"] == 2
    assert cluster["verified_relationship_count"] == 1
    assert cluster["top_entities"][0]["entity_id"] == "ENT_B"


def test_analyze_graph_opportunities_applies_min_score_filter(tmp_path):
    db_path = seed_m11_opportunity_graph(tmp_path)

    result = analyze_graph_opportunities(db_path=db_path, limit=10, min_score=0.95)

    assert [item["claim_id"] for item in result["relationship_opportunities"]] == ["CLM_AB"]
    assert result["summary"]["relationship_opportunity_count"] == 1


def test_analyze_graph_opportunities_limits_each_result_collection(tmp_path):
    db_path = seed_m11_opportunity_graph(tmp_path)

    result = analyze_graph_opportunities(db_path=db_path, limit=1)

    assert len(result["relationship_opportunities"]) == 1
    assert len(result["bridge_entities"]) == 1
    assert len(result["customer_opportunities"]) == 1
    assert len(result["clusters"]) == 1
    assert result["summary"]["relationship_opportunity_count"] == 2


def test_analyze_graph_opportunities_include_rejected_controls_rejected_edges(tmp_path):
    db_path = seed_m11_opportunity_graph(tmp_path)
    seed_rejected_relationship_pair(db_path)

    default_result = analyze_graph_opportunities(db_path=db_path, limit=10)
    include_rejected_result = analyze_graph_opportunities(
        db_path=db_path,
        include_rejected=True,
        limit=10,
    )

    assert default_result["summary"]["entity_count"] == 4
    assert default_result["summary"]["edge_count"] == 3
    assert include_rejected_result["summary"]["entity_count"] == 6
    assert include_rejected_result["summary"]["edge_count"] == 4
    assert include_rejected_result["summary"]["include_rejected"] is True


def test_analyze_graph_opportunities_handles_empty_graph(tmp_path):
    db_path = initialize_database(tmp_path / "empty-m11-opportunities.db")

    result = analyze_graph_opportunities(db_path=db_path)

    assert result["summary"] == {
        "entity_count": 0,
        "edge_count": 0,
        "cluster_count": 0,
        "bridge_entity_count": 0,
        "customer_opportunity_count": 0,
        "relationship_opportunity_count": 0,
        "country_count": 0,
        "max_opportunity_score": 0.0,
        "include_rejected": False,
        "min_score": 0.0,
    }
    assert result["clusters"] == []
    assert result["bridge_entities"] == []
    assert result["customer_opportunities"] == []
    assert result["relationship_opportunities"] == []
