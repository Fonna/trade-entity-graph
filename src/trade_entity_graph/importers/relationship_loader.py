"""Relationship candidate loading for imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from trade_entity_graph.importers.field_mapping import get_value
from trade_entity_graph.importers.models import ImportSourceRow
from trade_entity_graph.utils.ids import new_id


@dataclass
class RelationshipClaimLoadResult:
    claim_count: int = 0
    skipped_rows: list[str] = field(default_factory=list)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))


def load_relationship_claims(
    connection: sqlite3.Connection,
    rows: list[ImportSourceRow],
    *,
    run_id: str,
) -> RelationshipClaimLoadResult:
    """Load existing candidate relationship rows."""

    result = RelationshipClaimLoadResult()
    for row in rows:
        from_entity_id = get_value(row.values, "from_entity_id")
        to_entity_id = get_value(row.values, "to_entity_id")
        if not from_entity_id or not to_entity_id:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: missing from_entity_id or to_entity_id"
            )
            continue

        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                confidence_level, confidence_score, order_count, total_teu,
                recommendation_reason, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("CLM"),
                str(from_entity_id),
                str(to_entity_id),
                get_value(row.values, "candidate_relation_type", "trading_partner_candidate"),
                get_value(row.values, "confidence_level"),
                _to_float(get_value(row.values, "confidence_score")),
                _to_int(get_value(row.values, "order_count")),
                _to_float(get_value(row.values, "total_teu")) or 0,
                get_value(row.values, "recommendation_reason"),
                run_id,
            ),
        )
        result.claim_count += 1

    connection.commit()
    return result
