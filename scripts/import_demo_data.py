# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.entity_loader import find_entity_id_by_name
from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    generate_order_role_edges,
)
from trade_entity_graph.utils.ids import new_id

DEFAULT_DEMO_DIR = PROJECT_ROOT / "data" / "demo"


def _load_supplemental_candidates(
    candidates_path: Path,
    *,
    db_path: str | Path,
    run_id: str,
) -> int:
    if not candidates_path.exists():
        return 0

    frame = pd.read_csv(candidates_path)
    inserted = 0
    with get_connection(db_path) as connection:
        for record in frame.to_dict(orient="records"):
            from_entity_id = find_entity_id_by_name(connection, record["from_canonical_name"])
            to_entity_id = find_entity_id_by_name(connection, record["to_canonical_name"])
            if not from_entity_id or not to_entity_id:
                raise ValueError(
                    "Unknown supplemental candidate endpoint: "
                    f"{record['from_canonical_name']} -> {record['to_canonical_name']}"
                )
            connection.execute(
                """
                INSERT INTO relationship_claim (
                    claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                    relation_status, confidence_level, confidence_score, order_count,
                    total_teu, recommendation_reason, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("CLM"),
                    from_entity_id,
                    to_entity_id,
                    record["candidate_relation_type"],
                    "candidate",
                    record["confidence_level"],
                    float(record["confidence_score"]),
                    int(record["order_count"]),
                    float(record["total_teu"]),
                    record["recommendation_reason"],
                    run_id,
                ),
            )
            inserted += 1
        connection.commit()
    return inserted


def import_demo_data(
    *,
    output_dir: str | Path = DEFAULT_DEMO_DIR,
    db_path: str | Path | None = None,
    imported_by: str = "demo_import",
) -> dict[str, Any]:
    demo_dir = Path(output_dir)
    target_db = initialize_database(db_path)
    entities_path = demo_dir / "demo_entities.csv"
    orders_path = demo_dir / "demo_orders.csv"
    candidates_path = demo_dir / "demo_relationship_candidates.csv"

    result = run_import(
        ImportInputs(
            entities_path=entities_path,
            orders_path=orders_path,
            imported_by=imported_by,
        ),
        db_path=target_db,
    )
    edge_result = generate_order_role_edges(db_path=target_db, run_id=result.run_id)
    claim_result = aggregate_relationship_claims(db_path=target_db, run_id=result.run_id)
    supplemental_count = _load_supplemental_candidates(
        candidates_path,
        db_path=target_db,
        run_id=result.run_id,
    )
    return {
        "run_id": result.run_id,
        "entity_count": result.entity_count,
        "alias_count": result.alias_count,
        "evidence_count": result.evidence_count,
        "edge_count": edge_result["edge_count"],
        "skipped_edge_count": edge_result["skipped_count"],
        "claim_count": claim_result["claim_count"],
        "supplemental_candidate_count": supplemental_count,
        "db_path": str(target_db),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import M8 demo data into SQLite.")
    parser.add_argument("--demo-dir", default=str(DEFAULT_DEMO_DIR))
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()
    result = import_demo_data(output_dir=args.demo_dir, db_path=args.db_path)
    print(
        "Imported demo data: "
        f"run_id={result['run_id']}, "
        f"entities={result['entity_count']}, "
        f"evidence={result['evidence_count']}, "
        f"edges={result['edge_count']}, "
        f"claims={result['claim_count'] + result['supplemental_candidate_count']}"
    )


if __name__ == "__main__":
    main()
