# M8 Demo Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic M8 demo package with about 50 entities, 80-120 orders, supplemental candidates, seeded review outcomes, tests, generated files, and acceptance documentation.

**Architecture:** Keep M8 as demo tooling around the existing MVP services. A generator writes importable CSV files, a demo import script reuses the current import pipeline plus edge and claim services, and a review seed script reuses the current review service. Tests run the whole flow in `tmp_path` and temporary SQLite databases without depending on global `data/` state.

**Tech Stack:** Python 3.12, pandas, SQLite, pytest, ruff, existing `trade_entity_graph` importers/services.

---

## File Structure

- Create `scripts/generate_demo_data.py`: deterministic demo data builder and CLI writer.
- Create `scripts/import_demo_data.py`: demo import adapter that imports entities/orders, generates role edges, aggregates claims, and loads supplemental candidates by canonical names.
- Create `scripts/seed_demo_reviews.py`: idempotent demo review seeder using current review services.
- Create `tests/test_demo_acceptance.py`: M8 generator and end-to-end acceptance tests.
- Create `data/demo/demo_entities.csv`: generated entity source file.
- Create `data/demo/demo_orders.csv`: generated order source file.
- Create `data/demo/demo_relationship_candidates.csv`: generated supplemental candidate file.
- Create `data/demo/README.md`: demo file purpose and regeneration notes.
- Modify `README.md`: add M8 demo commands and update current status.
- Modify `README.en.md`: add M8 demo commands and update current status.
- Modify `docs/task-breakdown.md`: update M8 status, acceptance checklist evidence, and P1 out-of-scope notes.

The scripts live in `scripts/` because current operational entry points are there. Tests import script modules directly by adding the repository root to `sys.path`, matching the existing lightweight script pattern.

## Task 1: Demo Data Generator

**Files:**
- Create: `tests/test_demo_acceptance.py`
- Create: `scripts/generate_demo_data.py`

- [ ] **Step 1: Write the failing generator test**

Create `tests/test_demo_acceptance.py` with:

```python
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
```

- [ ] **Step 2: Run the generator test to verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py::test_generate_demo_data_writes_importable_files -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.generate_demo_data'`.

- [ ] **Step 3: Implement the deterministic generator**

Create `scripts/generate_demo_data.py` with these public functions:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "demo"


