"""Entity API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from trade_entity_graph.services.entity_service import get_entity_detail, search_entities
from trade_entity_graph.services.graph_service import get_ego_graph
from trade_entity_graph.services.relationship_service import list_relationship_claims_for_entity

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/search")
def search_entities_endpoint(q: str) -> list[dict[str, object]]:
    return search_entities(q)


@router.get("/{entity_id}")
def get_entity_endpoint(entity_id: str) -> dict[str, object]:
    detail = get_entity_detail(entity_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="未找到企业")
    return detail


@router.get("/{entity_id}/neighbors")
def get_neighbors_endpoint(entity_id: str) -> dict[str, object]:
    graph = get_ego_graph(entity_id)
    claims = list_relationship_claims_for_entity(entity_id)
    return {"graph": graph, "claims": claims}


@router.get("/{entity_id}/ego-graph")
def get_ego_graph_endpoint(
    entity_id: str,
    depth: int = Query(1, ge=1, le=2),
    max_nodes: int = Query(50, ge=1, le=200),
    include_rejected: bool = False,
) -> dict[str, object]:
    return get_ego_graph(
        entity_id,
        depth=depth,
        max_nodes=max_nodes,
        include_rejected=include_rejected,
    )
