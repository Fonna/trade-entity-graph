"""Review queue API router."""

from __future__ import annotations

from fastapi import APIRouter

from trade_entity_graph.services.review_queue_service import list_review_queue

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _split_csv(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(part.strip() for part in value.split(",") if part.strip())


@router.get("/queue")
def get_review_queue_endpoint(
    status: str | None = None,
    run_id: str | None = None,
    q: str | None = None,
    confidence_level: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, object]:
    return list_review_queue(
        statuses=_split_csv(status),
        run_id=run_id,
        keyword=q,
        confidence_levels=_split_csv(confidence_level),
        limit=limit,
        offset=offset,
    )
