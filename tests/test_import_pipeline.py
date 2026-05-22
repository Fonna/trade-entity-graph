from pathlib import Path

import pandas as pd

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import


def test_run_import_loads_entities_orders_and_role_names(tmp_path, monkeypatch) -> None:
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    archive_root = tmp_path / "archives"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(archive_root))

    pd.DataFrame(
        {
            "标准名": ["ACME TRADING", "BETA FACTORY", "OMEGA BUYER"],
            "原始名": ["Acme Trading Ltd", "Beta Factory Inc", "Omega Buyer LLC"],
            "清洗名": ["ACME TRADING LTD", "BETA FACTORY INC", "OMEGA BUYER LLC"],
            "国家": ["US", "CN", "MX"],
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

    with get_connection(db_path) as connection:
        batch_count = connection.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0]
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        alias_count = connection.execute("SELECT COUNT(*) FROM entity_alias").fetchone()[0]
        evidence_rows = connection.execute(
            """
            SELECT order_id, customer_name, shipper_name, consignee_name, notify_name, teu
            FROM order_evidence
            ORDER BY order_id
            """
        ).fetchall()
        archived_rows = connection.execute(
            """
            SELECT source_role, original_path, archived_path, file_name, file_size_bytes, sha256
            FROM import_source_file
            WHERE run_id = ?
            ORDER BY source_role
            """,
            (result.run_id,),
        ).fetchall()

    assert result.run_id.startswith("RUN_")
    assert result.entity_count == 3
    assert result.alias_count == 6
    assert result.evidence_count == 2
    assert batch_count == 1
    assert entity_count == 3
    assert alias_count == 6
    assert [row["order_id"] for row in evidence_rows] == ["SO-1", "SO-2"]
    assert evidence_rows[0]["customer_name"] == "Acme Trading Ltd"
    assert evidence_rows[0]["shipper_name"] == "Beta Factory Inc"
    assert evidence_rows[0]["consignee_name"] == "Omega Buyer LLC"
    assert evidence_rows[1]["notify_name"] == "SAME AS"
    assert evidence_rows[0]["teu"] == 3.5
    assert len(result.archived_files) == 2
    assert {row["source_role"] for row in archived_rows} == {"entities", "orders"}
    assert {Path(row["original_path"]) for row in archived_rows} == {entities_path, orders_path}
    assert all(Path(row["archived_path"]).exists() for row in archived_rows)
    assert all(archive_root in Path(row["archived_path"]).parents for row in archived_rows)
    assert all(Path(row["archived_path"]).parent.name == result.run_id for row in archived_rows)
    assert all(row["file_size_bytes"] > 0 for row in archived_rows)
    assert all(len(row["sha256"]) == 64 for row in archived_rows)
    assert {item["source_role"] for item in result.archived_files} == {"entities", "orders"}


def test_run_import_allows_entities_without_country_or_entity_type(tmp_path, monkeypatch) -> None:
    entities_path = tmp_path / "entities.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {
            "标准名": ["ACME TRADING"],
            "原始名": ["Acme Trading Ltd"],
            "清洗名": ["ACME TRADING LTD"],
        }
    ).to_csv(entities_path, index=False)

    result = run_import(
        ImportInputs(entities_path=entities_path, imported_by="tester"),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT canonical_name, country, entity_type FROM entity"
        ).fetchone()

    assert result.entity_count == 1
    assert result.alias_count == 2
    assert result.skipped_rows == []
    assert row["canonical_name"] == "ACME TRADING"
    assert row["country"] is None
    assert row["entity_type"] is None