def build_entities() -> list[dict[str, str]]:
    """Return deterministic demo entities covering the M8 relationship story."""

    rows = [
        ("APEX GLOBAL HOLDINGS", "Apex Global Holdings Ltd", "APEX GLOBAL HOLDINGS LTD", "Apex Group", "US", "group"),
        ("APEX OUTDOOR USA", "Apex Outdoor USA Inc", "APEX OUTDOOR USA INC", "Apex Outdoor", "US", "customer"),
        ("APEX OUTDOOR EUROPE", "Apex Outdoor Europe GmbH", "APEX OUTDOOR EUROPE GMBH", "Apex Europe", "DE", "sales_center"),
        ("APEX SOURCING SHENZHEN", "Apex Sourcing Shenzhen Co Ltd", "APEX SOURCING SHENZHEN CO LTD", "Apex Shenzhen", "CN", "trader"),
        ("NOVA RETAIL GROUP", "Nova Retail Group LLC", "NOVA RETAIL GROUP LLC", "Nova Retail", "US", "group"),
        ("NOVA HOME STORES", "Nova Home Stores Inc", "NOVA HOME STORES INC", "Nova Home", "US", "customer"),
        ("NOVA EUROPE BUYING", "Nova Europe Buying BV", "NOVA EUROPE BUYING BV", "Nova Europe", "NL", "sales_center"),
        ("ORBIT COMMERCE HOLDINGS", "Orbit Commerce Holdings Ltd", "ORBIT COMMERCE HOLDINGS LTD", "Orbit Group", "GB", "group"),
        ("ORBIT MARKETPLACE", "Orbit Marketplace Inc", "ORBIT MARKETPLACE INC", "Orbit Market", "US", "customer"),
        ("ORBIT CANADA BUYING", "Orbit Canada Buying Ltd", "ORBIT CANADA BUYING LTD", "Orbit Canada", "CA", "buyer"),
        ("LUMEN BRANDS", "Lumen Brands LLC", "LUMEN BRANDS LLC", "Lumen", "US", "customer"),
        ("LUMEN LATAM IMPORTS", "Lumen Latam Imports SA", "LUMEN LATAM IMPORTS SA", "Lumen Latam", "MX", "buyer"),
        ("MERIDIAN SUPPLY CHAIN", "Meridian Supply Chain Ltd", "MERIDIAN SUPPLY CHAIN LTD", "Meridian Supply", "SG", "trader"),
        ("PACIFIC HOME BUYING", "Pacific Home Buying Pty Ltd", "PACIFIC HOME BUYING PTY LTD", "Pacific Home", "AU", "buyer"),
        ("HARBOR WHOLESALE", "Harbor Wholesale Co", "HARBOR WHOLESALE CO", "Harbor Wholesale", "US", "customer"),
        ("SUMMIT DIGITAL RETAIL", "Summit Digital Retail Inc", "SUMMIT DIGITAL RETAIL INC", "Summit Digital", "US", "customer"),
        ("BLUE RIDGE SOURCING", "Blue Ridge Sourcing LLC", "BLUE RIDGE SOURCING LLC", "Blue Ridge", "US", "trader"),
        ("DRAGON PEAK MANUFACTURING", "Dragon Peak Manufacturing Co Ltd", "DRAGON PEAK MANUFACTURING CO LTD", "Dragon Peak", "CN", "factory"),
        ("DRAGON PEAK VIETNAM", "Dragon Peak Vietnam Ltd", "DRAGON PEAK VIETNAM LTD", "Dragon Vietnam", "VN", "factory"),
        ("SUNRISE PLASTICS NINGBO", "Sunrise Plastics Ningbo Co Ltd", "SUNRISE PLASTICS NINGBO CO LTD", "Sunrise Ningbo", "CN", "factory"),
        ("SUNRISE PLASTICS THAILAND", "Sunrise Plastics Thailand Ltd", "SUNRISE PLASTICS THAILAND LTD", "Sunrise Thailand", "TH", "factory"),
        ("RIVERSTONE METALWORKS", "Riverstone Metalworks Co Ltd", "RIVERSTONE METALWORKS CO LTD", "Riverstone", "CN", "factory"),
        ("RIVERSTONE CAMBODIA", "Riverstone Cambodia Ltd", "RIVERSTONE CAMBODIA LTD", "Riverstone KH", "KH", "factory"),
        ("EASTWIND TEXTILES", "Eastwind Textiles Co Ltd", "EASTWIND TEXTILES CO LTD", "Eastwind", "CN", "factory"),
        ("EASTWIND BANGLADESH", "Eastwind Bangladesh Ltd", "EASTWIND BANGLADESH LTD", "Eastwind BD", "BD", "factory"),
        ("GREENFIELD ELECTRONICS", "Greenfield Electronics Co Ltd", "GREENFIELD ELECTRONICS CO LTD", "Greenfield", "CN", "factory"),
        ("GREENFIELD MALAYSIA", "Greenfield Malaysia Sdn Bhd", "GREENFIELD MALAYSIA SDN BHD", "Greenfield MY", "MY", "factory"),
        ("ORIENTAL CERAMICS", "Oriental Ceramics Ltd", "ORIENTAL CERAMICS LTD", "Oriental Ceramics", "CN", "factory"),
        ("ORIENTAL CERAMICS INDONESIA", "Oriental Ceramics Indonesia PT", "ORIENTAL CERAMICS INDONESIA PT", "Oriental ID", "ID", "factory"),
        ("ALPINE TOOLING", "Alpine Tooling Co Ltd", "ALPINE TOOLING CO LTD", "Alpine Tooling", "CN", "factory"),
        ("SILVERLINE PACKAGING", "Silverline Packaging Ltd", "SILVERLINE PACKAGING LTD", "Silverline", "CN", "factory"),
        ("AURORA LIGHTING FACTORY", "Aurora Lighting Factory Ltd", "AURORA LIGHTING FACTORY LTD", "Aurora Lighting", "CN", "factory"),
        ("CRESCENT FURNITURE WORKS", "Crescent Furniture Works Ltd", "CRESCENT FURNITURE WORKS LTD", "Crescent Furniture", "VN", "factory"),
        ("NORTHSTAR DISTRIBUTION", "Northstar Distribution Inc", "NORTHSTAR DISTRIBUTION INC", "Northstar", "US", "buyer"),
        ("MAPLE LEAF IMPORTS", "Maple Leaf Imports Ltd", "MAPLE LEAF IMPORTS LTD", "Maple Leaf", "CA", "buyer"),
        ("IBERIA RETAIL IMPORTS", "Iberia Retail Imports SL", "IBERIA RETAIL IMPORTS SL", "Iberia Imports", "ES", "buyer"),
        ("RHINE HOME IMPORTS", "Rhine Home Imports GmbH", "RHINE HOME IMPORTS GMBH", "Rhine Home", "DE", "buyer"),
        ("SAHARA TRADE HOUSE", "Sahara Trade House LLC", "SAHARA TRADE HOUSE LLC", "Sahara Trade", "AE", "buyer"),
        ("ANDES MARKET SUPPLY", "Andes Market Supply SAC", "ANDES MARKET SUPPLY SAC", "Andes Supply", "PE", "buyer"),
        ("ATLAS MEXICO DISTRIBUTION", "Atlas Mexico Distribution SA", "ATLAS MEXICO DISTRIBUTION SA", "Atlas Mexico", "MX", "buyer"),
        ("CAPE TOWN RETAIL IMPORTS", "Cape Town Retail Imports Pty", "CAPE TOWN RETAIL IMPORTS PTY", "Cape Retail", "ZA", "buyer"),
        ("YQN LOGISTICS", "YQN Logistics Co Ltd", "YQN LOGISTICS CO LTD", "YQN", "CN", "logistics"),
        ("OCEANBRIDGE LOGISTICS", "Oceanbridge Logistics Ltd", "OCEANBRIDGE LOGISTICS LTD", "Oceanbridge", "CN", "logistics"),
        ("SKYLINE FREIGHT FORWARDING", "Skyline Freight Forwarding Ltd", "SKYLINE FREIGHT FORWARDING LTD", "Skyline Freight", "CN", "logistics"),
        ("TRANSWORLD CARGO SERVICES", "Transworld Cargo Services Ltd", "TRANSWORLD CARGO SERVICES LTD", "Transworld Cargo", "SG", "logistics"),
        ("GLOBEWAY SHIPPING", "Globeway Shipping Ltd", "GLOBEWAY SHIPPING LTD", "Globeway", "HK", "logistics"),
        ("APEX GLOBAL SOURCING HK", "Apex Global Sourcing HK Ltd", "APEX GLOBAL SOURCING HK LTD", "Apex HK", "HK", "subsidiary"),
        ("NOVA SOURCING SHANGHAI", "Nova Sourcing Shanghai Co Ltd", "NOVA SOURCING SHANGHAI CO LTD", "Nova Shanghai", "CN", "subsidiary"),
        ("ORBIT ASIA PROCUREMENT", "Orbit Asia Procurement Ltd", "ORBIT ASIA PROCUREMENT LTD", "Orbit Asia", "SG", "subsidiary"),
        ("UNMATCHED LEGACY TRADER", "Unmatched Legacy Trader Ltd", "UNMATCHED LEGACY TRADER LTD", "Legacy Trader", "HK", "unknown"),
    ]
    return [
        {
            "canonical_name": canonical,
            "original_name": original,
            "clean_name": clean,
            "alias_name": alias,
            "country": country,
            "entity_type": entity_type,
        }
        for canonical, original, clean, alias, country, entity_type in rows
    ]


