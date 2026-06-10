"""M11 graph analytics API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trade_entity_graph.services.opportunity_service import analyze_graph_opportunities

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/opportunities")
def get_graph_opportunities_endpoint(
    include_rejected: bool = False,
    limit: int = Query(20, ge=1, le=100),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
) -> dict[str, object]:
    """Return M11 graph-analysis and opportunity-discovery results."""

    try:
        return analyze_graph_opportunities(
            include_rejected=include_rejected,
            limit=limit,
            min_score=min_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
