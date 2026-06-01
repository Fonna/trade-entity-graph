"""Import API router."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services import import_quality_service as _import_quality_service
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
from trade_entity_graph.services.import_quality_service import (
    find_duplicate_import,
    get_import_batch_detail,
    get_import_quality_report,
    import_errors_export_filename,
    list_import_batches,
    list_import_errors,
    render_import_errors_csv,
)
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    generate_order_role_edges,
)

router = APIRouter(prefix="/imports", tags=["imports"])

# Preserve the legacy router attribute for downstream monkeypatches; the endpoint
# renders CSV in memory via render_import_errors_csv instead of calling it.
export_import_errors = _import_quality_service.export_import_errors


class ImportRunRequest(BaseModel):
    orders_path: str | None = None
    entities_path: str | None = None
    relationships_path: str | None = None
    confirmed_relationships_path: str | None = None
    imported_by: str = "local_user"
    generate_edges: bool = True
    aggregate_claims: bool = True


def _not_found_from_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _import_failure_detail(exc: Exception, inputs: ImportInputs) -> str:
    paths = [
        str(path)
        for path in (
            inputs.orders_path,
            inputs.entities_path,
            inputs.relationships_path,
            inputs.confirmed_relationships_path,
        )
        if path is not None
    ]
    path_text = f" for {', '.join(paths)}" if paths else ""
    exc_text = str(exc) or exc.__class__.__name__
    return f"Import file failure{path_text}: {exc_text}"


def _input_sources(inputs: ImportInputs) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    if inputs.entities_path is not None:
        sources.append(("entities", Path(inputs.entities_path)))
    if inputs.orders_path is not None:
        sources.append(("orders", Path(inputs.orders_path)))
    if inputs.relationships_path is not None:
        sources.append(("relationships", Path(inputs.relationships_path)))
    if inputs.confirmed_relationships_path is not None:
        sources.append(("confirmed_relationships", Path(inputs.confirmed_relationships_path)))
    return sources


def _duplicate_import_payload(inputs: ImportInputs) -> dict[str, object]:
    duplicate_import_match = find_duplicate_import(_input_sources(inputs))
    return {
        "duplicate_import_warning": duplicate_import_match is not None,
        "duplicate_import_match": duplicate_import_match,
    }


@router.get("")
def list_import_batches_endpoint(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = None,
) -> dict[str, object]:
    return list_import_batches(limit=limit, offset=offset, status=status)


@router.get("/{run_id}")
def get_import_batch_endpoint(run_id: str) -> dict[str, object]:
    try:
        return get_import_batch_detail(run_id)
    except ValueError as exc:
        raise _not_found_from_value_error(exc) from exc


@router.get("/{run_id}/errors")
def list_import_errors_endpoint(
    run_id: str,
    severity: str | None = None,
    error_type: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, object]:
    try:
        return list_import_errors(
            run_id,
            severity=severity,
            error_type=error_type,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise _not_found_from_value_error(exc) from exc


@router.get("/{run_id}/errors/export")
def export_import_errors_endpoint(run_id: str) -> Response:
    try:
        content = render_import_errors_csv(run_id)
    except ValueError as exc:
        raise _not_found_from_value_error(exc) from exc

    filename = import_errors_export_filename(run_id)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{run_id}/quality-report")
def get_import_quality_report_endpoint(run_id: str) -> dict[str, object]:
    try:
        return get_import_quality_report(run_id)
    except ValueError as exc:
        raise _not_found_from_value_error(exc) from exc


@router.post("/duplicate-check")
def duplicate_import_check_endpoint(request: ImportRunRequest) -> dict[str, object]:
    inputs = ImportInputs(
        orders_path=Path(request.orders_path) if request.orders_path else None,
        entities_path=Path(request.entities_path) if request.entities_path else None,
        relationships_path=(
            Path(request.relationships_path) if request.relationships_path else None
        ),
        confirmed_relationships_path=(
            Path(request.confirmed_relationships_path)
            if request.confirmed_relationships_path
            else None
        ),
        imported_by=request.imported_by,
    )
    return _duplicate_import_payload(inputs)


@router.post("/run")
def run_import_endpoint(request: ImportRunRequest) -> dict[str, object]:
    inputs = ImportInputs(
        orders_path=Path(request.orders_path) if request.orders_path else None,
        entities_path=Path(request.entities_path) if request.entities_path else None,
        relationships_path=(
            Path(request.relationships_path) if request.relationships_path else None
        ),
        confirmed_relationships_path=(
            Path(request.confirmed_relationships_path)
            if request.confirmed_relationships_path
            else None
        ),
        imported_by=request.imported_by,
    )
    try:
        duplicate_import = _duplicate_import_payload(inputs)
        result = run_import(inputs)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=_import_failure_detail(exc, inputs)
        ) from exc
    edge_count = 0
    claim_count = result.claim_count
    history_reuse = {"history_matched": 0, "history_conflict": 0, "unchanged": 0}
    if request.generate_edges:
        edge_count = generate_order_role_edges(run_id=result.run_id)["edge_count"]
    if request.aggregate_claims and edge_count > 0:
        claim_count = aggregate_relationship_claims(run_id=result.run_id)["claim_count"]
        history_reuse = apply_history_reuse_to_claims(run_id=result.run_id)
    elif result.claim_count > 0:
        history_reuse = apply_history_reuse_to_claims(run_id=result.run_id)
    return {
        "run_id": result.run_id,
        "entity_count": result.entity_count,
        "alias_count": result.alias_count,
        "evidence_count": result.evidence_count,
        "edge_count": edge_count,
        "claim_count": claim_count,
        "curated_relationship_count": getattr(result, "curated_relationship_count", 0),
        "history_reuse": history_reuse,
        "skipped_rows": result.skipped_rows,
        "archived_files": result.archived_files,
        "error_count": getattr(result, "error_count", 0),
        "warning_count": getattr(result, "warning_count", 0),
        "import_errors": getattr(result, "import_errors", []),
        "quality_summary": getattr(result, "quality_summary", {}),
        **duplicate_import,
    }
