from pathlib import Path

import pandas as pd
import pytest

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.models import ImportErrorRecord, ImportInputs
from trade_entity_graph.importers.pipeline import _error_row_count, run_import


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


def test_run_import_records_invalid_relationship_numeric_and_keeps_entities(
    tmp_path, monkeypatch
) -> None:
    entities_path = tmp_path / "entities.csv"
    relationships_path = tmp_path / "relationships.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {
            "canonical_name": ["ACME TRADING", "BETA FACTORY"],
            "original_name": ["Acme Trading Ltd", "Beta Factory Inc"],
        }
    ).to_csv(entities_path, index=False)
    pd.DataFrame(
        {
            "from_entity_name": ["ACME TRADING"],
            "to_entity_name": ["BETA FACTORY"],
            "candidate_relation_type": ["trading_partner_candidate"],
            "confidence_score": ["0.8"],
            "order_count": ["2"],
            "total_teu": ["not-a-number"],
        }
    ).to_csv(relationships_path, index=False)

    result = run_import(
        ImportInputs(
            entities_path=entities_path,
            relationships_path=relationships_path,
            imported_by="tester",
        ),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        claim_count = connection.execute("SELECT COUNT(*) FROM relationship_claim").fetchone()[0]
        error = connection.execute(
            """
            SELECT file_role, error_type, severity, normalized_field
            FROM import_error
            WHERE run_id = ?
            """,
            (result.run_id,),
        ).fetchone()
        batch = connection.execute(
            """
            SELECT success_rows, error_rows, warning_rows
            FROM import_batch
            WHERE run_id = ?
            """,
            (result.run_id,),
        ).fetchone()

    assert entity_count == 2
    assert claim_count == 0
    assert dict(error) == {
        "file_role": "relationships",
        "error_type": "invalid_numeric_value",
        "severity": "blocking",
        "normalized_field": "total_teu",
    }
    assert batch["success_rows"] == 2
    assert batch["error_rows"] == 1
    assert batch["warning_rows"] == 0
    assert result.error_count == 1


def test_run_import_records_errors_and_keeps_valid_rows(tmp_path, monkeypatch) -> None:
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.csv"
    relationships_path = tmp_path / "relationships.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {
            "标准名": ["ACME TRADING", "BETA FACTORY", ""],
            "原始名": ["Acme Trading Ltd", "Beta Factory Inc", "Missing Name Ltd"],
        }
    ).to_csv(entities_path, index=False)
    pd.DataFrame(
        {
            "业务编号": ["SO-1", "SO-2", ""],
            "Booking Customer": ["Acme Trading Ltd", "Acme Trading Ltd", "Acme Trading Ltd"],
            "Shipper": ["Beta Factory Inc", "Beta Factory Inc", "Beta Factory Inc"],
            "Consignee": ["Beta Factory Inc", "Beta Factory Inc", "Beta Factory Inc"],
            "TEU": ["3.5", "not-a-number", "1.0"],
        }
    ).to_csv(orders_path, index=False)
    pd.DataFrame(
        {
            "主体A": ["ACME TRADING", "UNKNOWN CO"],
            "主体B": ["BETA FACTORY", "BETA FACTORY"],
            "关系类型": ["trading_partner_candidate", "trading_partner_candidate"],
        }
    ).to_csv(relationships_path, index=False)

    result = run_import(
        ImportInputs(
            entities_path=entities_path,
            orders_path=orders_path,
            relationships_path=relationships_path,
            imported_by="tester",
        ),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        evidence_count = connection.execute("SELECT COUNT(*) FROM order_evidence").fetchone()[0]
        claim_count = connection.execute("SELECT COUNT(*) FROM relationship_claim").fetchone()[0]
        errors = connection.execute(
            """
            SELECT error_type, severity, source_file_id
            FROM import_error
            WHERE run_id = ?
            ORDER BY file_role, row_number, normalized_field
            """,
            (result.run_id,),
        ).fetchall()
        source_file_ids = {
            row["source_file_id"]
            for row in connection.execute(
                "SELECT source_file_id FROM import_source_file WHERE run_id = ?",
                (result.run_id,),
            ).fetchall()
        }
        batch = connection.execute(
            "SELECT success_rows, error_rows, warning_rows FROM import_batch WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()

    assert evidence_count == 1
    assert claim_count == 1
    assert result.error_count == 4
    assert result.warning_count == 0
    assert batch["success_rows"] == 4
    assert batch["error_rows"] == 4
    assert all(row["source_file_id"] is not None for row in errors)
    assert {item["source_file_id"] for item in result.archived_files} == source_file_ids
    assert {row["source_file_id"] for row in errors}.issubset(source_file_ids)
    assert [row["error_type"] for row in errors] == [
        "missing_required_value",
        "invalid_numeric_value",
        "missing_required_value",
        "unknown_entity_reference",
    ]


def test_error_row_count_deduplicates_warning_source_rows() -> None:
    records = [
        ImportErrorRecord(
            run_id="RUN_WARN",
            error_type="field_mapping_error",
            severity="warning",
            message="duplicate mapping 1",
            file_role="orders",
            source_path="orders.csv",
            sheet_name="orders",
            row_number=2,
        ),
        ImportErrorRecord(
            run_id="RUN_WARN",
            error_type="field_mapping_error",
            severity="warning",
            message="duplicate mapping 2",
            file_role="orders",
            source_path="orders.csv",
            sheet_name="orders",
            row_number=2,
        ),
    ]

    assert len(records) == 2
    assert _error_row_count(records, "warning") == 1

def test_import_batch_error_rows_deduplicates_blocking_relationship_source_rows(
    tmp_path, monkeypatch
) -> None:
    relationships_path = tmp_path / "relationships.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {
            "from_entity_name": ["UNKNOWN SUPPLIER"],
            "to_entity_name": ["UNKNOWN BUYER"],
            "candidate_relation_type": ["trading_partner_candidate"],
        }
    ).to_csv(relationships_path, index=False)

    result = run_import(
        ImportInputs(relationships_path=relationships_path, imported_by="tester"),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        batch = connection.execute(
            "SELECT success_rows, error_rows FROM import_batch WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()

    assert result.error_count == 2
    assert batch["success_rows"] == 0
    assert batch["error_rows"] == 1


def test_import_batch_success_rows_counts_duplicate_valid_entity_source_rows(
    tmp_path, monkeypatch
) -> None:
    entities_path = tmp_path / "entities.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {
            "canonical_name": ["ACME TRADING", "ACME TRADING"],
            "original_name": ["Acme Trading Ltd", "Acme Trading Limited"],
        }
    ).to_csv(entities_path, index=False)

    result = run_import(
        ImportInputs(entities_path=entities_path, imported_by="tester"),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        batch = connection.execute(
            "SELECT success_rows, error_rows FROM import_batch WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()

    assert result.entity_count == 1
    assert batch["success_rows"] == 2
    assert batch["error_rows"] == 0


def test_mapping_only_failures_populate_import_batch_error_summary(tmp_path, monkeypatch) -> None:
    orders_path = tmp_path / "orders.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {
            "customer_name": ["ACME TRADING"],
            "teu": ["1.0"],
        }
    ).to_csv(orders_path, index=False)

    result = run_import(
        ImportInputs(orders_path=orders_path, imported_by="tester"),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        import_error_count = connection.execute(
            "SELECT COUNT(*) FROM import_error WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()[0]
        batch = connection.execute(
            "SELECT error_rows, error_summary FROM import_batch WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()

    assert import_error_count == 1
    assert batch["error_rows"] == 1
    assert batch["error_summary"] is not None
    assert "Missing required field: order_id." in batch["error_summary"]


def test_run_import_records_file_read_error_for_missing_file(tmp_path, monkeypatch) -> None:
    missing_path = tmp_path / "missing_orders.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    with pytest.raises(FileNotFoundError):
        run_import(ImportInputs(orders_path=missing_path), db_path=db_path)

    with get_connection(db_path) as connection:
        batch = connection.execute(
            "SELECT success_rows, error_rows, warning_rows, error_summary FROM import_batch"
        ).fetchone()
        error_rows = connection.execute(
            """
            SELECT run_id, file_role, source_path, error_type, severity, message
            FROM import_error
            """
        ).fetchall()

    assert batch is not None
    assert batch["success_rows"] == 0
    assert batch["error_rows"] == 1
    assert batch["warning_rows"] == 0
    assert batch["error_summary"] is not None
    assert str(missing_path) in batch["error_summary"] or "missing" in batch[
        "error_summary"
    ].lower()
    assert len(error_rows) == 1
    error = error_rows[0]
    assert error["run_id"]
    assert error["file_role"] == "orders"
    assert str(missing_path) in error["source_path"]
    assert error["error_type"] == "file_read_error"
    assert error["severity"] == "blocking"
    assert str(missing_path) in error["message"] or "missing" in error["message"].lower()


def test_run_import_preserves_success_rows_when_later_file_read_fails(
    tmp_path, monkeypatch
) -> None:
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.txt"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {
            "canonical_name": ["ACME TRADING"],
            "original_name": ["Acme Trading Ltd"],
        }
    ).to_csv(entities_path, index=False)
    orders_path.write_text("unsupported file content", encoding="utf-8")

    with pytest.raises(ValueError):
        run_import(
            ImportInputs(entities_path=entities_path, orders_path=orders_path),
            db_path=db_path,
        )

    with get_connection(db_path) as connection:
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        batch = connection.execute(
            "SELECT success_rows, error_rows, warning_rows FROM import_batch"
        ).fetchone()
        errors = connection.execute(
            """
            SELECT file_role, error_type, severity
            FROM import_error
            """
        ).fetchall()

    assert entity_count == 1
    assert batch["success_rows"] == 1
    assert batch["error_rows"] == 1
    assert batch["warning_rows"] == 0
    assert len(errors) == 1
    assert errors[0]["file_role"] == "orders"
    assert errors[0]["error_type"] == "file_read_error"
    assert errors[0]["severity"] == "blocking"
