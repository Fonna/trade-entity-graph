"""Import API router."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
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


@router.post("/run")
def run_import_endpoint(request: ImportRunRequest) -> dict[str, object]:
    result = run_import(
        ImportInputs(
            orders_path=Path(request.orders_path) if request.orders_path else None,
            entities_path=Path(request.entities_path) if request.entities_path else None,
            relationships_path=(
                Path(request.relationships_path) if request.relationships_path else None
            ),
            imported_by=request.imported_by,
        )
    )
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
    }