def _expanded_orders() -> list[tuple[str, str, str, str, str, float, str, str, str, str, str, int]]:
    """Return lane templates with repeat counts."""

    return [
        ("APEX OUTDOOR USA", "DRAGON PEAK MANUFACTURING", "NORTHSTAR DISTRIBUTION", "APEX OUTDOOR EUROPE", 4.5, "Outdoor chair", "outdoor furniture", "US", "Los Angeles", "2026-01-05", 8),
        ("APEX OUTDOOR USA", "SUNRISE PLASTICS NINGBO", "MAPLE LEAF IMPORTS", "APEX GLOBAL SOURCING HK", 3.0, "Storage box", "household plastic", "CA", "Vancouver", "2026-01-08", 6),
        ("NOVA HOME STORES", "RIVERSTONE METALWORKS", "NOVA EUROPE BUYING", "NOVA EUROPE BUYING", 2.5, "Kitchen rack", "metal houseware", "NL", "Rotterdam", "2026-01-10", 7),
        ("NOVA HOME STORES", "CRESCENT FURNITURE WORKS", "RHINE HOME IMPORTS", "NOVA SOURCING SHANGHAI", 5.0, "Flat pack table", "furniture", "DE", "Hamburg", "2026-01-12", 5),
        ("ORBIT MARKETPLACE", "GREENFIELD ELECTRONICS", "ORBIT CANADA BUYING", "ORBIT ASIA PROCUREMENT", 2.0, "LED controller", "electronics", "CA", "Prince Rupert", "2026-01-14", 7),
        ("ORBIT MARKETPLACE", "EASTWIND TEXTILES", "IBERIA RETAIL IMPORTS", "ORBIT ASIA PROCUREMENT", 3.5, "Cotton throw", "textile", "ES", "Valencia", "2026-01-16", 5),
        ("LUMEN BRANDS", "AURORA LIGHTING FACTORY", "LUMEN LATAM IMPORTS", "LUMEN LATAM IMPORTS", 2.2, "Pendant lamp", "lighting", "MX", "Manzanillo", "2026-01-18", 6),
        ("MERIDIAN SUPPLY CHAIN", "ORIENTAL CERAMICS", "PACIFIC HOME BUYING", "TRANSWORLD CARGO SERVICES", 4.2, "Ceramic planter", "ceramics", "AU", "Sydney", "2026-01-20", 5),
        ("HARBOR WHOLESALE", "ALPINE TOOLING", "HARBOR WHOLESALE", "SAME AS", 1.8, "Hand tool kit", "tools", "US", "Long Beach", "2026-01-22", 4),
        ("SUMMIT DIGITAL RETAIL", "GREENFIELD MALAYSIA", "SAHARA TRADE HOUSE", "TO ORDER", 2.8, "Smart sensor", "electronics", "AE", "Jebel Ali", "2026-01-24", 4),
        ("BLUE RIDGE SOURCING", "SILVERLINE PACKAGING", "ANDES MARKET SUPPLY", "YQN LOGISTICS", 1.5, "Gift carton", "packaging", "PE", "Callao", "2026-01-26", 3),
        ("APEX SOURCING SHENZHEN", "DRAGON PEAK VIETNAM", "ATLAS MEXICO DISTRIBUTION", "APEX OUTDOOR EUROPE", 3.2, "Camping table", "outdoor furniture", "MX", "Veracruz", "2026-01-28", 4),
        ("NOVA HOME STORES", "SUNRISE PLASTICS THAILAND", "CAPE TOWN RETAIL IMPORTS", "NOVA EUROPE BUYING", 2.6, "Laundry basket", "household plastic", "ZA", "Cape Town", "2026-02-01", 3),
        ("ORBIT MARKETPLACE", "RIVERSTONE CAMBODIA", "MAPLE LEAF IMPORTS", "ORBIT CANADA BUYING", 2.1, "Metal shelf", "metal houseware", "CA", "Montreal", "2026-02-03", 3),
        ("LUMEN BRANDS", "ORIENTAL CERAMICS INDONESIA", "IBERIA RETAIL IMPORTS", "LUMEN LATAM IMPORTS", 1.7, "Table vase", "ceramics", "ES", "Barcelona", "2026-02-05", 3),
        ("MERIDIAN SUPPLY CHAIN", "EASTWIND BANGLADESH", "RHINE HOME IMPORTS", "TRANSWORLD CARGO SERVICES", 2.3, "Bedding set", "textile", "DE", "Bremerhaven", "2026-02-07", 3),
        ("PACIFIC HOME BUYING", "CRESCENT FURNITURE WORKS", "PACIFIC HOME BUYING", "SAME AS", 1.6, "Dining chair", "furniture", "AU", "Melbourne", "2026-02-09", 3),
        ("APEX OUTDOOR USA", "OCEANBRIDGE LOGISTICS", "NORTHSTAR DISTRIBUTION", "APEX GLOBAL SOURCING HK", 1.0, "Freight handling", "logistics service", "US", "Los Angeles", "2026-02-11", 2),
    ]


