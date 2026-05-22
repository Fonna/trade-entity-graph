"""Application configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    app_name: str = "trade-entity-graph"
    app_env: str = os.getenv("TEG_APP_ENV", "local")
    database_path: Path = PROJECT_ROOT / os.getenv(
        "TEG_DATABASE_PATH", "data/processed/trade_entity_graph.db"
    )
    import_operator: str = os.getenv("TEG_IMPORT_OPERATOR", "local_user")
    rule_version: str = os.getenv("TEG_RULE_VERSION", "mvp-0.1")
    field_mapping_version: str = os.getenv("TEG_FIELD_MAPPING_VERSION", "mvp-0.1")


def get_settings() -> Settings:
    """Return immutable application settings."""

    return Settings()
