"""Relationship API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from trade_entity_graph.services.relationship_service import (
    get_relationship_detail,
    get_relationship_evidence,
)
from trade_entity_graph.services.review_service import (
    create_manual_relationship,
    decide_relationship,
)

router = APIRouter(prefix="/relationships", tags=["relationships"])


class DecisionRequest(BaseModel):
    action_type: str
    relation_type: str
    reason: str
    operator: str


class ManualRelationshipRequest(BaseModel):
    from_entity_id: str
    to_entity_id: str
    relation_type: str
    reason: str
    operator: str


@router.get("/{relationship_id}")
def get_relationship_endpoint(relationship_id: str) -> dict[str, object]:
    detail = get_relationship_detail(relationship_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    return detail


@router.get("/{relationship_id}/evidence")
def get_relationship_evidence_endpoint(relationship_id: str) -> list[dict[str, object]]:
    return get_relationship_evidence(relationship_id)


@router.post("/{relationship_id}/decision")
def decide_relationship_endpoint(
    relationship_id: str, request: DecisionRequest
) -> dict[str, object]:
    return decide_relationship(
        relationship_id,
        action_type=request.action_type,
        relation_type=request.relation_type,
        reason=request.reason,
        operator=request.operator,
    )


@router.post("/manual")
def create_manual_relationship_endpoint(request: ManualRelationshipRequest) -> dict[str, object]:
    return create_manual_relationship(
        request.from_entity_id,
        request.to_entity_id,
        relation_type=request.relation_type,
        reason=request.reason,
        operator=request.operator,
    )