def build_orders() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sequence = 1
    for template in _expanded_orders():
        (
            customer,
            shipper,
            consignee,
            notify,
            teu,
            product,
            category,
            destination_country,
            destination_port,
            base_date,
            count,
        ) = template
        for offset in range(count):
            rows.append(
                {
                    "order_id": f"DEMO-SO-{sequence:04d}",
                    "customer_name": customer,
                    "shipper_name": shipper,
                    "consignee_name": consignee,
                    "notify_name": notify,
                    "teu": round(teu + (offset % 3) * 0.4, 2),
                    "product_name": product,
                    "function_category": category,
                    "destination_country": destination_country,
                    "destination_port": destination_port,
                    "order_date": base_date,
                }
            )
            sequence += 1
    return rows


def build_supplemental_candidates() -> list[dict[str, Any]]:
    return [
        {
            "from_canonical_name": "APEX GLOBAL HOLDINGS",
            "to_canonical_name": "APEX GLOBAL SOURCING HK",
            "candidate_relation_type": "same_group_candidate",
            "confidence_level": "high",
            "confidence_score": 0.92,
            "order_count": 8,
            "total_teu": 36.0,
            "recommendation_reason": "Shared Apex branding and repeated notify roles",
        },
        {
            "from_canonical_name": "NOVA RETAIL GROUP",
            "to_canonical_name": "NOVA SOURCING SHANGHAI",
            "candidate_relation_type": "subsidiary_candidate",
            "confidence_level": "high",
            "confidence_score": 0.9,
            "order_count": 7,
            "total_teu": 25.0,
            "recommendation_reason": "Nova sourcing office appears in China-side order roles",
        },
        {
            "from_canonical_name": "ORBIT COMMERCE HOLDINGS",
            "to_canonical_name": "ORBIT ASIA PROCUREMENT",
            "candidate_relation_type": "subsidiary_candidate",
            "confidence_level": "high",
            "confidence_score": 0.88,
            "order_count": 7,
            "total_teu": 21.0,
            "recommendation_reason": "Orbit procurement center supports Orbit customer orders",
        },
        {
            "from_canonical_name": "OCEANBRIDGE LOGISTICS",
            "to_canonical_name": "APEX OUTDOOR USA",
            "candidate_relation_type": "logistics_service_candidate",
            "confidence_level": "medium",
            "confidence_score": 0.63,
            "order_count": 2,
            "total_teu": 2.4,
            "recommendation_reason": "Logistics provider appears in Apex service lanes",
        },
        {
            "from_canonical_name": "SKYLINE FREIGHT FORWARDING",
            "to_canonical_name": "NOVA HOME STORES",
            "candidate_relation_type": "logistics_service_candidate",
            "confidence_level": "medium",
            "confidence_score": 0.58,
            "order_count": 2,
            "total_teu": 3.0,
            "recommendation_reason": "Freight forwarder relationship supplied by demo knowledge",
        },
        {
            "from_canonical_name": "UNMATCHED LEGACY TRADER",
            "to_canonical_name": "APEX OUTDOOR USA",
            "candidate_relation_type": "unknown_candidate",
            "confidence_level": "low",
            "confidence_score": 0.22,
            "order_count": 1,
            "total_teu": 0.5,
            "recommendation_reason": "Legacy noisy record retained for rejection demo",
        },
    ]


