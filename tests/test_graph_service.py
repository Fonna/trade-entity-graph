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


def test_find_entity_paths_raises_for_unknown_endpoint(tmp_path):
    db_path = _seed_path_graph(tmp_path)

    with pytest.raises(ValueError, match="Unknown entity: NO_SUCH"):
        find_entity_paths("ENT_A", "NO_SUCH", db_path=db_path)
