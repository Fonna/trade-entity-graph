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
        (
            "APEX GLOBAL HOLDINGS",
            "Apex Global Holdings Ltd",
            "APEX GLOBAL HOLDINGS LTD",
            "Apex Group",
            "US",
            "group",
        ),
        (
            "APEX OUTDOOR USA",
            "Apex Outdoor USA Inc",
            "APEX OUTDOOR USA INC",
            "Apex Outdoor",
            "US",
            "customer",
        ),
        (
            "APEX OUTDOOR EUROPE",
            "Apex Outdoor Europe GmbH",
            "APEX OUTDOOR EUROPE GMBH",
            "Apex Europe",
            "DE",
            "sales_center",
        ),
        (
            "APEX SOURCING SHENZHEN",
            "Apex Sourcing Shenzhen Co Ltd",
            "APEX SOURCING SHENZHEN CO LTD",
            "Apex Shenzhen",
            "CN",
            "trader",
        ),
        (
            "NOVA RETAIL GROUP",
            "Nova Retail Group LLC",
            "NOVA RETAIL GROUP LLC",
            "Nova Retail",
            "US",
            "group",
        ),
        (
            "NOVA HOME STORES",
            "Nova Home Stores Inc",
            "NOVA HOME STORES INC",
            "Nova Home",
            "US",
            "customer",
        ),
        (
            "NOVA EUROPE BUYING",
            "Nova Europe Buying BV",
            "NOVA EUROPE BUYING BV",
            "Nova Europe",
            "NL",
            "sales_center",
        ),
        (
            "ORBIT COMMERCE HOLDINGS",
            "Orbit Commerce Holdings Ltd",
            "ORBIT COMMERCE HOLDINGS LTD",
            "Orbit Group",
            "GB",
            "group",
        ),
        (
            "ORBIT MARKETPLACE",
            "Orbit Marketplace Inc",
            "ORBIT MARKETPLACE INC",
            "Orbit Market",
            "US",
            "customer",
        ),
        (
            "ORBIT CANADA BUYING",
            "Orbit Canada Buying Ltd",
            "ORBIT CANADA BUYING LTD",
            "Orbit Canada",
            "CA",
            "buyer",
        ),
        ("LUMEN BRANDS", "Lumen Brands LLC", "LUMEN BRANDS LLC", "Lumen", "US", "customer"),
        (
            "LUMEN LATAM IMPORTS",
            "Lumen Latam Imports SA",
            "LUMEN LATAM IMPORTS SA",
            "Lumen Latam",
            "MX",
            "buyer",
        ),
        (
            "MERIDIAN SUPPLY CHAIN",
            "Meridian Supply Chain Ltd",
            "MERIDIAN SUPPLY CHAIN LTD",
            "Meridian Supply",
            "SG",
            "trader",
        ),
        (
            "PACIFIC HOME BUYING",
            "Pacific Home Buying Pty Ltd",
            "PACIFIC HOME BUYING PTY LTD",
            "Pacific Home",
            "AU",
            "buyer",
        ),
        (
            "HARBOR WHOLESALE",
            "Harbor Wholesale Co",
            "HARBOR WHOLESALE CO",
            "Harbor Wholesale",
            "US",
            "customer",
        ),
        (
            "SUMMIT DIGITAL RETAIL",
            "Summit Digital Retail Inc",
            "SUMMIT DIGITAL RETAIL INC",
            "Summit Digital",
            "US",
            "customer",
        ),
        (
            "BLUE RIDGE SOURCING",
            "Blue Ridge Sourcing LLC",
            "BLUE RIDGE SOURCING LLC",
            "Blue Ridge",
            "US",
            "trader",
        ),
        (
            "DRAGON PEAK MANUFACTURING",
            "Dragon Peak Manufacturing Co Ltd",
            "DRAGON PEAK MANUFACTURING CO LTD",
            "Dragon Peak",
            "CN",
            "factory",
        ),
        (
            "DRAGON PEAK VIETNAM",
            "Dragon Peak Vietnam Ltd",
            "DRAGON PEAK VIETNAM LTD",
            "Dragon Vietnam",
            "VN",
            "factory",
        ),
        (
            "SUNRISE PLASTICS NINGBO",
            "Sunrise Plastics Ningbo Co Ltd",
            "SUNRISE PLASTICS NINGBO CO LTD",
            "Sunrise Ningbo",
            "CN",
            "factory",
        ),
        (
            "SUNRISE PLASTICS THAILAND",
            "Sunrise Plastics Thailand Ltd",
            "SUNRISE PLASTICS THAILAND LTD",
            "Sunrise Thailand",
            "TH",
            "factory",
        ),
        (
            "RIVERSTONE METALWORKS",
            "Riverstone Metalworks Co Ltd",
            "RIVERSTONE METALWORKS CO LTD",
            "Riverstone",
            "CN",
            "factory",
        ),
        (
            "RIVERSTONE CAMBODIA",
            "Riverstone Cambodia Ltd",
            "RIVERSTONE CAMBODIA LTD",
            "Riverstone KH",
            "KH",
            "factory",
        ),
        (
            "EASTWIND TEXTILES",
            "Eastwind Textiles Co Ltd",
            "EASTWIND TEXTILES CO LTD",
            "Eastwind",
            "CN",
            "factory",
        ),
        (
            "EASTWIND BANGLADESH",
            "Eastwind Bangladesh Ltd",
            "EASTWIND BANGLADESH LTD",
            "Eastwind BD",
            "BD",
            "factory",
        ),
        (
            "GREENFIELD ELECTRONICS",
            "Greenfield Electronics Co Ltd",
            "GREENFIELD ELECTRONICS CO LTD",
            "Greenfield",
            "CN",
            "factory",
        ),
        (
            "GREENFIELD MALAYSIA",
            "Greenfield Malaysia Sdn Bhd",
            "GREENFIELD MALAYSIA SDN BHD",
            "Greenfield MY",
            "MY",
            "factory",
        ),
        (
            "ORIENTAL CERAMICS",
            "Oriental Ceramics Ltd",
            "ORIENTAL CERAMICS LTD",
            "Oriental Ceramics",
            "CN",
            "factory",
        ),
        (
            "ORIENTAL CERAMICS INDONESIA",
            "Oriental Ceramics Indonesia PT",
            "ORIENTAL CERAMICS INDONESIA PT",
            "Oriental ID",
            "ID",
            "factory",
        ),
        (
            "ALPINE TOOLING",
            "Alpine Tooling Co Ltd",
            "ALPINE TOOLING CO LTD",
            "Alpine Tooling",
            "CN",
            "factory",
        ),
        (
            "SILVERLINE PACKAGING",
            "Silverline Packaging Ltd",
            "SILVERLINE PACKAGING LTD",
            "Silverline",
            "CN",
            "factory",
        ),
        (
            "AURORA LIGHTING FACTORY",
            "Aurora Lighting Factory Ltd",
            "AURORA LIGHTING FACTORY LTD",
            "Aurora Lighting",
            "CN",
            "factory",
        ),
        (
            "CRESCENT FURNITURE WORKS",
            "Crescent Furniture Works Ltd",
            "CRESCENT FURNITURE WORKS LTD",
            "Crescent Furniture",
            "VN",
            "factory",
        ),
        (
            "NORTHSTAR DISTRIBUTION",
            "Northstar Distribution Inc",
            "NORTHSTAR DISTRIBUTION INC",
            "Northstar",
            "US",
            "buyer",
        ),
        (
            "MAPLE LEAF IMPORTS",
            "Maple Leaf Imports Ltd",
            "MAPLE LEAF IMPORTS LTD",
            "Maple Leaf",
            "CA",
            "buyer",
        ),
        (
            "IBERIA RETAIL IMPORTS",
            "Iberia Retail Imports SL",
            "IBERIA RETAIL IMPORTS SL",
            "Iberia Imports",
            "ES",
            "buyer",
        ),
        (
            "RHINE HOME IMPORTS",
            "Rhine Home Imports GmbH",
            "RHINE HOME IMPORTS GMBH",
            "Rhine Home",
            "DE",
            "buyer",
        ),
        (
            "SAHARA TRADE HOUSE",
            "Sahara Trade House LLC",
            "SAHARA TRADE HOUSE LLC",
            "Sahara Trade",
            "AE",
            "buyer",
        ),
        (
            "ANDES MARKET SUPPLY",
            "Andes Market Supply SAC",
            "ANDES MARKET SUPPLY SAC",
            "Andes Supply",
            "PE",
            "buyer",
        ),
        (
            "ATLAS MEXICO DISTRIBUTION",
            "Atlas Mexico Distribution SA",
            "ATLAS MEXICO DISTRIBUTION SA",
            "Atlas Mexico",
            "MX",
            "buyer",
        ),
        (
            "CAPE TOWN RETAIL IMPORTS",
            "Cape Town Retail Imports Pty",
            "CAPE TOWN RETAIL IMPORTS PTY",
            "Cape Retail",
            "ZA",
            "buyer",
        ),
        ("YQN LOGISTICS", "YQN Logistics Co Ltd", "YQN LOGISTICS CO LTD", "YQN", "CN", "logistics"),
        (
            "OCEANBRIDGE LOGISTICS",
            "Oceanbridge Logistics Ltd",
            "OCEANBRIDGE LOGISTICS LTD",
            "Oceanbridge",
            "CN",
            "logistics",
        ),
        (
            "SKYLINE FREIGHT FORWARDING",
            "Skyline Freight Forwarding Ltd",
            "SKYLINE FREIGHT FORWARDING LTD",
            "Skyline Freight",
            "CN",
            "logistics",
        ),
        (
            "TRANSWORLD CARGO SERVICES",
            "Transworld Cargo Services Ltd",
            "TRANSWORLD CARGO SERVICES LTD",
            "Transworld Cargo",
            "SG",
            "logistics",
        ),
        (
            "GLOBEWAY SHIPPING",
            "Globeway Shipping Ltd",
            "GLOBEWAY SHIPPING LTD",
            "Globeway",
            "HK",
            "logistics",
        ),
        (
            "APEX GLOBAL SOURCING HK",
            "Apex Global Sourcing HK Ltd",
            "APEX GLOBAL SOURCING HK LTD",
            "Apex HK",
            "HK",
            "subsidiary",
        ),
        (
            "NOVA SOURCING SHANGHAI",
            "Nova Sourcing Shanghai Co Ltd",
            "NOVA SOURCING SHANGHAI CO LTD",
            "Nova Shanghai",
            "CN",
            "subsidiary",
        ),
        (
            "ORBIT ASIA PROCUREMENT",
            "Orbit Asia Procurement Ltd",
            "ORBIT ASIA PROCUREMENT LTD",
            "Orbit Asia",
            "SG",
            "subsidiary",
        ),
        (
            "UNMATCHED LEGACY TRADER",
            "Unmatched Legacy Trader Ltd",
            "UNMATCHED LEGACY TRADER LTD",
            "Legacy Trader",
            "HK",
            "unknown",
        ),
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


