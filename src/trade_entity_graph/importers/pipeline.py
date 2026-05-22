"""M2 import pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from trade_entity_graph.config import get_settings
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.batch_loader import create_import_batch, finish_import_batch
from trade_entity_graph.importers.entity_loader import load_entities
from trade_entity_graph.importers.evidence_loader import load_order_evidence
from trade_entity_graph.importers.excel_importer import read_tabular_rows
from trade_entity_graph.importers.models import ImportInputs, ImportRunResult
from trade_entity_graph.importers.relationship_loader import load_relationship_claims
from trade_entity_graph.importers.source_archive import archive_source_files


def _primary_source(inputs: ImportInputs) -> Path:
    for path in (inputs.orders_path, inputs.entities_path, inputs.relationships_path):
        if path is not None:
            return Path(path)
    raise ValueError("At least one import input path is required")


def _input_sources(inputs: ImportInputs) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    if inputs.entities_path is not None:
        sources.append(("entities", Path(inputs.entities_path)))
    if inputs.orders_path is not None:
        sources.append(("orders", Path(inputs.orders_path)))
    if inputs.relationships_path is not None:
        sources.append(("relationships", Path(inputs.relationships_path)))
    return sources


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

        if inputs.entities_path is not None:
            entity_result = load_entities(
                connection,
                read_tabular_rows(inputs.entities_path),
                run_id=run_id,
                source="entity_cleaning",
            )
            result.entity_count = entity_result.entity_count
            result.alias_count = entity_result.alias_count
            result.skipped_rows.extend(entity_result.skipped_rows)

        if inputs.orders_path is not None:
            evidence_result = load_order_evidence(
                connection,
                read_tabular_rows(inputs.orders_path),
                run_id=run_id,
            )
            result.evidence_count = evidence_result.evidence_count
            result.skipped_rows.extend(evidence_result.skipped_rows)

        if inputs.relationships_path is not None:
            claim_result = load_relationship_claims(
                connection,
                read_tabular_rows(inputs.relationships_path),
                run_id=run_id,
            )
            result.claim_count = claim_result.claim_count
            result.skipped_rows.extend(claim_result.skipped_rows)

        finish_import_batch(
            connection,
            run_id,
            success_rows=result.entity_count + result.evidence_count + result.claim_count,
            error_rows=len(result.skipped_rows),
            error_summary="; ".join(result.skipped_rows) if result.skipped_rows else None,
        )
        return result
