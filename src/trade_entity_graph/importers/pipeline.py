"""M2 import pipeline orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from trade_entity_graph.config import get_settings
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.batch_loader import create_import_batch, finish_import_batch
from trade_entity_graph.importers.entity_loader import load_entities
from trade_entity_graph.importers.evidence_loader import load_order_evidence
from trade_entity_graph.importers.excel_importer import read_tabular_rows
from trade_entity_graph.importers.field_mapping import resolve_rows_for_role
from trade_entity_graph.importers.import_error_loader import write_import_errors
from trade_entity_graph.importers.models import ImportErrorRecord, ImportInputs, ImportRunResult
from trade_entity_graph.importers.relationship_loader import load_relationship_claims
from trade_entity_graph.importers.source_archive import archive_source_files


def _primary_source(inputs: ImportInputs) -> Path:
    for path in (inputs.orders_path, inputs.entities_path, inputs.relationships_path):
        if path is not None:
            return Path(path)
    raise ValueError("请至少提供一个导入文件路径")


def _input_sources(inputs: ImportInputs) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    if inputs.entities_path is not None:
        sources.append(("entities", Path(inputs.entities_path)))
    if inputs.orders_path is not None:
        sources.append(("orders", Path(inputs.orders_path)))
    if inputs.relationships_path is not None:
        sources.append(("relationships", Path(inputs.relationships_path)))
    return sources


def _quality_summary(import_errors: list[ImportErrorRecord]) -> dict[str, object]:
    counts_by_type: dict[str, int] = {}
    for record in import_errors:
        counts_by_type[record.error_type] = counts_by_type.get(record.error_type, 0) + 1
    return {
        "blocking_error_count": sum(
            1 for record in import_errors if record.severity == "blocking"
        ),
        "warning_count": sum(1 for record in import_errors if record.severity == "warning"),
        "error_count_by_type": dict(sorted(counts_by_type.items())),
    }


def _error_row_count(import_errors: list[ImportErrorRecord], severity: str) -> int:
    row_error_keys: set[tuple[str | None, str | None, str | None, int]] = set()
    non_row_error_count = 0
    for record in import_errors:
        if record.severity != severity:
            continue
        if record.row_number is None:
            non_row_error_count += 1
            continue
        row_error_keys.add(
            (record.file_role, record.source_path, record.sheet_name, record.row_number)
        )
    return len(row_error_keys) + non_row_error_count


def _enrich_error_source_file_ids(
    import_errors: list[ImportErrorRecord],
    source_file_ids_by_role: dict[str, str],
) -> list[ImportErrorRecord]:
    return [
        replace(record, source_file_id=source_file_ids_by_role.get(record.file_role))
        if record.source_file_id is None and record.file_role in source_file_ids_by_role
        else record
        for record in import_errors
    ]


def _error_summary(
    skipped_rows: list[str],
    import_errors: list[ImportErrorRecord],
) -> str | None:
    if skipped_rows:
        return "; ".join(skipped_rows)
    if import_errors:
        return "; ".join(record.message for record in import_errors)
    return None


def _same_path(left: Path, right: Path) -> bool:
    if str(left) == str(right):
        return True
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _source_from_exception(
    sources: list[tuple[str, Path]],
    exc: BaseException,
) -> tuple[str | None, Path | None]:
    exception_paths = [
        Path(value)
        for value in (getattr(exc, "filename", None), getattr(exc, "filename2", None))
        if value
    ]
    for role, source_path in sources:
        if any(_same_path(source_path, exception_path) for exception_path in exception_paths):
            return role, source_path
    for role, source_path in sources:
        if not source_path.exists():
            return role, source_path
    return sources[0] if sources else (None, None)


def _file_failure_message(
    exc: BaseException,
    *,
    role: str | None,
    path: Path | None,
) -> str:
    role_text = f"{role} " if role else ""
    path_text = f" at {path}" if path is not None else ""
    exc_text = str(exc) or exc.__class__.__name__
    return f"Failed to read {role_text}import file{path_text}: {exc_text}"


def _record_file_read_failure(
    connection,
    *,
    run_id: str,
    exc: BaseException,
    role: str | None,
    path: Path | None,
    source_file_id: str | None = None,
    success_rows: int = 0,
    import_errors: list[ImportErrorRecord] | None = None,
) -> None:
    message = _file_failure_message(exc, role=role, path=path)
    failure_error = ImportErrorRecord(
        run_id=run_id,
        source_file_id=source_file_id,
        file_role=role,
        source_path=str(path) if path is not None else None,
        error_type="file_read_error",
        severity="blocking",
        message=message,
    )
    persisted_errors = [*(import_errors or []), failure_error]
    write_import_errors(connection, persisted_errors)
    finish_import_batch(
        connection,
        run_id,
        success_rows=success_rows,
        error_rows=_error_row_count(persisted_errors, "blocking"),
        warning_rows=_error_row_count(persisted_errors, "warning"),
        error_summary=_error_summary([], persisted_errors),
    )


def _read_rows_or_record_file_failure(
    connection,
    *,
    run_id: str,
    role: str,
    path: Path,
    source_file_id: str | None,
    success_rows: int = 0,
    import_errors: list[ImportErrorRecord] | None = None,
):
    try:
        return read_tabular_rows(path)
    except (OSError, ValueError) as exc:
        try:
            _record_file_read_failure(
                connection,
                run_id=run_id,
                exc=exc,
                role=role,
                path=path,
                source_file_id=source_file_id,
                success_rows=success_rows,
                import_errors=import_errors,
            )
        except Exception as persistence_exc:
            exc.add_note(f"Failed to persist import file failure: {persistence_exc}")
        raise


def run_import(inputs: ImportInputs, *, db_path: str | Path | None = None) -> ImportRunResult:
    """Run the M2 import pipeline for the provided input files."""

    settings = get_settings()
    target_db = initialize_database(db_path)
    source_path = _primary_source(inputs)

    with get_connection(target_db) as connection:
        run_id = create_import_batch(
            connection,
            source_file=source_path.name,
            source_path=str(source_path),
            imported_by=inputs.imported_by,
            field_mapping_version=settings.field_mapping_version,
            rule_version=settings.rule_version,
        )
        result = ImportRunResult(run_id=run_id)
        input_sources = _input_sources(inputs)
        try:
            result.archived_files = archive_source_files(
                connection,
                run_id=run_id,
                sources=input_sources,
            )
        except OSError as exc:
            role, path = _source_from_exception(input_sources, exc)
            try:
                _record_file_read_failure(
                    connection,
                    run_id=run_id,
                    exc=exc,
                    role=role,
                    path=path,
                )
            except Exception as persistence_exc:
                exc.add_note(f"Failed to persist import file failure: {persistence_exc}")
            raise
        source_file_ids_by_role = {
            str(item["source_role"]): str(item["source_file_id"])
            for item in result.archived_files
        }
        import_errors: list[ImportErrorRecord] = []
        success_rows = 0

        if inputs.entities_path is not None:
            entity_rows, mapping_errors = resolve_rows_for_role(
                _read_rows_or_record_file_failure(
                    connection,
                    run_id=run_id,
                    role="entities",
                    path=Path(inputs.entities_path),
                    source_file_id=source_file_ids_by_role.get("entities"),
                    success_rows=success_rows,
                    import_errors=_enrich_error_source_file_ids(
                        import_errors, source_file_ids_by_role
                    ),
                ),
                role="entities",
                run_id=run_id,
            )
            import_errors.extend(mapping_errors)
            entity_result = load_entities(
                connection,
                entity_rows,
                run_id=run_id,
                source="entity_cleaning",
            )
            result.entity_count = entity_result.entity_count
            result.alias_count = entity_result.alias_count
            result.skipped_rows.extend(entity_result.skipped_rows)
            import_errors.extend(entity_result.import_errors)
            success_rows += entity_result.success_rows

        if inputs.orders_path is not None:
            order_rows, mapping_errors = resolve_rows_for_role(
                _read_rows_or_record_file_failure(
                    connection,
                    run_id=run_id,
                    role="orders",
                    path=Path(inputs.orders_path),
                    source_file_id=source_file_ids_by_role.get("orders"),
                    success_rows=success_rows,
                    import_errors=_enrich_error_source_file_ids(
                        import_errors, source_file_ids_by_role
                    ),
                ),
                role="orders",
                run_id=run_id,
            )
            import_errors.extend(mapping_errors)
            evidence_result = load_order_evidence(
                connection,
                order_rows,
                run_id=run_id,
            )
            result.evidence_count = evidence_result.evidence_count
            result.skipped_rows.extend(evidence_result.skipped_rows)
            import_errors.extend(evidence_result.import_errors)
            success_rows += evidence_result.success_rows

        if inputs.relationships_path is not None:
            relationship_rows, mapping_errors = resolve_rows_for_role(
                _read_rows_or_record_file_failure(
                    connection,
                    run_id=run_id,
                    role="relationships",
                    path=Path(inputs.relationships_path),
                    source_file_id=source_file_ids_by_role.get("relationships"),
                    success_rows=success_rows,
                    import_errors=_enrich_error_source_file_ids(
                        import_errors, source_file_ids_by_role
                    ),
                ),
                role="relationships",
                run_id=run_id,
            )
            import_errors.extend(mapping_errors)
            claim_result = load_relationship_claims(
                connection,
                relationship_rows,
                run_id=run_id,
            )
            result.claim_count = claim_result.claim_count
            result.skipped_rows.extend(claim_result.skipped_rows)
            import_errors.extend(claim_result.import_errors)
            success_rows += claim_result.success_rows

        import_errors = _enrich_error_source_file_ids(import_errors, source_file_ids_by_role)
        write_import_errors(connection, import_errors)
        result.import_errors = [record.as_dict() for record in import_errors]
        result.error_count = sum(1 for record in import_errors if record.severity == "blocking")
        result.warning_count = sum(1 for record in import_errors if record.severity == "warning")
        result.quality_summary = _quality_summary(import_errors)

        finish_import_batch(
            connection,
            run_id,
            success_rows=success_rows,
            error_rows=_error_row_count(import_errors, "blocking"),
            warning_rows=_error_row_count(import_errors, "warning"),
            error_summary=_error_summary(result.skipped_rows, import_errors),
        )
        return result
