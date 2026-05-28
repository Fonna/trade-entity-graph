from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.import_error_loader import write_import_errors
from trade_entity_graph.importers.models import ImportErrorRecord


def test_write_import_errors_persists_traceability_fields(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_ERR', 'orders.csv', 'tester')
            """
        )
        connection.commit()

        count = write_import_errors(
            connection,
            [
                ImportErrorRecord(
                    run_id="RUN_ERR",
                    file_role="orders",
                    source_path="orders.csv",
                    sheet_name="orders",
                    row_number=3,
                    column_name="TEU",
                    normalized_field="teu",
                    raw_value="abc",
                    error_type="invalid_numeric_value",
                    severity="blocking",
                    message="TEU 必须是数字",
                )
            ],
        )

        row = connection.execute(
            """
            SELECT run_id, file_role, source_path, sheet_name, row_number,
                   column_name, normalized_field, raw_value, error_type, severity, message
            FROM import_error
            """
        ).fetchone()

    assert count == 1
    assert row["run_id"] == "RUN_ERR"
    assert row["file_role"] == "orders"
    assert row["row_number"] == 3
    assert row["normalized_field"] == "teu"
    assert row["raw_value"] == "abc"
    assert row["error_type"] == "invalid_numeric_value"
    assert row["severity"] == "blocking"
    assert row["message"] == "TEU 必须是数字"


def test_import_error_record_as_dict_stringifies_raw_value() -> None:
    record = ImportErrorRecord(
        run_id="RUN_ERR",
        file_role="entities",
        source_path="entities.csv",
        sheet_name="entities",
        row_number=2,
        column_name="标准名",
        normalized_field="canonical_name",
        raw_value=123,
        error_type="missing_required_value",
        severity="blocking",
        message="标准企业名称不能为空",
    )

    assert record.as_dict()["raw_value"] == "123"
    assert record.as_dict()["source_file_id"] is None
