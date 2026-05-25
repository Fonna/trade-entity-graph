from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_demo_data import write_demo_data


def test_generate_demo_data_writes_importable_files(tmp_path) -> None:
    output_dir = tmp_path / "demo"

    result = write_demo_data(output_dir)

    entities_path = output_dir / "demo_entities.csv"
    orders_path = output_dir / "demo_orders.csv"
    candidates_path = output_dir / "demo_relationship_candidates.csv"
    readme_path = output_dir / "README.md"

    assert result["entity_count"] == 50
    assert 80 <= result["order_count"] <= 120
    assert result["supplemental_candidate_count"] >= 6
    assert entities_path.exists()
    assert orders_path.exists()
    assert candidates_path.exists()
    assert readme_path.exists()

    entities = pd.read_csv(entities_path)
    orders = pd.read_csv(orders_path)
    candidates = pd.read_csv(candidates_path)

    assert set(
        [
            "canonical_name",
            "original_name",
            "clean_name",
            "alias_name",
            "country",
            "entity_type",
        ]
    ).issubset(entities.columns)
    assert set(
        [
            "order_id",
            "customer_name",
            "shipper_name",
            "consignee_name",
            "notify_name",
            "teu",
            "product_name",
            "function_category",
            "destination_country",
            "destination_port",
            "order_date",
        ]
    ).issubset(orders.columns)
    assert set(
        [
            "from_canonical_name",
            "to_canonical_name",
            "candidate_relation_type",
            "confidence_level",
            "confidence_score",
            "order_count",
            "total_teu",
            "recommendation_reason",
        ]
    ).issubset(candidates.columns)
    assert entities["entity_type"].nunique() >= 7
    assert orders["customer_name"].nunique() >= 10
    assert orders["destination_country"].nunique() >= 8
    assert orders["product_name"].nunique() >= 6
    assert {"SAME AS", "TO ORDER", "YQN LOGISTICS"} & set(orders["notify_name"])
