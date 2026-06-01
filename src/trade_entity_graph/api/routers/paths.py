"""Entity path query API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trade_entity_graph.services.graph_service import find_entity_paths

router = APIRouter(tags=["paths"])


@router.get("/paths")
def find_entity_paths_endpoint(
    from_entity_id: str,
    to_entity_id: str,
    max_depth: int = Query(3, ge=1, le=5),
    max_paths: int = Query(5, ge=1, le=20),
    include_rejected: bool = False,
) -> dict[str, object]:
    try:
        return find_entity_paths(
            from_entity_id,
            to_entity_id,
            max_depth=max_depth,
            max_paths=max_paths,
            include_rejected=include_rejected,
        )
    except ValueError as exc:
        status_code = 404 if "Unknown entity" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
