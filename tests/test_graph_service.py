import pytest

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.graph_service import find_entity_paths, get_ego_graph


def _seed_path_graph(tmp_path):
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")
    with get_connection(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type, tags)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ENT_A", "Alpha Trading", "customer", "[]"),
                ("ENT_B", "Beta Factory", "shipper", "[]"),
                ("ENT_C", "Gamma Buyer", "consignee", "[]"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO order_role_edge (
                edge_id,
                order_id,
                from_entity_id,
                from_role,
                to_entity_id,
                to_role,
                role_pair_type,
                teu
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "ORE_AB",
                    "ORD_1",
                    "ENT_A",
                    "customer",
                    "ENT_B",
                    "shipper",
                    "customer_to_shipper",
                    2.0,
                ),
                (
                    "ORE_BC",
                    "ORD_2",
                    "ENT_B",
                    "shipper",
                    "ENT_C",
                    "consignee",
                    "shipper_to_consignee",
                    3.0,
                ),
            ],
        )
    return db_path


def test_get_ego_graph_depth_defaults_to_one_hop_and_depth_two_expands(tmp_path):
    db_path = _seed_path_graph(tmp_path)

    one_hop = get_ego_graph("ENT_A", db_path=db_path)
    two_hop = get_ego_graph("ENT_A", db_path=db_path, depth=2, max_nodes=10)

    assert {node["id"] for node in one_hop["nodes"]} == {"ENT_A", "ENT_B"}
    assert {node["id"] for node in two_hop["nodes"]} == {"ENT_A", "ENT_B", "ENT_C"}
    assert two_hop["summary"]["depth"] == 2
    assert two_hop["summary"]["max_nodes"] == 10
    assert two_hop["summary"]["truncated"] is False


def test_get_ego_graph_depth_two_truncates_at_max_nodes(tmp_path):
    db_path = _seed_path_graph(tmp_path)

    graph = get_ego_graph("ENT_A", db_path=db_path, depth=2, max_nodes=2)

    assert len(graph["nodes"]) == 2
    assert graph["summary"]["truncated"] is True


def test_find_entity_paths_returns_indirect_path_with_edge_provenance(tmp_path):
    db_path = _seed_path_graph(tmp_path)

    result = find_entity_paths("ENT_A", "ENT_C", db_path=db_path, max_depth=3)

    assert result["path_count"] == 1
    path = result["paths"][0]
    assert path["node_ids"] == ["ENT_A", "ENT_B", "ENT_C"]
    assert [edge["record_type"] for edge in path["edges"]] == [
        "order_role_edge",
        "order_role_edge",
    ]
    assert "ENT_A" in path["explanation"]
    assert "ENT_C" in path["explanation"]


def test_find_entity_paths_does_not_mark_single_allowed_path_as_truncated(tmp_path):
    db_path = _seed_path_graph(tmp_path)

    result = find_entity_paths(
        "ENT_A",
        "ENT_C",
        db_path=db_path,
        max_depth=3,
        max_paths=1,
    )

    assert result["path_count"] == 1
    assert result["summary"]["truncated"] is False


