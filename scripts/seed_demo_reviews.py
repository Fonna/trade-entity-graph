# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.entity_loader import find_entity_id_by_name
from trade_entity_graph.services.review_service import (
    create_manual_relationship,
    decide_relationship,
)

DEMO_OPERATOR = "demo_seed"

CLAIM_DECISIONS = [
    (
        "APEX OUTDOOR USA",
        "DRAGON PEAK MANUFACTURING",
        "confirm",
        "trading_partner",
        "Repeated Apex orders with Dragon Peak factory.",
    ),
    (
        "APEX OUTDOOR USA",
        "SUNRISE PLASTICS NINGBO",
        "confirm",
        "trading_partner",
        "Repeated Apex plastic product lanes.",
    ),
    (
        "NOVA HOME STORES",
        "RIVERSTONE METALWORKS",
        "modify",
        "factory_node",
        "Riverstone acts as Nova metalware production node.",
    ),
    (
        "NOVA HOME STORES",
        "CRESCENT FURNITURE WORKS",
        "modify",
        "factory_node",
        "Crescent supplies Nova furniture lanes.",
    ),
    (
        "ORBIT MARKETPLACE",
        "GREENFIELD ELECTRONICS",
        "confirm",
        "trading_partner",
        "Orbit electronics orders repeat across multiple shipments.",
    ),
    (
        "ORBIT MARKETPLACE",
        "ORBIT ASIA PROCUREMENT",
        "modify",
        "sales_center",
        "Orbit Asia is treated as procurement and sales support center.",
    ),
    (
        "LUMEN BRANDS",
        "LUMEN LATAM IMPORTS",
        "modify",
        "sales_center",
        "Lumen Latam appears as repeated consignee and notify office.",
    ),
    (
        "MERIDIAN SUPPLY CHAIN",
        "TRANSWORLD CARGO SERVICES",
        "reject",
        "rejected_relation",
        "Transworld is a logistics notify party, not a business relationship.",
    ),
    (
        "UNMATCHED LEGACY TRADER",
        "APEX OUTDOOR USA",
        "reject",
        "rejected_relation",
        "Legacy low-confidence record is rejected during demo review.",
    ),
]

MANUAL_RELATIONSHIPS = [
    (
        "APEX GLOBAL HOLDINGS",
        "APEX OUTDOOR USA",
        "same_group",
        "Apex brand owner and US customer are in the same group.",
    ),
    (
        "APEX GLOBAL HOLDINGS",
        "APEX GLOBAL SOURCING HK",
        "subsidiary",
        "Apex HK sourcing entity is a subsidiary of Apex Global.",
    ),
    (
        "NOVA RETAIL GROUP",
        "NOVA HOME STORES",
        "same_group",
        "Nova Home is part of Nova Retail Group.",
    ),
    (
        "NOVA RETAIL GROUP",
        "NOVA SOURCING SHANGHAI",
        "subsidiary",
        "Nova Shanghai is the group sourcing subsidiary.",
    ),
    (
        "ORBIT COMMERCE HOLDINGS",
        "ORBIT ASIA PROCUREMENT",
        "subsidiary",
        "Orbit Asia Procurement supports the Orbit group.",
    ),
    (
        "OCEANBRIDGE LOGISTICS",
        "APEX OUTDOOR USA",
        "logistics_service",
        "Oceanbridge is manually known as Apex logistics provider.",
    ),
    (
        "SKYLINE FREIGHT FORWARDING",
        "NOVA HOME STORES",
        "logistics_service",
        "Skyline is manually known as Nova logistics provider.",
    ),
]


def _claim_id(connection, from_name: str, to_name: str) -> str:
    row = connection.execute(
        """
        SELECT rc.claim_id
        FROM relationship_claim rc
        JOIN entity e1 ON e1.entity_id = rc.from_entity_id
        JOIN entity e2 ON e2.entity_id = rc.to_entity_id
        WHERE e1.canonical_name = ? AND e2.canonical_name = ?
        ORDER BY rc.confidence_score DESC, rc.order_count DESC
        LIMIT 1
        """,
        (from_name, to_name),
    ).fetchone()
    if not row:
        raise ValueError(f"Missing demo claim: {from_name} -> {to_name}")
    return row["claim_id"]


def _entity_id(connection, name: str) -> str:
    entity_id = find_entity_id_by_name(connection, name)
    if not entity_id:
        raise ValueError(f"Missing demo entity: {name}")
    return entity_id


def _already_seeded(db_path: str | Path | None) -> bool:
    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM relationship_decision
            WHERE operator = ?
            """,
            (DEMO_OPERATOR,),
        ).fetchone()
    return int(row["count"]) > 0


def seed_demo_reviews(*, db_path: str | Path | None = None) -> dict[str, Any]:
    if _already_seeded(db_path):
        return {"skipped": True, "created_relationship_count": 0}

    created = 0
    with get_connection(db_path) as connection:
        claim_ids = [
            (_claim_id(connection, source, target), action, relation_type, reason)
            for source, target, action, relation_type, reason in CLAIM_DECISIONS
        ]
        manual_pairs = [
            (_entity_id(connection, source), _entity_id(connection, target), relation_type, reason)
            for source, target, relation_type, reason in MANUAL_RELATIONSHIPS
        ]

    for claim_id, action, relation_type, reason in claim_ids:
        decide_relationship(
            claim_id,
            action_type=action,
            relation_type=relation_type,
            reason=reason,
            operator=DEMO_OPERATOR,
            db_path=db_path,
        )
        created += 1

    for from_entity_id, to_entity_id, relation_type, reason in manual_pairs:
        create_manual_relationship(
            from_entity_id,
            to_entity_id,
            relation_type=relation_type,
            reason=reason,
            operator=DEMO_OPERATOR,
            db_path=db_path,
        )
        created += 1

    return {"skipped": False, "created_relationship_count": created}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed reviewed relationships for M8 demo data.")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()
    result = seed_demo_reviews(db_path=args.db_path)
    if result["skipped"]:
        print("Demo reviews already seeded; no changes made.")
    else:
        print(f"Seeded {result['created_relationship_count']} demo reviewed relationships.")


if __name__ == "__main__":
    main()
