"""Entity and alias loading for imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from trade_entity_graph.importers.field_mapping import get_value
from trade_entity_graph.importers.models import ImportErrorRecord, ImportSourceRow
from trade_entity_graph.utils.ids import new_id
from trade_entity_graph.utils.normalization import normalize_company_name


@dataclass
class EntityLoadResult:
    entity_count: int = 0
    alias_count: int = 0
    success_rows: int = 0
    skipped_rows: list[str] = field(default_factory=list)
    import_errors: list[ImportErrorRecord] = field(default_factory=list)


def find_entity_id_by_name(connection: sqlite3.Connection, name: str | None) -> str | None:
    """Resolve an entity id by canonical name or alias."""

    normalized = normalize_company_name(name)
    if not normalized:
        return None

    row = connection.execute(
        "SELECT entity_id FROM entity WHERE canonical_name = ?",
        (normalized,),
    ).fetchone()
    if row:
        return row["entity_id"]

    row = connection.execute(
        """
        SELECT entity_id
        FROM entity_alias
        WHERE UPPER(TRIM(alias_name)) = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (normalized,),
    ).fetchone()
    return row["entity_id"] if row else None


def _insert_alias(
    connection: sqlite3.Connection,
    *,
    entity_id: str,
    alias_name: str,
    alias_type: str,
    source: str,
    run_id: str,
) -> bool:
    existing = connection.execute(
        """
        SELECT alias_id FROM entity_alias
        WHERE entity_id = ? AND alias_name = ? AND alias_type = ?
        """,
        (entity_id, alias_name, alias_type),
    ).fetchone()
    if existing:
        return False

    connection.execute(
        """
        INSERT INTO entity_alias (alias_id, entity_id, alias_name, alias_type, source, run_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (new_id("ALS"), entity_id, alias_name, alias_type, source, run_id),
    )
    return True


def _record_import_entity(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    entity_id: str,
    row: ImportSourceRow,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO import_entity (
            run_id, entity_id, source_file, source_sheet, source_row
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, entity_id, row.source_file, row.source_sheet, row.source_row),
    )


def load_entities(
    connection: sqlite3.Connection,
    rows: list[ImportSourceRow],
    *,
    run_id: str,
    source: str,
) -> EntityLoadResult:
    """Load canonical entities and aliases from source rows."""

    result = EntityLoadResult()
    seen_entities: set[str] = set()
    for row in rows:
        raw_canonical_name = get_value(row.values, "canonical_name", "")
        canonical_name = normalize_company_name(raw_canonical_name)
        if not canonical_name:
            result.skipped_rows.append(
                f"{row.source_file}:{row.source_row}: missing canonical_name"
            )
            result.import_errors.append(
                ImportErrorRecord(
                    run_id=run_id,
                    error_type="missing_required_value",
                    severity="blocking",
                    message="标准企业名称不能为空",
                    file_role="entities",
                    source_path=row.source_file,
                    sheet_name=row.source_sheet,
                    row_number=row.source_row,
                    normalized_field="canonical_name",
                    raw_value=raw_canonical_name,
                )
            )
            continue

        result.success_rows += 1
        entity_id = find_entity_id_by_name(connection, canonical_name)
        if entity_id is None:
            entity_id = new_id("ENT")
            connection.execute(
                """
                INSERT INTO entity (entity_id, canonical_name, country, entity_type, run_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    canonical_name,
                    get_value(row.values, "country"),
                    get_value(row.values, "entity_type"),
                    run_id,
                ),
            )
        seen_entities.add(entity_id)
        _record_import_entity(connection, run_id=run_id, entity_id=entity_id, row=row)

        aliases = (
            (get_value(row.values, "original_name"), "original_name"),
            (get_value(row.values, "clean_name"), "clean_name"),
            (get_value(row.values, "alias_name"), "alias"),
        )
        for alias_name, alias_type in aliases:
            if alias_name and _insert_alias(
                connection,
                entity_id=entity_id,
                alias_name=str(alias_name).strip(),
                alias_type=alias_type,
                source=source,
                run_id=run_id,
            ):
                result.alias_count += 1

    result.entity_count = len(seen_entities)
    connection.commit()
    return result
