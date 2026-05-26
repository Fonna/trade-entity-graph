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
    keep_history_for_claim,
    mark_claim_pending_verify,
    supersede_history_with_claim,
)

router = APIRouter(prefix="/relationships", tags=["relationships"])

HISTORY_ACTIONS = {"keep_history", "mark_pending_verify", "supersede_history"}
ORDINARY_ACTIONS = {"confirm", "modify", "reject"}


def _bad_request_from_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


class DecisionRequest(BaseModel):
    action_type: str
    relation_type: str | None = None
    old_relationship_id: str | None = None
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
    if request.action_type not in HISTORY_ACTIONS | ORDINARY_ACTIONS:
        raise HTTPException(status_code=422, detail="Unsupported action_type")

    try:
        if request.action_type == "keep_history":
            return keep_history_for_claim(
                relationship_id,
                reason=request.reason,
                operator=request.operator,
            )
        if request.action_type == "mark_pending_verify":
            return mark_claim_pending_verify(
                relationship_id,
                reason=request.reason,
                operator=request.operator,
            )
        if request.action_type == "supersede_history":
            if request.relation_type is None:
                raise HTTPException(status_code=422, detail="relation_type is required")
            return supersede_history_with_claim(
                relationship_id,
                old_relationship_id=request.old_relationship_id,
                relation_type=request.relation_type,
                reason=request.reason,
                operator=request.operator,
            )

        if request.relation_type is None:
            raise HTTPException(status_code=422, detail="relation_type is required")
        return decide_relationship(
            relationship_id,
            action_type=request.action_type,
            relation_type=request.relation_type,
            reason=request.reason,
            operator=request.operator,
        )
    except ValueError as exc:
        raise _bad_request_from_value_error(exc) from exc


@router.post("/manual")
def create_manual_relationship_endpoint(request: ManualRelationshipRequest) -> dict[str, object]:
    return create_manual_relationship(
        request.from_entity_id,
        request.to_entity_id,
        relation_type=request.relation_type,
        reason=request.reason,
        operator=request.operator,
    )