def write_demo_data(output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, int]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    entities = build_entities()
    orders = build_orders()
    candidates = build_supplemental_candidates()

    pd.DataFrame(entities).to_csv(target / "demo_entities.csv", index=False)
    pd.DataFrame(orders).to_csv(target / "demo_orders.csv", index=False)
    pd.DataFrame(candidates).to_csv(target / "demo_relationship_candidates.csv", index=False)
    (target / "README.md").write_text(
        "# Demo Data\n\n"
        "Generated by `scripts/generate_demo_data.py` for the M8 acceptance flow.\n\n"
        "- `demo_entities.csv`: about 50 importable company entities.\n"
        "- `demo_orders.csv`: order evidence rows that generate P0 role edges.\n"
        "- `demo_relationship_candidates.csv`: supplemental candidates resolved by canonical name.\n",
        encoding="utf-8",
    )
    return {
        "entity_count": len(entities),
        "order_count": len(orders),
        "supplemental_candidate_count": len(candidates),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate M8 demo CSV files.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    result = write_demo_data(args.output_dir)
    print(
        "Generated demo data: "
        f"{result['entity_count']} entities, "
        f"{result['order_count']} orders, "
        f"{result['supplemental_candidate_count']} supplemental candidates"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the generator test to verify GREEN**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py::test_generate_demo_data_writes_importable_files -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add tests/test_demo_acceptance.py scripts/generate_demo_data.py
git commit -m "feat: add m8 demo data generator"
```

## Task 2: Demo Import Adapter

**Files:**
- Modify: `tests/test_demo_acceptance.py`
- Create: `scripts/import_demo_data.py`

- [ ] **Step 1: Add a failing import adapter test**

Append to `tests/test_demo_acceptance.py`:

```python
from trade_entity_graph.db.connection import get_connection
from scripts.import_demo_data import import_demo_data


def test_import_demo_data_loads_sources_edges_claims_and_supplemental_candidates(
    tmp_path, monkeypatch
) -> None:
    output_dir = tmp_path / "demo"
    db_path = tmp_path / "trade_entity_graph.db"
    archive_root = tmp_path / "archives"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(archive_root))
    write_demo_data(output_dir)

    result = import_demo_data(output_dir=output_dir, db_path=db_path)

    with get_connection(db_path) as connection:
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        alias_count = connection.execute("SELECT COUNT(*) FROM entity_alias").fetchone()[0]
        evidence_count = connection.execute("SELECT COUNT(*) FROM order_evidence").fetchone()[0]
        edge_count = connection.execute("SELECT COUNT(*) FROM order_role_edge").fetchone()[0]
        claim_count = connection.execute("SELECT COUNT(*) FROM relationship_claim").fetchone()[0]
        confidence_levels = {
            row["confidence_level"]
            for row in connection.execute(
                "SELECT DISTINCT confidence_level FROM relationship_claim"
            ).fetchall()
        }
        archived_roles = {
            row["source_role"]
            for row in connection.execute(
                "SELECT source_role FROM import_source_file"
            ).fetchall()
        }
        supplemental = connection.execute(
            """
            SELECT COUNT(*)
            FROM relationship_claim
            WHERE candidate_relation_type IN (
                'same_group_candidate',
                'subsidiary_candidate',
                'logistics_service_candidate',
                'unknown_candidate'
            )
            """
        ).fetchone()[0]

    assert result["run_id"].startswith("RUN_")
    assert entity_count == 50
    assert alias_count >= 100
    assert evidence_count == result["evidence_count"]
    assert 80 <= evidence_count <= 120
    assert edge_count == result["edge_count"]
    assert edge_count > evidence_count * 2
    assert claim_count == result["claim_count"] + result["supplemental_candidate_count"]
    assert {"high", "medium", "low"}.issubset(confidence_levels)
    assert archived_roles == {"entities", "orders"}
    assert supplemental == result["supplemental_candidate_count"]
```

- [ ] **Step 2: Run the import adapter test to verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py::test_import_demo_data_loads_sources_edges_claims_and_supplemental_candidates -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.import_demo_data'`.

- [ ] **Step 3: Implement `scripts/import_demo_data.py`**

Create `scripts/import_demo_data.py`:

```python
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
```

- [ ] **Step 4: Run the import adapter test to verify GREEN**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py::test_import_demo_data_loads_sources_edges_claims_and_supplemental_candidates -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add tests/test_demo_acceptance.py scripts/import_demo_data.py
git commit -m "feat: add m8 demo import adapter"
```

## Task 3: Demo Review Seeder

**Files:**
- Modify: `tests/test_demo_acceptance.py`
- Create: `scripts/seed_demo_reviews.py`

- [ ] **Step 1: Add the failing end-to-end seeded review test**

Append to `tests/test_demo_acceptance.py`:

```python
from trade_entity_graph.services.export_service import export_relationship_rows
from trade_entity_graph.services.graph_service import get_ego_graph
from trade_entity_graph.services.relationship_service import get_relationship_evidence
from scripts.seed_demo_reviews import seed_demo_reviews


def _entity_id(db_path: Path, canonical_name: str) -> str:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT entity_id FROM entity WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()
    assert row is not None
    return row["entity_id"]


def test_demo_acceptance_flow_imports_reviews_graphs_and_exports(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "demo"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))
    write_demo_data(output_dir)
    import_demo_data(output_dir=output_dir, db_path=db_path)

    seed_result = seed_demo_reviews(db_path=db_path)

    with get_connection(db_path) as connection:
        curated_count = connection.execute(
            "SELECT COUNT(*) FROM curated_relationship"
        ).fetchone()[0]
        decision_count = connection.execute(
            "SELECT COUNT(*) FROM relationship_decision"
        ).fetchone()[0]
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        relation_types = {
            row["relation_type"]
            for row in connection.execute(
                "SELECT DISTINCT relation_type FROM curated_relationship"
            ).fetchall()
        }
        statuses = {
            row["relation_status"]
            for row in connection.execute(
                "SELECT DISTINCT relation_status FROM curated_relationship"
            ).fetchall()
        }
        pending_claims = connection.execute(
            """
            SELECT COUNT(*)
            FROM relationship_claim rc
            WHERE NOT EXISTS (
                SELECT 1
                FROM curated_relationship cr
                WHERE cr.decision_source = rc.claim_id
            )
            """
        ).fetchone()[0]
        rejected_relationship_id = connection.execute(
            """
            SELECT relationship_id
            FROM curated_relationship
            WHERE relation_status = 'rejected'
            LIMIT 1
            """
        ).fetchone()["relationship_id"]

    assert seed_result["created_relationship_count"] >= 12
    assert curated_count == seed_result["created_relationship_count"]
    assert decision_count == curated_count
    assert audit_count == curated_count
    assert {
        "same_group",
        "subsidiary",
        "factory_node",
        "sales_center",
        "trading_partner",
        "logistics_service",
        "rejected_relation",
    }.issubset(relation_types)
    assert {"verified", "rejected", "manual_only"}.issubset(statuses)
    assert pending_claims >= 10

    center_id = _entity_id(db_path, "APEX OUTDOOR USA")
    graph = get_ego_graph(center_id, db_path=db_path)
    graph_with_rejected = get_ego_graph(center_id, db_path=db_path, include_rejected=True)
    exported = export_relationship_rows(center_id, db_path=db_path)
    evidence = get_relationship_evidence(exported[0]["relationship_id"], db_path=db_path)

    assert graph["summary"]["node_count"] >= 5
    assert graph["summary"]["edge_count"] >= 10
    assert all(edge["status"] != "rejected" for edge in graph["edges"])
    assert any(edge["id"] == rejected_relationship_id for edge in graph_with_rejected["edges"])
    assert exported
    assert evidence

    second_seed = seed_demo_reviews(db_path=db_path)
    assert second_seed["skipped"] is True