def test_find_entity_paths_ranks_same_depth_paths_by_confidence_before_volume(tmp_path):
    db_path = _seed_path_graph(tmp_path)
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM order_role_edge")
        connection.executemany(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type, tags)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ENT_X", "Low Confidence Bridge", "company", "[]"),
                ("ENT_Y", "High Confidence Bridge", "company", "[]"),
            ],
        )
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_RANKING', 'ranking.csv', 'tester')
            """
        )
        connection.executemany(
            """
            INSERT INTO relationship_claim (
                claim_id,
                from_entity_id,
                to_entity_id,
                candidate_relation_type,
                relation_status,
                confidence_level,
                confidence_score,
                order_count,
                total_teu,
                recommendation_reason,
                run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RUN_RANKING')
            """,
            [
                (
                    "CLM_AX_LOW",
                    "ENT_A",
                    "ENT_X",
                    "trading_partner_candidate",
                    "candidate",
                    "low",
                    0.2,
                    100,
                    300.0,
                    "high volume but low confidence",
                ),
                (
                    "CLM_XC_LOW",
                    "ENT_X",
                    "ENT_C",
                    "trading_partner_candidate",
                    "candidate",
                    "low",
                    0.2,
                    100,
                    300.0,
                    "high volume but low confidence",
                ),
                (
                    "CLM_AY_HIGH",
                    "ENT_A",
                    "ENT_Y",
                    "trading_partner_candidate",
                    "candidate",
                    "high",
                    0.9,
                    1,
                    1.0,
                    "high confidence bridge",
                ),
                (
                    "CLM_YC_HIGH",
                    "ENT_Y",
                    "ENT_C",
                    "trading_partner_candidate",
                    "candidate",
                    "high",
                    0.9,
                    1,
                    1.0,
                    "high confidence bridge",
                ),
            ],
        )

    result = find_entity_paths("ENT_A", "ENT_C", db_path=db_path, max_depth=2)

    assert result["path_count"] == 2
    assert result["paths"][0]["node_ids"] == ["ENT_A", "ENT_Y", "ENT_C"]
    assert result["paths"][0]["score"] == pytest.approx(0.8)


def test_find_entity_paths_collapses_parallel_order_edges_into_one_route(tmp_path):
    db_path = _seed_path_graph(tmp_path)
    with get_connection(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO order_role_edge (
                edge_id,
                order_id,
                from_entity_id,
                from_role,
                to_entity_id,
                to_role,
                role_pair_type,
                teu
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "ORE_AB_DUP_1",
                    "ORD_DUP_1",
                    "ENT_A",
                    "customer",
                    "ENT_B",
                    "shipper",
                    "customer_to_shipper",
                    4.0,
                ),
                (
                    "ORE_AB_DUP_2",
                    "ORD_DUP_2",
                    "ENT_A",
                    "customer",
                    "ENT_B",
                    "shipper",
                    "customer_to_shipper",
                    5.5,
                ),
            ],
        )

    result = find_entity_paths(
        "ENT_A",
        "ENT_B",
        db_path=db_path,
        max_depth=1,
        max_paths=1,
    )

    assert result["path_count"] == 1
    assert result["summary"]["truncated"] is False
    path = result["paths"][0]
    assert path["node_ids"] == ["ENT_A", "ENT_B"]
    assert len(path["edges"]) == 1
    assert path["edges"][0]["order_count"] == 3
    assert path["edges"][0]["total_teu"] == pytest.approx(11.5)


def test_find_entity_paths_hides_rejected_curated_relationship_by_default(tmp_path):
    db_path = _seed_path_graph(tmp_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id,
                from_entity_id,
                to_entity_id,
                relation_type,
                relation_status,
                confidence_level,
                confidence_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("REL_AC_REJECTED", "ENT_A", "ENT_C", "partner", "rejected", "low", 0.2),
        )

    default_result = find_entity_paths("ENT_A", "ENT_C", db_path=db_path, max_depth=1)
    include_rejected_result = find_entity_paths(
        "ENT_A",
        "ENT_C",
        db_path=db_path,
        include_rejected=True,
        max_depth=1,
    )

    assert default_result["path_count"] == 0
    assert include_rejected_result["path_count"] == 1
    assert include_rejected_result["paths"][0]["edges"][0]["record_type"] == "curated_relationship"
    assert include_rejected_result["paths"][0]["edges"][0]["status"] == "rejected"


def test_find_entity_paths_includes_history_matched_claims(tmp_path):
    db_path = _seed_path_graph(tmp_path)
    with get_connection(db_path) as connection:
        connection.execute("DELETE FROM order_role_edge")
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_HISTORY_MATCHED', 'history.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id,
                from_entity_id,
                to_entity_id,
                candidate_relation_type,
                relation_status,
                confidence_level,
                confidence_score,
                order_count,
                total_teu,
                recommendation_reason,
                run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CLM_HISTORY_MATCHED",
                "ENT_A",
                "ENT_C",
                "trading_partner_candidate",
                "history_matched",
                "high",
                0.91,
                4,
                12.5,
                "history reuse matched",
                "RUN_HISTORY_MATCHED",
            ),
        )

    result = find_entity_paths("ENT_A", "ENT_C", db_path=db_path, max_depth=1)

    assert result["path_count"] == 1
    edge = result["paths"][0]["edges"][0]
    assert edge["record_type"] == "relationship_claim"
    assert edge["status"] == "history_matched"


def test_find_entity_paths_raises_for_unknown_endpoint(tmp_path):
    db_path = _seed_path_graph(tmp_path)

    with pytest.raises(ValueError, match="Unknown entity: NO_SUCH"):
        find_entity_paths("ENT_A", "NO_SUCH", db_path=db_path)
