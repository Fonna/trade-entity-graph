"""Relationship API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from trade_entity_graph.services.relationship_service import (
    create_external_evidence,
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
DETAIL_NOT_FOUND = "\u672a\u627e\u5230\u5173\u7cfb\u6216\u5019\u9009\u5173\u7cfb"
DETAIL_RELATION_TYPE_REQUIRED = "\u5173\u7cfb\u7c7b\u578b\u4e3a\u5fc5\u586b\u9879"
DETAIL_UNSUPPORTED_ACTION = "\u4e0d\u652f\u6301\u7684\u5ba1\u6838\u52a8\u4f5c"


def _bad_request_from_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


class ExternalEvidenceRequest(BaseModel):
    evidence_type: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    evidence_summary: str
    evidence_date: str | None = None
    confidence_level: str | None = None
    created_by: str | None = None


class DecisionRequest(BaseModel):
    action_type: str
    relation_type: str | None = None
    old_relationship_id: str | None = None
    reason: str
    operator: str
    external_evidence: ExternalEvidenceRequest | None = None


class ManualRelationshipRequest(BaseModel):
    from_entity_id: str
    to_entity_id: str
    relation_type: str
    reason: str
    operator: str
    external_evidence: ExternalEvidenceRequest | None = None


def _external_evidence_payload(
    evidence: ExternalEvidenceRequest | None,
) -> dict[str, object] | None:
    return evidence.model_dump(exclude_none=True) if evidence else None


@router.get("/{relationship_id}")
def get_relationship_endpoint(relationship_id: str) -> dict[str, object]:
    detail = get_relationship_detail(relationship_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=DETAIL_NOT_FOUND)
    return detail


@router.get("/{relationship_id}/evidence")
def get_relationship_evidence_endpoint(relationship_id: str) -> list[dict[str, object]]:
    return get_relationship_evidence(relationship_id)


@router.post("/{relationship_id}/external-evidence")
def create_external_evidence_endpoint(
    relationship_id: str, request: ExternalEvidenceRequest
) -> dict[str, object]:
    try:
        return create_external_evidence(
            relationship_id,
            request.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise _bad_request_from_value_error(exc) from exc


@router.post("/{relationship_id}/decision")
def decide_relationship_endpoint(
    relationship_id: str, request: DecisionRequest
) -> dict[str, object]:
    if request.action_type not in HISTORY_ACTIONS | ORDINARY_ACTIONS:
        raise HTTPException(status_code=422, detail=DETAIL_UNSUPPORTED_ACTION)

    try:
        if request.action_type == "keep_history":
            return keep_history_for_claim(
                relationship_id,
                reason=request.reason,
                operator=request.operator,
                external_evidence=_external_evidence_payload(request.external_evidence),
            )
        if request.action_type == "mark_pending_verify":
            return mark_claim_pending_verify(
                relationship_id,
                reason=request.reason,
                operator=request.operator,
                external_evidence=_external_evidence_payload(request.external_evidence),
            )
        if request.action_type == "supersede_history":
            if request.relation_type is None:
                raise HTTPException(status_code=422, detail=DETAIL_RELATION_TYPE_REQUIRED)
            return supersede_history_with_claim(
                relationship_id,
                old_relationship_id=request.old_relationship_id,
                relation_type=request.relation_type,
                reason=request.reason,
                operator=request.operator,
                external_evidence=_external_evidence_payload(request.external_evidence),
            )

        if request.relation_type is None:
            raise HTTPException(status_code=422, detail=DETAIL_RELATION_TYPE_REQUIRED)
        return decide_relationship(
            relationship_id,
            action_type=request.action_type,
            relation_type=request.relation_type,
            reason=request.reason,
            operator=request.operator,
            external_evidence=_external_evidence_payload(request.external_evidence),
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
        external_evidence=_external_evidence_payload(request.external_evidence),
    )