```

- [ ] **Step 2: Run the seeded review test to verify RED**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py::test_demo_acceptance_flow_imports_reviews_graphs_and_exports -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.seed_demo_reviews'`.

- [ ] **Step 3: Implement `scripts/seed_demo_reviews.py`**

Create `scripts/seed_demo_reviews.py`:

```python
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
    ("APEX OUTDOOR USA", "DRAGON PEAK MANUFACTURING", "confirm", "trading_partner", "Repeated Apex orders with Dragon Peak factory."),
    ("APEX OUTDOOR USA", "SUNRISE PLASTICS NINGBO", "confirm", "trading_partner", "Repeated Apex plastic product lanes."),
    ("NOVA HOME STORES", "RIVERSTONE METALWORKS", "modify", "factory_node", "Riverstone acts as Nova metalware production node."),
    ("NOVA HOME STORES", "CRESCENT FURNITURE WORKS", "modify", "factory_node", "Crescent supplies Nova furniture lanes."),
    ("ORBIT MARKETPLACE", "GREENFIELD ELECTRONICS", "confirm", "trading_partner", "Orbit electronics orders repeat across multiple shipments."),
    ("ORBIT MARKETPLACE", "ORBIT ASIA PROCUREMENT", "modify", "sales_center", "Orbit Asia is treated as procurement and sales support center."),
    ("LUMEN BRANDS", "LUMEN LATAM IMPORTS", "modify", "sales_center", "Lumen Latam appears as repeated consignee and notify office."),
    ("MERIDIAN SUPPLY CHAIN", "TRANSWORLD CARGO SERVICES", "reject", "rejected_relation", "Transworld is a logistics notify party, not a business relationship."),
    ("BLUE RIDGE SOURCING", "YQN LOGISTICS", "reject", "rejected_relation", "YQN logistics role should not become a curated relationship."),
]

MANUAL_RELATIONSHIPS = [
    ("APEX GLOBAL HOLDINGS", "APEX OUTDOOR USA", "same_group", "Apex brand owner and US customer are in the same group."),
    ("APEX GLOBAL HOLDINGS", "APEX GLOBAL SOURCING HK", "subsidiary", "Apex HK sourcing entity is a subsidiary of Apex Global."),
    ("NOVA RETAIL GROUP", "NOVA HOME STORES", "same_group", "Nova Home is part of Nova Retail Group."),
    ("NOVA RETAIL GROUP", "NOVA SOURCING SHANGHAI", "subsidiary", "Nova Shanghai is the group sourcing subsidiary."),
    ("ORBIT COMMERCE HOLDINGS", "ORBIT ASIA PROCUREMENT", "subsidiary", "Orbit Asia Procurement supports the Orbit group."),
    ("OCEANBRIDGE LOGISTICS", "APEX OUTDOOR USA", "logistics_service", "Oceanbridge is manually known as Apex logistics provider."),
    ("SKYLINE FREIGHT FORWARDING", "NOVA HOME STORES", "logistics_service", "Skyline is manually known as Nova logistics provider."),
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
```

