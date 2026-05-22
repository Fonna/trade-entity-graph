"""Application configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    app_name: str
    app_env: str
    database_path: Path
    import_archive_root: Path
    import_operator: str
    rule_version: str
    field_mapping_version: str


def get_settings() -> Settings:
    """Return immutable application settings."""

    database_path = Path(os.getenv("TEG_DATABASE_PATH", "data/processed/trade_entity_graph.db"))
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    import_archive_root = Path(os.getenv("TEG_IMPORT_ARCHIVE_ROOT", "data/raw/imports"))
    if not import_archive_root.is_absolute():
        import_archive_root = PROJECT_ROOT / import_archive_root
    return Settings(
        app_name="trade-entity-graph",
        app_env=os.getenv("TEG_APP_ENV", "local"),
        database_path=database_path,
        import_archive_root=import_archive_root,
        import_operator=os.getenv("TEG_IMPORT_OPERATOR", "local_user"),
        rule_version=os.getenv("TEG_RULE_VERSION", "mvp-0.1"),
        field_mapping_version=os.getenv("TEG_FIELD_MAPPING_VERSION", "mvp-0.1"),
    )
