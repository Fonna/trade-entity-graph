from pathlib import Path

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.import_quality_service import (
    ERROR_EXPORT_COLUMNS,
    export_import_errors,
    get_import_batch_detail,
    get_import_quality_report,
    list_import_batches,
    list_import_errors,
    render_import_errors_csv,
)


def _seed_import_quality_fixture(db_path: Path) -> None:
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (
                run_id,
                source_file,
                imported_by,
                success_rows,
                error_rows,
                warning_rows
            )
            VALUES ('RUN_QA', 'orders.csv', 'tester', 3, 1, 1)
            """
        )
        connection.execute(
            """
            INSERT INTO import_source_file (
                source_file_id,
                run_id,
                source_role,
                original_path,
                archived_path,
                file_name,
                file_size_bytes,
                sha256
            )
            VALUES (
                'SRC_QA',
                'RUN_QA',
                'orders',
                'orders.csv',
                'archive/orders.csv',
                'orders.csv',
                128,
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name)
            VALUES ('ENT_A', 'ACME'), ('ENT_B', 'BETA')
            """
        )
        connection.execute(
            """
            INSERT INTO order_evidence (evidence_id, order_id, run_id)
            VALUES ('EVD_QA', 'SO-1', 'RUN_QA')
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id,
                from_entity_id,
                to_entity_id,
                candidate_relation_type,
                run_id
            )
            VALUES ('CLM_QA', 'ENT_A', 'ENT_B', 'trading_partner_candidate', 'RUN_QA')
            """
        )
        connection.execute(
            """
            INSERT INTO import_error (
                error_id,
                run_id,
                file_role,
                source_path,
                sheet_name,
                row_number,
                column_name,
                normalized_field,
                raw_value,
                error_type,
                severity,
                message
            )
            VALUES
                (
                    'IER_BLOCK',
                    'RUN_QA',
                    'orders',
                    'orders.csv',
                    'orders',
                    3,
                    'TEU',
                    'teu',
                    'abc',
                    'invalid_numeric_value',
                    'blocking',
                    'TEU 必须是数字'
                ),
                (
                    'IER_WARN',
                    'RUN_QA',
                    'entities',
                    'entities.csv',
                    'entities',
                    NULL,
                    '企业标准名',
                    'canonical_name',
                    '企业标准名',
                    'field_mapping_error',
                    'warning',
                    '重复映射'
                )
            """
        )
        connection.commit()


def _seed_many_import_errors(db_path: Path, count: int = 1005) -> None:
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (
                run_id,
                source_file,
                imported_by,
                success_rows,
                error_rows,
                warning_rows
            )
            VALUES ('RUN_MANY', 'orders.csv', 'tester', 0, ?, 0)
            """,
            (count,),
        )
        connection.executemany(
            """
            INSERT INTO import_error (
                error_id,
                run_id,
                file_role,
                source_path,
                sheet_name,
                row_number,
                column_name,
                normalized_field,
                raw_value,
                error_type,
                severity,
                message
            )
            VALUES (?, 'RUN_MANY', 'orders', 'orders.csv', 'orders', ?, 'TEU', 'teu', 'abc',
                    'invalid_numeric_value', 'blocking', 'TEU must be numeric')
            """,
            [(f"IER_MANY_{index:04d}", index) for index in range(1, count + 1)],
        )
        connection.commit()


def test_import_quality_service_reports_counts_and_exports(tmp_path: Path) -> None:
    db_path = tmp_path / "quality.db"
    output_path = tmp_path / "errors.csv"
    _seed_import_quality_fixture(db_path)

    batches = list_import_batches(db_path=db_path)
    detail = get_import_batch_detail("RUN_QA", db_path=db_path)
    errors = list_import_errors("RUN_QA", severity="blocking", db_path=db_path)
    report = get_import_quality_report("RUN_QA", db_path=db_path)
    export = export_import_errors("RUN_QA", output_path=output_path, db_path=db_path)

    assert batches["items"][0]["blocking_error_count"] == 1
    assert detail["counts"]["order_evidence"] == 1
    assert detail["quality_summary"]["warning_count"] == 1
    assert errors["items"][0]["error_type"] == "invalid_numeric_value"
    assert report["quality_summary"]["error_count_by_type"] == {
        "field_mapping_error": 1,
        "invalid_numeric_value": 1,
    }
    assert export["row_count"] == 2
    assert "invalid_numeric_value" in output_path.read_text(encoding="utf-8")


def test_import_quality_report_and_export_include_all_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "quality.db"
    output_path = tmp_path / "many_errors.csv"
    _seed_many_import_errors(db_path)

    report = get_import_quality_report("RUN_MANY", db_path=db_path)
    export = export_import_errors("RUN_MANY", output_path=output_path, db_path=db_path)

    assert len(report["errors"]) == 1005
    assert export["row_count"] == 1005


def test_render_import_errors_csv_returns_utf8_sig_bytes_with_export_columns(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "quality.db"
    _seed_import_quality_fixture(db_path)

    content = render_import_errors_csv("RUN_QA", db_path=db_path)

    assert content.startswith(b"\xef\xbb\xbf")
    text = content.decode("utf-8-sig")
    assert text.splitlines()[0] == ",".join(ERROR_EXPORT_COLUMNS)
    assert "invalid_numeric_value" in text


def test_export_import_errors_default_path_sanitizes_run_id(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "quality.db"
    unsafe_run_id = "../evil/run"
    monkeypatch.chdir(tmp_path)
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES (?, 'orders.csv', 'tester')
            """,
            (unsafe_run_id,),
        )
        connection.execute(
            """
            INSERT INTO import_error (
                error_id, run_id, file_role, source_path, sheet_name, row_number,
                normalized_field, raw_value, error_type, severity, message
            )
            VALUES (
                'IER_UNSAFE', ?, 'orders', 'orders.csv',
                'orders', 3, 'teu', 'abc', 'invalid_numeric_value', 'blocking',
                'TEU must be numeric'
            )
            """,
            (unsafe_run_id,),
        )
        connection.commit()

    export = export_import_errors(unsafe_run_id, db_path=db_path)

    export_path = Path(export["path"]).resolve()
    exports_dir = (tmp_path / "data" / "exports").resolve()
    assert export_path.parent == exports_dir
    assert ".." not in export_path.name
    assert "/" not in export_path.name
    assert "\\" not in export_path.name


def test_list_import_errors_rejects_unknown_batch(tmp_path: Path) -> None:
    db_path = tmp_path / "quality.db"
    initialize_database(db_path)

    try:
        list_import_errors("NO_SUCH", db_path=db_path)
    except ValueError as exc:
        assert "Unknown import batch: NO_SUCH" in str(exc)
    else:
        raise AssertionError("list_import_errors should reject unknown import batches")