- [ ] **Step 4: Run the seeded review test to verify GREEN**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py::test_demo_acceptance_flow_imports_reviews_graphs_and_exports -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add tests/test_demo_acceptance.py scripts/seed_demo_reviews.py
git commit -m "feat: seed m8 demo reviews"
```

## Task 4: Generate and Commit Demo Files

**Files:**
- Create: `data/demo/demo_entities.csv`
- Create: `data/demo/demo_orders.csv`
- Create: `data/demo/demo_relationship_candidates.csv`
- Create: `data/demo/README.md`

- [ ] **Step 1: Generate the committed demo files**

Run:

```powershell
uv --cache-dir .uv-cache run python scripts\generate_demo_data.py
```

Expected output starts with:

```text
Generated demo data: 50 entities,
```

- [ ] **Step 2: Inspect generated file sizes and row counts**

Run:

```powershell
python -c "import pandas as pd; from pathlib import Path; base=Path('data/demo'); print(len(pd.read_csv(base/'demo_entities.csv')), len(pd.read_csv(base/'demo_orders.csv')), len(pd.read_csv(base/'demo_relationship_candidates.csv')))"
```

Expected output:

```text
50 81 6
```

If the order count changes due to later generator tuning, keep it between 80 and 120 and update this plan checkbox note in the execution log.

- [ ] **Step 3: Run demo acceptance tests against generated code**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py -q
```

