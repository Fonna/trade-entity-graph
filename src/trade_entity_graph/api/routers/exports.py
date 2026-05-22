"""Export API router."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from trade_entity_graph.services.export_service import export_relationship_rows

router = APIRouter(prefix="/exports", tags=["exports"])


class RelationshipExportRequest(BaseModel):
    center_entity_id: str
    include_rejected: bool = False


@router.post("/relationships")
def export_relationships_endpoint(request: RelationshipExportRequest) -> dict[str, object]:
    return {
        "rows": export_relationship_rows(
            request.center_entity_id,
            include_rejected=request.include_rejected,
        )
    }
