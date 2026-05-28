"""M2 import pipeline orchestration."""

from __future__ import annotations

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
        result.archived_files = archive_source_files(
            connection,
            run_id=run_id,
            sources=_input_sources(inputs),
        )
        import_errors: list[ImportErrorRecord] = []

        if inputs.entities_path is not None:
            entity_rows, mapping_errors = resolve_rows_for_role(
                read_tabular_rows(inputs.entities_path),
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

        if inputs.orders_path is not None:
            order_rows, mapping_errors = resolve_rows_for_role(
                read_tabular_rows(inputs.orders_path),
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

        if inputs.relationships_path is not None:
            relationship_rows, mapping_errors = resolve_rows_for_role(
                read_tabular_rows(inputs.relationships_path),
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

        write_import_errors(connection, import_errors)
        result.import_errors = [record.as_dict() for record in import_errors]
        result.error_count = sum(1 for record in import_errors if record.severity == "blocking")
        result.warning_count = sum(1 for record in import_errors if record.severity == "warning")
        result.quality_summary = _quality_summary(import_errors)

        finish_import_batch(
            connection,
            run_id,
            success_rows=result.entity_count + result.evidence_count + result.claim_count,
            error_rows=result.error_count,
            warning_rows=result.warning_count,
            error_summary="; ".join(result.skipped_rows) if result.skipped_rows else None,
        )
        return result