Expected: all tests in `tests/test_demo_acceptance.py` PASS.

- [ ] **Step 4: Commit Task 4**

Run:

```powershell
git add data/demo
git commit -m "data: add m8 demo dataset"
```

## Task 5: Documentation and Acceptance Checklist

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/task-breakdown.md`

- [ ] **Step 1: Add demo commands to `README.md`**

Insert after the existing Streamlit startup snippet:

```markdown
### M8 演示数据与验收

生成并导入约 50 个主体、80+ 条订单和覆盖多种关系类型的演示数据：

```powershell
uv --cache-dir .uv-cache run python scripts\generate_demo_data.py
uv --cache-dir .uv-cache run python scripts\init_db.py
uv --cache-dir .uv-cache run python scripts\import_demo_data.py
uv --cache-dir .uv-cache run python scripts\seed_demo_reviews.py
```

演示数据位于 `data/demo/`。导入后，系统会保留一批待审核候选关系，并预置覆盖 `same_group`、`subsidiary`、`factory_node`、`sales_center`、`trading_partner`、`logistics_service` 和 `rejected_relation` 的已审核关系。
```

- [ ] **Step 2: Add demo commands to `README.en.md`**

Insert after the existing Streamlit startup snippet:

```markdown
### M8 Demo Data and Acceptance

Generate and import demo data with about 50 entities, 80+ orders, and broad relationship coverage:

```powershell
uv --cache-dir .uv-cache run python scripts\generate_demo_data.py
uv --cache-dir .uv-cache run python scripts\init_db.py
uv --cache-dir .uv-cache run python scripts\import_demo_data.py
uv --cache-dir .uv-cache run python scripts\seed_demo_reviews.py
```

The demo files live under `data/demo/`. After import, the system keeps pending candidates for manual review and pre-seeds reviewed relationships covering `same_group`, `subsidiary`, `factory_node`, `sales_center`, `trading_partner`, `logistics_service`, and `rejected_relation`.
```

- [ ] **Step 3: Update `docs/task-breakdown.md`**

In `docs/task-breakdown.md`, update the current implementation status section to add:

```markdown
- M8：新增可重复生成的演示数据包和预置审核脚本；演示数据约 50 个主体、80+ 条订单，保留待审核候选关系，并覆盖主要最终关系类型。
```

In the acceptance checklist, convert the P0 items to checked boxes only after the Task 6 verification commands pass. The final checklist should show every P0 acceptance item as `- [x]`.

- [ ] **Step 4: Commit Task 5**

Run:

```powershell
git add README.md README.en.md docs/task-breakdown.md
git commit -m "docs: document m8 demo acceptance flow"
```

## Task 6: Full Verification and Cleanup

**Files:**
- No new files unless verification exposes a bug.

- [ ] **Step 1: Run the full M8 test file**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py
```

Expected: all M8 tests PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
uv --cache-dir .uv-cache run pytest
```

Expected: full test suite PASS. A `.pytest_cache` write-permission warning may appear and is acceptable if all tests pass.

- [ ] **Step 3: Run ruff**

Run:

```powershell
uv --cache-dir .uv-cache run ruff check .
```

Expected:

```text
All checks passed!
```

- [ ] **Step 4: Check Git status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## main...origin/main [ahead N]
?? streamlit-ui.err.log
?? streamlit-ui.log
```

Only the existing local Streamlit log files should remain untracked. Do not commit them.

- [ ] **Step 5: Final commit only if verification required additional fixes**

If Task 6 required code or documentation fixes, commit them:

```powershell
git add <fixed-files>
git commit -m "fix: stabilize m8 demo acceptance"
```

If no files changed, skip this commit.

## Self-Review

- Spec coverage: Tasks cover demo generation, committed demo files, demo import, supplemental candidates by canonical name, seeded reviewed relationships, pending candidates, tests, documentation, and verification.
- Incomplete-marker scan: The plan contains no open-ended markers. The only conditional instruction is in Task 6 for optional stabilization fixes after verification.
- Type consistency: Public functions are `write_demo_data`, `import_demo_data`, and `seed_demo_reviews`; tests and scripts use these exact names.
- Scope check: The plan stays within M8 and does not implement P1 two-hop graph or path search.