def _expanded_orders() -> list[tuple[str, str, str, str, float, str, str, str, str, str, int]]:
    """Return lane templates with repeat counts."""

    return [
        (
            "APEX OUTDOOR USA",
            "DRAGON PEAK MANUFACTURING",
            "NORTHSTAR DISTRIBUTION",
            "APEX OUTDOOR EUROPE",
            4.5,
            "Outdoor chair",
            "outdoor furniture",
            "US",
            "Los Angeles",
            "2026-01-05",
            8,
        ),
        (
            "APEX OUTDOOR USA",
            "SUNRISE PLASTICS NINGBO",
            "MAPLE LEAF IMPORTS",
            "APEX GLOBAL SOURCING HK",
            3.0,
            "Storage box",
            "household plastic",
            "CA",
            "Vancouver",
            "2026-01-08",
            6,
        ),
        (
            "NOVA HOME STORES",
            "RIVERSTONE METALWORKS",
            "NOVA EUROPE BUYING",
            "NOVA EUROPE BUYING",
            2.5,
            "Kitchen rack",
            "metal houseware",
            "NL",
            "Rotterdam",
            "2026-01-10",
            7,
        ),
        (
            "NOVA HOME STORES",
            "CRESCENT FURNITURE WORKS",
            "RHINE HOME IMPORTS",
            "NOVA SOURCING SHANGHAI",
            5.0,
            "Flat pack table",
            "furniture",
            "DE",
            "Hamburg",
            "2026-01-12",
            5,
        ),
        (
            "ORBIT MARKETPLACE",
            "GREENFIELD ELECTRONICS",
            "ORBIT CANADA BUYING",
            "ORBIT ASIA PROCUREMENT",
            2.0,
            "LED controller",
            "electronics",
            "CA",
            "Prince Rupert",
            "2026-01-14",
            7,
        ),
        (
            "ORBIT MARKETPLACE",
            "EASTWIND TEXTILES",
            "IBERIA RETAIL IMPORTS",
            "ORBIT ASIA PROCUREMENT",
            3.5,
            "Cotton throw",
            "textile",
            "ES",
            "Valencia",
            "2026-01-16",
            5,
        ),
        (
            "LUMEN BRANDS",
            "AURORA LIGHTING FACTORY",
            "LUMEN LATAM IMPORTS",
            "LUMEN LATAM IMPORTS",
            2.2,
            "Pendant lamp",
            "lighting",
            "MX",
            "Manzanillo",
            "2026-01-18",
            6,
        ),
        (
            "MERIDIAN SUPPLY CHAIN",
            "ORIENTAL CERAMICS",
            "PACIFIC HOME BUYING",
            "TRANSWORLD CARGO SERVICES",
            4.2,
            "Ceramic planter",
            "ceramics",
            "AU",
            "Sydney",
            "2026-01-20",
            5,
        ),
        (
            "HARBOR WHOLESALE",
            "ALPINE TOOLING",
            "HARBOR WHOLESALE",
            "SAME AS",
            1.8,
            "Hand tool kit",
            "tools",
            "US",
            "Long Beach",
            "2026-01-22",
            4,
        ),
        (
            "SUMMIT DIGITAL RETAIL",
            "GREENFIELD MALAYSIA",
            "SAHARA TRADE HOUSE",
            "TO ORDER",
            2.8,
            "Smart sensor",
            "electronics",
            "AE",
            "Jebel Ali",
            "2026-01-24",
            4,
        ),
        (
            "BLUE RIDGE SOURCING",
            "SILVERLINE PACKAGING",
            "ANDES MARKET SUPPLY",
            "YQN LOGISTICS",
            1.5,
            "Gift carton",
            "packaging",
            "PE",
            "Callao",
            "2026-01-26",
            3,
        ),
        (
            "APEX SOURCING SHENZHEN",
            "DRAGON PEAK VIETNAM",
            "ATLAS MEXICO DISTRIBUTION",
            "APEX OUTDOOR EUROPE",
            3.2,
            "Camping table",
            "outdoor furniture",
            "MX",
            "Veracruz",
            "2026-01-28",
            4,
        ),
        (
            "NOVA HOME STORES",
            "SUNRISE PLASTICS THAILAND",
            "CAPE TOWN RETAIL IMPORTS",
            "NOVA EUROPE BUYING",
            2.6,
            "Laundry basket",
            "household plastic",
            "ZA",
            "Cape Town",
            "2026-02-01",
            3,
        ),
        (
            "ORBIT MARKETPLACE",
            "RIVERSTONE CAMBODIA",
            "MAPLE LEAF IMPORTS",
            "ORBIT CANADA BUYING",
            2.1,
            "Metal shelf",
            "metal houseware",
            "CA",
            "Montreal",
            "2026-02-03",
            3,
        ),
        (
            "LUMEN BRANDS",
            "ORIENTAL CERAMICS INDONESIA",
            "IBERIA RETAIL IMPORTS",
            "LUMEN LATAM IMPORTS",
            1.7,
            "Table vase",
            "ceramics",
            "ES",
            "Barcelona",
            "2026-02-05",
            3,
        ),
        (
            "MERIDIAN SUPPLY CHAIN",
            "EASTWIND BANGLADESH",
            "RHINE HOME IMPORTS",
            "TRANSWORLD CARGO SERVICES",
            2.3,
            "Bedding set",
            "textile",
            "DE",
            "Bremerhaven",
            "2026-02-07",
            3,
        ),
        (
            "PACIFIC HOME BUYING",
            "CRESCENT FURNITURE WORKS",
            "PACIFIC HOME BUYING",
            "SAME AS",
            1.6,
            "Dining chair",
            "furniture",
            "AU",
            "Melbourne",
            "2026-02-09",
            3,
        ),
        (
            "APEX OUTDOOR USA",
            "OCEANBRIDGE LOGISTICS",
            "NORTHSTAR DISTRIBUTION",
            "APEX GLOBAL SOURCING HK",
            1.0,
            "Freight handling",
            "logistics service",
            "US",
            "Los Angeles",
            "2026-02-11",
            2,
        ),
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
        "- `demo_relationship_candidates.csv`: supplemental candidates resolved by "
        "canonical name.\n",
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
