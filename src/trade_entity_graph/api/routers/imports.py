"""Import API router."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
from trade_entity_graph.services.import_quality_service import (
    get_import_batch_detail,
    get_import_quality_report,
    list_import_batches,
    list_import_errors,
)
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    generate_order_role_edges,
)

router = APIRouter(prefix="/imports", tags=["imports"])


class ImportRunRequest(BaseModel):
    orders_path: str | None = None
    entities_path: str | None = None
    relationships_path: str | None = None
    imported_by: str = "local_user"
    generate_edges: bool = True
    aggregate_claims: bool = True


def _not_found_from_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _import_failure_detail(exc: Exception, inputs: ImportInputs) -> str:
    paths = [
        str(path)
        for path in (inputs.orders_path, inputs.entities_path, inputs.relationships_path)
        if path is not None
    ]
    path_text = f" for {', '.join(paths)}" if paths else ""
    exc_text = str(exc) or exc.__class__.__name__
    return f"Import file failure{path_text}: {exc_text}"


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


@router.get("/{run_id}/quality-report")
def get_import_quality_report_endpoint(run_id: str) -> dict[str, object]:
    try:
        return get_import_quality_report(run_id)
    except ValueError as exc:
        raise _not_found_from_value_error(exc) from exc


@router.post("/run")
def run_import_endpoint(request: ImportRunRequest) -> dict[str, object]:
    inputs = ImportInputs(
        orders_path=Path(request.orders_path) if request.orders_path else None,
        entities_path=Path(request.entities_path) if request.entities_path else None,
        relationships_path=(
            Path(request.relationships_path) if request.relationships_path else None
        ),
        imported_by=request.imported_by,
    )
    try:
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
        "history_reuse": history_reuse,
        "skipped_rows": result.skipped_rows,
        "archived_files": result.archived_files,
        "error_count": getattr(result, "error_count", 0),
        "warning_count": getattr(result, "warning_count", 0),
        "import_errors": getattr(result, "import_errors", []),
        "quality_summary": getattr(result, "quality_summary", {}),
    }
