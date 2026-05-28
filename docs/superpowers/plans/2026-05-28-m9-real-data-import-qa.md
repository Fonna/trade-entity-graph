# M9 Real Data Import QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M9 real-data import quality loop: configurable field mapping, row-level import errors, import batch visibility, quality reports, API endpoints, and Streamlit quality review.

**Architecture:** Extend the current M2-M8 modular monolith. Importers collect structured `ImportErrorRecord` values while still loading valid rows, persist those records in a new `import_error` table, and expose reports through a query-only `import_quality_service` used by FastAPI and Streamlit.

**Tech Stack:** Python 3.10+, SQLite, Pandas, FastAPI, Pydantic, Streamlit, pytest, ruff.

---

## File Structure

- Modify `src/trade_entity_graph/db/schema.sql`: add `import_error` table, indexes, and `import_batch.warning_rows`.
- Modify `src/trade_entity_graph/db/connection.py`: add legacy column migration for `import_batch.warning_rows`.
- Modify `tests/test_database_schema.py`: assert `import_error` table and indexes exist.
- Modify `src/trade_entity_graph/importers/models.py`: add `ImportErrorRecord`; extend `ImportRunResult`.
- Create `src/trade_entity_graph/importers/import_error_loader.py`: write structured errors.
- Create `src/trade_entity_graph/importers/field_mappings/default.json`: default role-specific column aliases.
- Modify `src/trade_entity_graph/importers/field_mapping.py`: resolve role-specific headers and emit mapping errors.
- Modify `src/trade_entity_graph/importers/entity_loader.py`: return structured missing-entity-name errors.
- Modify `src/trade_entity_graph/importers/evidence_loader.py`: return missing order and invalid TEU errors.
- Modify `src/trade_entity_graph/importers/relationship_loader.py`: support endpoint names and return unknown-entity / self-pair errors.
- Modify `src/trade_entity_graph/importers/pipeline.py`: resolve mappings, collect errors, persist errors, return quality summary.
- Modify `src/trade_entity_graph/importers/batch_loader.py`: persist `warning_rows`.
- Create `src/trade_entity_graph/services/import_quality_service.py`: list batches, load details, list errors, report, export CSV.
- Modify `src/trade_entity_graph/api/routers/imports.py`: add read endpoints and return import quality in `/imports/run`.
- Modify `src/trade_entity_graph/ui/streamlit_app.py`: show recent batches, reports, errors, and error CSV download.
- Modify `README.md`, `README.en.md`, `docs/task-breakdown.md`: document M9.

---

### Task 1: Import Error Schema

**Files:**
- Modify: `src/trade_entity_graph/db/schema.sql`
- Modify: `src/trade_entity_graph/db/connection.py`
- Modify: `tests/test_database_schema.py`

- [ ] **Step 1: Write the failing schema assertions**

In `tests/test_database_schema.py`, add `import_error` to `EXPECTED_TABLES`, add `idx_import_error_run`, `idx_import_error_type`, and `idx_import_error_severity` to `EXPECTED_INDEXES`, and add:

```python
def test_import_error_schema_has_traceability_columns(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(import_error)")
        }

    assert {
        "error_id",
        "run_id",
        "source_file_id",
        "file_role",
        "source_path",
        "sheet_name",
        "row_number",
        "column_name",
        "normalized_field",
        "raw_value",
        "error_type",
        "severity",
        "message",
        "created_at",
    }.issubset(columns)
```

- [ ] **Step 2: Run schema tests to verify red**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_database_schema.py -v
```

Expected: FAIL because `import_error` does not exist.

- [ ] **Step 3: Add schema and indexes**

In `src/trade_entity_graph/db/schema.sql`, add `warning_rows INTEGER DEFAULT 0,` after `error_rows`, then add:

```sql
CREATE TABLE IF NOT EXISTS import_error (
    error_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES import_batch(run_id),
    source_file_id TEXT REFERENCES import_source_file(source_file_id),
    file_role TEXT,
    source_path TEXT,
    sheet_name TEXT,
    row_number INTEGER,
    column_name TEXT,
    normalized_field TEXT,
    raw_value TEXT,
    error_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_import_error_run ON import_error(run_id);
CREATE INDEX IF NOT EXISTS idx_import_error_type ON import_error(error_type);
CREATE INDEX IF NOT EXISTS idx_import_error_severity ON import_error(severity);
```

- [ ] **Step 4: Add legacy migration for existing local databases**

In `src/trade_entity_graph/db/connection.py`, update `SCHEMA_COLUMN_MIGRATIONS`:

```python
SCHEMA_COLUMN_MIGRATIONS: dict[str, dict[str, str]] = {
    "import_batch": {
        "warning_rows": "INTEGER DEFAULT 0",
    },
    "order_evidence": {
        "customer_name": "TEXT",
        "shipper_name": "TEXT",
        "consignee_name": "TEXT",
        "notify_name": "TEXT",
    },
}
```

- [ ] **Step 5: Run schema tests to verify green**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_database_schema.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/trade_entity_graph/db/schema.sql src/trade_entity_graph/db/connection.py tests/test_database_schema.py
git commit -m "feat: add import error schema"
```

---

### Task 2: Import Error Model And Loader

**Files:**
- Modify: `src/trade_entity_graph/importers/models.py`
- Create: `src/trade_entity_graph/importers/import_error_loader.py`
- Create: `tests/test_import_error_loader.py`

- [ ] **Step 1: Write failing loader tests**

Create `tests/test_import_error_loader.py`:

```python
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.import_error_loader import write_import_errors
from trade_entity_graph.importers.models import ImportErrorRecord


def test_write_import_errors_persists_traceability_fields(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_ERR', 'orders.csv', 'tester')
            """
        )
        connection.commit()

        count = write_import_errors(
            connection,
            [
                ImportErrorRecord(
                    run_id="RUN_ERR",
                    file_role="orders",
                    source_path="orders.csv",
                    sheet_name="orders",
                    row_number=3,
                    column_name="TEU",
                    normalized_field="teu",
                    raw_value="abc",
                    error_type="invalid_numeric_value",
                    severity="blocking",
                    message="TEU 必须是数字",
                )
            ],
        )

        row = connection.execute(
            """
            SELECT run_id, file_role, source_path, sheet_name, row_number,
                   column_name, normalized_field, raw_value, error_type, severity, message
            FROM import_error
            """
        ).fetchone()

    assert count == 1
    assert row["run_id"] == "RUN_ERR"
    assert row["file_role"] == "orders"
    assert row["row_number"] == 3
    assert row["normalized_field"] == "teu"
    assert row["raw_value"] == "abc"
    assert row["error_type"] == "invalid_numeric_value"
    assert row["severity"] == "blocking"
    assert row["message"] == "TEU 必须是数字"


def test_import_error_record_as_dict_stringifies_raw_value() -> None:
    record = ImportErrorRecord(
        run_id="RUN_ERR",
        file_role="entities",
        source_path="entities.csv",
        sheet_name="entities",
        row_number=2,
        column_name="标准名",
        normalized_field="canonical_name",
        raw_value=123,
        error_type="missing_required_value",
        severity="blocking",
        message="标准企业名称不能为空",
    )

    assert record.as_dict()["raw_value"] == "123"
    assert record.as_dict()["source_file_id"] is None
```

- [ ] **Step 2: Run loader tests to verify red**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_import_error_loader.py -v
```

Expected: FAIL because the model and loader do not exist.

- [ ] **Step 3: Add `ImportErrorRecord` and extend `ImportRunResult`**

In `src/trade_entity_graph/importers/models.py`, add:

```python
@dataclass(frozen=True)
class ImportErrorRecord:
    """Structured import problem with source-row traceability."""

    run_id: str
    error_type: str
    severity: str
    message: str
    source_file_id: str | None = None
    file_role: str | None = None
    source_path: str | None = None
    sheet_name: str | None = None
    row_number: int | None = None
    column_name: str | None = None
    normalized_field: str | None = None
    raw_value: Any | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_file_id": self.source_file_id,
            "file_role": self.file_role,
            "source_path": self.source_path,
            "sheet_name": self.sheet_name,
            "row_number": self.row_number,
            "column_name": self.column_name,
            "normalized_field": self.normalized_field,
            "raw_value": None if self.raw_value is None else str(self.raw_value),
            "error_type": self.error_type,
            "severity": self.severity,
            "message": self.message,
        }
```

Add these fields to `ImportRunResult`:

```python
    import_errors: list[dict[str, Any]] = field(default_factory=list)
    warning_count: int = 0
    error_count: int = 0
    quality_summary: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Create error loader**

Create `src/trade_entity_graph/importers/import_error_loader.py`:

```python
"""Persistence helpers for structured import errors."""

from __future__ import annotations

import sqlite3

from trade_entity_graph.importers.models import ImportErrorRecord
from trade_entity_graph.utils.ids import new_id


def write_import_errors(connection: sqlite3.Connection, records: list[ImportErrorRecord]) -> int:
    """Persist structured import errors and return inserted row count."""

    for record in records:
        payload = record.as_dict()
        connection.execute(
            """
            INSERT INTO import_error (
                error_id, run_id, source_file_id, file_role, source_path, sheet_name,
                row_number, column_name, normalized_field, raw_value, error_type,
                severity, message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("IER"),
                payload["run_id"],
                payload["source_file_id"],
                payload["file_role"],
                payload["source_path"],
                payload["sheet_name"],
                payload["row_number"],
                payload["column_name"],
                payload["normalized_field"],
                payload["raw_value"],
                payload["error_type"],
                payload["severity"],
                payload["message"],
            ),
        )
    connection.commit()
    return len(records)
```

- [ ] **Step 5: Run loader tests to verify green**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_import_error_loader.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/trade_entity_graph/importers/models.py src/trade_entity_graph/importers/import_error_loader.py tests/test_import_error_loader.py
git commit -m "feat: persist structured import errors"
```

---

### Task 3: Configurable Field Mapping

**Files:**
- Create: `src/trade_entity_graph/importers/field_mappings/default.json`
- Modify: `src/trade_entity_graph/importers/field_mapping.py`
- Create: `tests/test_field_mapping.py`

- [ ] **Step 1: Write failing field mapping tests**

Create `tests/test_field_mapping.py`:

```python
from trade_entity_graph.importers.field_mapping import resolve_rows_for_role
from trade_entity_graph.importers.models import ImportSourceRow


def test_resolve_rows_for_role_maps_real_order_column_variants() -> None:
    rows = [
        ImportSourceRow(
            source_file="orders.csv",
            source_sheet="orders",
            source_row=2,
            values={
                "业务编号": "SO-1",
                "Booking Customer": "Acme Trading Ltd",
                "Shipper": "Beta Factory Inc",
                "Consignee": "Omega Buyer LLC",
                "Notify Party": "Omega Buyer LLC",
                "箱量": "3.5",
                "目的国家": "MX",
                "品名": "Widget",
            },
        )
    ]

    resolved_rows, errors = resolve_rows_for_role(rows, role="orders", run_id="RUN_MAP")

    assert errors == []
    assert resolved_rows[0].values["order_id"] == "SO-1"
    assert resolved_rows[0].values["customer_name"] == "Acme Trading Ltd"
    assert resolved_rows[0].values["teu"] == "3.5"
    assert resolved_rows[0].values["product_name"] == "Widget"


def test_resolve_rows_for_role_records_missing_required_header() -> None:
    rows = [
        ImportSourceRow(
            source_file="orders.csv",
            source_sheet="orders",
            source_row=2,
            values={"客户名称": "Acme Trading Ltd"},
        )
    ]

    resolved_rows, errors = resolve_rows_for_role(rows, role="orders", run_id="RUN_MAP")

    assert resolved_rows == []
    assert errors[0].error_type == "missing_required_field"
    assert errors[0].severity == "blocking"
    assert errors[0].normalized_field == "order_id"


def test_resolve_rows_for_role_records_duplicate_mapping_warning() -> None:
    rows = [
        ImportSourceRow(
            source_file="entities.csv",
            source_sheet="entities",
            source_row=2,
            values={"标准名": "ACME TRADING", "企业标准名": "ACME TRADING DUP"},
        )
    ]

    resolved_rows, errors = resolve_rows_for_role(rows, role="entities", run_id="RUN_MAP")

    assert resolved_rows[0].values["canonical_name"] == "ACME TRADING"
    assert errors[0].error_type == "field_mapping_error"
    assert errors[0].severity == "warning"
```

- [ ] **Step 2: Run mapping tests to verify red**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_field_mapping.py -v
```

Expected: FAIL because `resolve_rows_for_role` does not exist.

- [ ] **Step 3: Add default mapping file**

Create `src/trade_entity_graph/importers/field_mappings/default.json`:

```json
{
  "version": "default-v1",
  "roles": {
    "orders": {
      "required": ["order_id"],
      "fields": {
        "order_id": ["order_id", "订单号", "业务编号", "提单号", "so_no"],
        "customer_name": ["customer_name", "客户名称", "下单客户", "Booking Customer", "customer"],
        "shipper_name": ["shipper_name", "发货人", "Shipper", "shipper"],
        "consignee_name": ["consignee_name", "收货人", "Consignee", "consignee"],
        "notify_name": ["notify_name", "通知人", "Notify Party", "notify"],
        "teu": ["teu", "TEU", "箱量", "箱量TEU"],
        "product_name": ["product_name", "产品名称", "货品名称", "品名", "产品"],
        "function_category": ["function_category", "功能分类", "产品功能"],
        "destination_country": ["destination_country", "目的国", "目的国家"],
        "destination_port": ["destination_port", "目的港", "目的港口"],
        "order_date": ["order_date", "订单日期", "出运日期"]
      }
    },
    "entities": {
      "required": ["canonical_name"],
      "fields": {
        "canonical_name": ["canonical_name", "standard_name", "标准名", "企业标准名"],
        "original_name": ["original_name", "raw_name", "原始名", "原始企业名"],
        "clean_name": ["clean_name", "cleaned_name", "清洗名", "清洗后名称"],
        "alias_name": ["alias_name", "alias", "别名", "企业别名"],
        "country": ["country", "国家", "国家地区"],
        "entity_type": ["entity_type", "主体类型", "企业类型"]
      }
    },
    "relationships": {
      "required": [],
      "fields": {
        "from_entity_id": ["from_entity_id", "source_entity_id", "起点主体ID"],
        "to_entity_id": ["to_entity_id", "target_entity_id", "终点主体ID"],
        "from_entity_name": ["from_entity_name", "主体A", "企业A", "起点企业"],
        "to_entity_name": ["to_entity_name", "主体B", "企业B", "终点企业"],
        "candidate_relation_type": ["candidate_relation_type", "关系类型", "候选关系类型"],
        "confidence_level": ["confidence_level", "置信度等级", "置信等级"],
        "confidence_score": ["confidence_score", "置信度分数", "score"],
        "order_count": ["order_count", "订单数"],
        "total_teu": ["total_teu", "总TEU", "teu_total"],
        "recommendation_reason": ["recommendation_reason", "推荐理由", "reason"]
      }
    }
  }
}
```

- [ ] **Step 4: Implement mapping resolver**

Replace `src/trade_entity_graph/importers/field_mapping.py` with:

```python
"""Field alias helpers for import sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trade_entity_graph.importers.models import ImportErrorRecord, ImportSourceRow

_DEFAULT_MAPPING_PATH = Path(__file__).with_name("field_mappings") / "default.json"


def _load_default_mapping() -> dict[str, Any]:
    return json.loads(_DEFAULT_MAPPING_PATH.read_text(encoding="utf-8"))


FIELD_MAPPING = _load_default_mapping()
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    field_name: tuple(aliases)
    for role_config in FIELD_MAPPING["roles"].values()
    for field_name, aliases in role_config["fields"].items()
}


def normalize_key(value: str) -> str:
    """Normalize a source column name for alias matching."""

    return "".join(
        ch
        for ch in str(value).replace("\u3000", " ").strip().lower()
        if ch not in {" ", "_", "-"}
    )


def get_value(row: dict[str, Any], field_name: str, default: Any = None) -> Any:
    """Return a logical field value from a source row."""

    if field_name in row:
        return row.get(field_name, default)
    normalized_row = {normalize_key(key): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field_name]:
        normalized_alias = normalize_key(alias)
        if normalized_alias in normalized_row:
            return normalized_row[normalized_alias]
    return default


def _column_to_field(
    role_config: dict[str, Any], columns: list[str]
) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    alias_to_field = {
        normalize_key(alias): field_name
        for field_name, aliases in role_config["fields"].items()
        for alias in aliases
    }
    mapped: dict[str, str] = {}
    duplicates: list[tuple[str, str, str]] = []
    for column in columns:
        field_name = alias_to_field.get(normalize_key(column))
        if not field_name:
            continue
        if field_name in mapped:
            duplicates.append((field_name, mapped[field_name], column))
            continue
        mapped[field_name] = column
    return mapped, duplicates


def resolve_rows_for_role(
    rows: list[ImportSourceRow], *, role: str, run_id: str
) -> tuple[list[ImportSourceRow], list[ImportErrorRecord]]:
    """Return rows with normalized field keys and mapping diagnostics for one file role."""

    if not rows:
        return [], []

    role_config = FIELD_MAPPING["roles"][role]
    mapped, duplicates = _column_to_field(role_config, list(rows[0].values.keys()))
    errors: list[ImportErrorRecord] = []

    for field_name, first_column, duplicate_column in duplicates:
        errors.append(
            ImportErrorRecord(
                run_id=run_id,
                file_role=role,
                source_path=rows[0].source_file,
                sheet_name=rows[0].source_sheet,
                column_name=duplicate_column,
                normalized_field=field_name,
                raw_value=duplicate_column,
                error_type="field_mapping_error",
                severity="warning",
                message=f"字段 {duplicate_column} 与 {first_column} 同时映射到 {field_name}，已使用 {first_column}",
            )
        )

    missing_required = [
        field_name for field_name in role_config.get("required", []) if field_name not in mapped
    ]
    if missing_required:
        for field_name in missing_required:
            errors.append(
                ImportErrorRecord(
                    run_id=run_id,
                    file_role=role,
                    source_path=rows[0].source_file,
                    sheet_name=rows[0].source_sheet,
                    normalized_field=field_name,
                    error_type="missing_required_field",
                    severity="blocking",
                    message=f"导入文件缺少必需字段：{field_name}",
                )
            )
        return [], errors

    resolved_rows = [
        ImportSourceRow(
            source_file=row.source_file,
            source_sheet=row.source_sheet,
            source_row=row.source_row,
            values={field_name: row.values.get(column_name) for field_name, column_name in mapped.items()},
        )
        for row in rows
    ]
    return resolved_rows, errors
```

- [ ] **Step 5: Run mapping and import regression tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_field_mapping.py tests/test_import_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/trade_entity_graph/importers/field_mapping.py src/trade_entity_graph/importers/field_mappings/default.json tests/test_field_mapping.py
git commit -m "feat: add configurable import field mapping"
```

---

### Task 4: Loader And Pipeline Error Capture

**Files:**
- Modify: `src/trade_entity_graph/importers/entity_loader.py`
- Modify: `src/trade_entity_graph/importers/evidence_loader.py`
- Modify: `src/trade_entity_graph/importers/relationship_loader.py`
- Modify: `src/trade_entity_graph/importers/pipeline.py`
- Modify: `src/trade_entity_graph/importers/batch_loader.py`
- Modify: `tests/test_import_pipeline.py`

- [ ] **Step 1: Write failing mixed-quality import test**

Append to `tests/test_import_pipeline.py`:

```python
def test_run_import_records_errors_and_keeps_valid_rows(tmp_path, monkeypatch) -> None:
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.csv"
    relationships_path = tmp_path / "relationships.csv"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))

    pd.DataFrame(
        {"标准名": ["ACME TRADING", "BETA FACTORY", ""], "原始名": ["Acme Trading Ltd", "Beta Factory Inc", "Missing Name Ltd"]}
    ).to_csv(entities_path, index=False)
    pd.DataFrame(
        {
            "业务编号": ["SO-1", "SO-2", ""],
            "Booking Customer": ["Acme Trading Ltd", "Acme Trading Ltd", "Acme Trading Ltd"],
            "Shipper": ["Beta Factory Inc", "Beta Factory Inc", "Beta Factory Inc"],
            "Consignee": ["Beta Factory Inc", "Beta Factory Inc", "Beta Factory Inc"],
            "TEU": ["3.5", "not-a-number", "1.0"],
        }
    ).to_csv(orders_path, index=False)
    pd.DataFrame(
        {"主体A": ["ACME TRADING", "UNKNOWN CO"], "主体B": ["BETA FACTORY", "BETA FACTORY"], "关系类型": ["trading_partner_candidate", "trading_partner_candidate"]}
    ).to_csv(relationships_path, index=False)

    result = run_import(
        ImportInputs(entities_path=entities_path, orders_path=orders_path, relationships_path=relationships_path, imported_by="tester"),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        evidence_count = connection.execute("SELECT COUNT(*) FROM order_evidence").fetchone()[0]
        claim_count = connection.execute("SELECT COUNT(*) FROM relationship_claim").fetchone()[0]
        errors = connection.execute(
            """
            SELECT error_type, severity
            FROM import_error
            WHERE run_id = ?
            ORDER BY file_role, row_number, normalized_field
            """,
            (result.run_id,),
        ).fetchall()
        batch = connection.execute(
            "SELECT success_rows, error_rows, warning_rows FROM import_batch WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()

    assert evidence_count == 1
    assert claim_count == 1
    assert result.error_count == 4
    assert result.warning_count == 0
    assert batch["success_rows"] == 4
    assert batch["error_rows"] == 4
    assert [row["error_type"] for row in errors] == [
        "missing_required_value",
        "invalid_numeric_value",
        "missing_required_value",
        "unknown_entity_reference",
    ]
```

- [ ] **Step 2: Run the mixed-quality test to verify red**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_import_pipeline.py::test_run_import_records_errors_and_keeps_valid_rows -v
```

Expected: FAIL because loaders do not yet produce structured import errors.

- [ ] **Step 3: Update `finish_import_batch`**

In `src/trade_entity_graph/importers/batch_loader.py`, replace `finish_import_batch` with:

```python
def finish_import_batch(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    success_rows: int,
    error_rows: int,
    warning_rows: int = 0,
    error_summary: str | None,
) -> None:
    """Update import row counts after loaders finish."""

    connection.execute(
        """
        UPDATE import_batch
        SET success_rows = ?, error_rows = ?, warning_rows = ?, error_summary = ?
        WHERE run_id = ?
        """,
        (success_rows, error_rows, warning_rows, error_summary, run_id),
    )
    connection.commit()
```

- [ ] **Step 4: Extend loader result dataclasses**

In `entity_loader.py`, `evidence_loader.py`, and `relationship_loader.py`, add `import_errors` to each result dataclass:

```python
    import_errors: list[ImportErrorRecord] = field(default_factory=list)
```

Each file must import `ImportErrorRecord` from `trade_entity_graph.importers.models`.

- [ ] **Step 5: Capture entity, evidence, and relationship errors**

Use this exact error construction pattern in each loader, with `file_role` set to `entities`, `orders`, or `relationships`:

```python
ImportErrorRecord(
    run_id=run_id,
    file_role="orders",
    source_path=row.source_file,
    sheet_name=row.source_sheet,
    row_number=row.source_row,
    normalized_field="teu",
    raw_value=get_value(row.values, "teu"),
    error_type="invalid_numeric_value",
    severity="blocking",
    message="TEU 必须是数字",
)
```

Required loader behavior:

- `entity_loader.load_entities`: missing `canonical_name` appends `missing_required_value` and skips that row.
- `evidence_loader.load_order_evidence`: missing `order_id` appends `missing_required_value`; invalid TEU appends `invalid_numeric_value`; both skip that row.
- `relationship_loader.load_relationship_claims`: resolve `from_entity_name` and `to_entity_name` through `find_entity_id_by_name` when IDs are absent; unknown endpoints append `unknown_entity_reference`; self-pairs append `invalid_relationship_pair`.

For TEU parsing, add this helper in `evidence_loader.py`:

```python
def _safe_float(value: Any) -> tuple[float | None, bool]:
    if value in (None, ""):
        return None, True
    try:
        return float(value), True
    except (TypeError, ValueError):
        return None, False
```

- [ ] **Step 6: Wire field mapping and error persistence in pipeline**

In `pipeline.py`, import:

```python
from trade_entity_graph.importers.field_mapping import resolve_rows_for_role
from trade_entity_graph.importers.import_error_loader import write_import_errors
from trade_entity_graph.importers.models import ImportErrorRecord, ImportInputs, ImportRunResult
```

Inside `run_import`, create `collected_errors: list[ImportErrorRecord] = []`, call `resolve_rows_for_role(..., role="entities" | "orders" | "relationships", run_id=run_id)` before each loader, append mapping and loader errors, then persist and summarize:

```python
write_import_errors(connection, collected_errors)
result.import_errors = [record.as_dict() for record in collected_errors]
result.error_count = sum(1 for record in collected_errors if record.severity == "blocking")
result.warning_count = sum(1 for record in collected_errors if record.severity == "warning")
result.quality_summary = {
    "blocking_error_count": result.error_count,
    "warning_count": result.warning_count,
    "error_count_by_type": {
        error_type: sum(1 for record in collected_errors if record.error_type == error_type)
        for error_type in sorted({record.error_type for record in collected_errors})
    },
}
finish_import_batch(
    connection,
    run_id,
    success_rows=result.entity_count + result.evidence_count + result.claim_count,
    error_rows=result.error_count,
    warning_rows=result.warning_count,
    error_summary="; ".join(result.skipped_rows) if result.skipped_rows else None,
)
```

- [ ] **Step 7: Run import tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_import_pipeline.py tests/test_relationship_service.py tests/test_demo_acceptance.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/trade_entity_graph/importers/entity_loader.py src/trade_entity_graph/importers/evidence_loader.py src/trade_entity_graph/importers/relationship_loader.py src/trade_entity_graph/importers/pipeline.py src/trade_entity_graph/importers/batch_loader.py tests/test_import_pipeline.py
git commit -m "feat: capture import row quality errors"
```

---

### Task 5: Import Quality Service

**Files:**
- Create: `src/trade_entity_graph/services/import_quality_service.py`
- Create: `tests/test_import_quality_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_import_quality_service.py` with one seed helper and these assertions:

```python
from pathlib import Path

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.import_quality_service import (
    export_import_errors,
    get_import_batch_detail,
    get_import_quality_report,
    list_import_batches,
    list_import_errors,
)


def _seed_import_quality_fixture(db_path: Path) -> None:
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute("INSERT INTO import_batch (run_id, source_file, imported_by, success_rows, error_rows, warning_rows) VALUES ('RUN_QA', 'orders.csv', 'tester', 3, 1, 1)")
        connection.execute("INSERT INTO import_source_file (source_file_id, run_id, source_role, original_path, archived_path, file_name, file_size_bytes, sha256) VALUES ('SRC_QA', 'RUN_QA', 'orders', 'orders.csv', 'archive/orders.csv', 'orders.csv', 128, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')")
        connection.execute("INSERT INTO entity (entity_id, canonical_name) VALUES ('ENT_A', 'ACME'), ('ENT_B', 'BETA')")
        connection.execute("INSERT INTO order_evidence (evidence_id, order_id, run_id) VALUES ('EVD_QA', 'SO-1', 'RUN_QA')")
        connection.execute("INSERT INTO relationship_claim (claim_id, from_entity_id, to_entity_id, candidate_relation_type, run_id) VALUES ('CLM_QA', 'ENT_A', 'ENT_B', 'trading_partner_candidate', 'RUN_QA')")
        connection.execute(
            """
            INSERT INTO import_error (error_id, run_id, file_role, source_path, sheet_name, row_number, column_name, normalized_field, raw_value, error_type, severity, message)
            VALUES
                ('IER_BLOCK', 'RUN_QA', 'orders', 'orders.csv', 'orders', 3, 'TEU', 'teu', 'abc', 'invalid_numeric_value', 'blocking', 'TEU 必须是数字'),
                ('IER_WARN', 'RUN_QA', 'entities', 'entities.csv', 'entities', NULL, '企业标准名', 'canonical_name', '企业标准名', 'field_mapping_error', 'warning', '重复映射')
            """
        )
        connection.commit()


def test_import_quality_service_reports_counts_and_exports(tmp_path) -> None:
    db_path = tmp_path / "quality.db"
    output_path = tmp_path / "errors.csv"
    _seed_import_quality_fixture(db_path)

    batches = list_import_batches(db_path=db_path)
    detail = get_import_batch_detail("RUN_QA", db_path=db_path)
    errors = list_import_errors("RUN_QA", severity="blocking", db_path=db_path)
    report = get_import_quality_report("RUN_QA", db_path=db_path)
    export = export_import_errors("RUN_QA", output_path=output_path, db_path=db_path)

    assert batches["items"][0]["blocking_error_count"] == 1
    assert detail["counts"]["order_evidence"] == 1
    assert detail["quality_summary"]["warning_count"] == 1
    assert errors["items"][0]["error_type"] == "invalid_numeric_value"
    assert report["quality_summary"]["error_count_by_type"] == {"field_mapping_error": 1, "invalid_numeric_value": 1}
    assert export["row_count"] == 2
    assert "invalid_numeric_value" in output_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run service tests to verify red**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_import_quality_service.py -v
```

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement service**

Create `src/trade_entity_graph/services/import_quality_service.py` with these public functions:

```python
def list_import_batches(*, limit: int = 20, offset: int = 0, status: str | None = None, db_path: str | Path | None = None) -> dict[str, Any]: ...
def get_import_batch_detail(run_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]: ...
def list_import_errors(run_id: str, *, severity: str | None = None, error_type: str | None = None, limit: int = 200, offset: int = 0, db_path: str | Path | None = None) -> dict[str, Any]: ...
def get_import_quality_report(run_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]: ...
def export_import_errors(run_id: str, *, output_path: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, Any]: ...
```

Implementation requirements:

- `list_import_batches` returns `{"summary": {"total_count": int}, "items": list[dict]}` ordered by `imported_at DESC, run_id DESC`.
- `get_import_batch_detail` returns `batch`, `archived_files`, `counts`, and `quality_summary`.
- `counts` includes `order_evidence`, `order_role_edges`, and `relationship_claims`.
- `quality_summary` includes `blocking_error_count`, `warning_count`, `error_count_by_type`, and `error_count_by_severity`.
- `list_import_errors` supports `severity`, `error_type`, `limit`, and `offset`.
- `export_import_errors` writes UTF-8-SIG CSV to `data/exports/<run_id>_import_errors.csv` when `output_path` is absent.

Use only parameterized SQL for user-provided values. The only SQL string interpolation allowed is the internally assembled `WHERE` clause from fixed clause fragments.

- [ ] **Step 4: Run service tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_import_quality_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/trade_entity_graph/services/import_quality_service.py tests/test_import_quality_service.py
git commit -m "feat: add import quality service"
```

---

### Task 6: Import Quality API

**Files:**
- Modify: `src/trade_entity_graph/api/routers/imports.py`
- Modify: `tests/test_api_p0.py`

- [ ] **Step 1: Write failing API tests**

Append to `tests/test_api_p0.py`:

```python
def test_imports_api_lists_batches_with_quality_summary(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "api-import-list.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute("INSERT INTO import_batch (run_id, source_file, imported_by, success_rows, error_rows, warning_rows) VALUES ('RUN_API_IMPORTS', 'orders.csv', 'tester', 1, 1, 0)")
        connection.execute("INSERT INTO import_error (error_id, run_id, file_role, source_path, sheet_name, row_number, normalized_field, raw_value, error_type, severity, message) VALUES ('IER_API_IMPORTS', 'RUN_API_IMPORTS', 'orders', 'orders.csv', 'orders', 3, 'teu', 'abc', 'invalid_numeric_value', 'blocking', 'TEU 必须是数字')")
        connection.commit()

    from trade_entity_graph.api.main import create_app

    status, payload = _request(create_app(), "GET", "/imports")

    assert status == 200
    assert payload["summary"]["total_count"] == 1
    assert payload["items"][0]["run_id"] == "RUN_API_IMPORTS"
    assert payload["items"][0]["blocking_error_count"] == 1


def test_imports_api_returns_batch_errors(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "api-import-errors.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute("INSERT INTO import_batch (run_id, source_file, imported_by) VALUES ('RUN_API_ERRORS', 'orders.csv', 'tester')")
        connection.execute("INSERT INTO import_error (error_id, run_id, file_role, source_path, sheet_name, row_number, normalized_field, raw_value, error_type, severity, message) VALUES ('IER_API_ERRORS', 'RUN_API_ERRORS', 'orders', 'orders.csv', 'orders', 3, 'teu', 'abc', 'invalid_numeric_value', 'blocking', 'TEU 必须是数字')")
        connection.commit()

    from trade_entity_graph.api.main import create_app

    status, payload = _request(create_app(), "GET", "/imports/RUN_API_ERRORS/errors", query={"severity": "blocking"})

    assert status == 200
    assert payload["summary"]["total_count"] == 1
    assert payload["items"][0]["error_type"] == "invalid_numeric_value"
```

- [ ] **Step 2: Run API tests to verify red**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_api_p0.py::test_imports_api_lists_batches_with_quality_summary tests/test_api_p0.py::test_imports_api_returns_batch_errors -v
```

Expected: FAIL because API endpoints do not exist.

- [ ] **Step 3: Add endpoints**

In `src/trade_entity_graph/api/routers/imports.py`, import:

```python
from trade_entity_graph.services.import_quality_service import (
    get_import_batch_detail,
    get_import_quality_report,
    list_import_batches,
    list_import_errors,
)
```

Add before `@router.post("/run")`:

```python
@router.get("")
def list_import_batches_endpoint(limit: int = 20, offset: int = 0, status: str | None = None) -> dict[str, object]:
    return list_import_batches(limit=limit, offset=offset, status=status)


@router.get("/{run_id}")
def get_import_batch_endpoint(run_id: str) -> dict[str, object]:
    return get_import_batch_detail(run_id)


@router.get("/{run_id}/errors")
def list_import_errors_endpoint(
    run_id: str,
    severity: str | None = None,
    error_type: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, object]:
    return list_import_errors(run_id, severity=severity, error_type=error_type, limit=limit, offset=offset)


@router.get("/{run_id}/quality-report")
def get_import_quality_report_endpoint(run_id: str) -> dict[str, object]:
    return get_import_quality_report(run_id)
```

Extend `/imports/run` response with:

```python
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "import_errors": result.import_errors,
        "quality_summary": result.quality_summary,
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_api_p0.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/trade_entity_graph/api/routers/imports.py tests/test_api_p0.py
git commit -m "feat: expose import quality endpoints"
```

---

### Task 7: Streamlit Import Quality UI

**Files:**
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Modify: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write failing helper tests**

Append to `tests/test_streamlit_app.py`:

```python
def test_import_quality_status_label_distinguishes_errors_and_warnings() -> None:
    assert streamlit_app.format_import_quality_status({"blocking_error_count": 0, "warning_count": 0}) == "无异常"
    assert streamlit_app.format_import_quality_status({"blocking_error_count": 0, "warning_count": 2}) == "仅警告：2 条"
    assert streamlit_app.format_import_quality_status({"blocking_error_count": 3, "warning_count": 2}) == "阻断异常：3 条，警告：2 条"


def test_import_error_export_filename_uses_run_id() -> None:
    assert streamlit_app.import_error_export_filename("RUN_ABC") == "RUN_ABC_import_errors.csv"
```

- [ ] **Step 2: Run helper tests to verify red**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_streamlit_app.py::test_import_quality_status_label_distinguishes_errors_and_warnings tests/test_streamlit_app.py::test_import_error_export_filename_uses_run_id -v
```

Expected: FAIL because helpers do not exist.

- [ ] **Step 3: Add helpers and labels**

In `streamlit_app.py`, import:

```python
from trade_entity_graph.services.import_quality_service import (
    export_import_errors,
    get_import_batch_detail,
    list_import_batches,
    list_import_errors,
)
```

Add these helper functions near other formatting helpers:

```python
def format_import_quality_status(summary: dict[str, Any]) -> str:
    """Return a short Chinese status label for an import quality summary."""

    blocking_count = int(summary.get("blocking_error_count") or 0)
    warning_count = int(summary.get("warning_count") or 0)
    if blocking_count == 0 and warning_count == 0:
        return "无异常"
    if blocking_count == 0:
        return f"仅警告：{warning_count} 条"
    return f"阻断异常：{blocking_count} 条，警告：{warning_count} 条"


def import_error_export_filename(run_id: str) -> str:
    """Return the CSV filename used for one import error export."""

    return f"{run_id}_import_errors.csv"
```

Extend `TABLE_COLUMN_LABELS` with import quality fields: `source_role`, `original_path`, `archived_path`, `success_rows`, `error_rows`, `warning_rows`, `blocking_error_count`, `warning_count`, `file_role`, `sheet_name`, `row_number`, `column_name`, `normalized_field`, `raw_value`, `error_type`, `severity`, `message`.

Extend `DISPLAY_VALUE_LABELS` for `severity` and `error_type`:

```python
    "severity": {"blocking": "阻断异常", "warning": "警告"},
    "error_type": {
        "missing_required_field": "缺少必需字段",
        "missing_required_value": "必填值为空",
        "unknown_entity_reference": "企业无法匹配",
        "invalid_numeric_value": "数值格式错误",
        "invalid_relationship_pair": "无效关系企业对",
        "field_mapping_error": "字段映射警告",
    },
```

- [ ] **Step 4: Enhance `render_import_tab`**

After the existing import result JSON, add:

```python
        quality_summary = getattr(result, "quality_summary", {}) or {}
        if quality_summary:
            st.markdown("**导入质量摘要**")
            st.info(format_import_quality_status(quality_summary))
            show_table([
                {"error_type": key, "数量": value}
                for key, value in quality_summary.get("error_count_by_type", {}).items()
            ])
        if getattr(result, "import_errors", None):
            with st.expander("查看本次导入异常"):
                show_table(result.import_errors)
```

Below the import button block, add:

```python
    st.markdown("---")
    st.subheader("最近导入批次")
    batches = list_import_batches(limit=10)
    show_table(batches.get("items", []))
    selected_run_id = st.text_input("查看批次详情的 run_id")
    if selected_run_id:
        detail = get_import_batch_detail(selected_run_id)
        st.markdown("**批次质量状态**")
        st.info(format_import_quality_status(detail.get("quality_summary", {})))
        st.markdown("**归档文件**")
        show_table(detail.get("archived_files", []))
        st.markdown("**导入计数**")
        st.json(detail.get("counts", {}))
        error_result = list_import_errors(selected_run_id, limit=500)
        error_items = error_result.get("items", [])
        st.markdown("**导入异常**")
        show_table(error_items)
        if error_items:
            export_result = export_import_errors(selected_run_id)
            export_path = Path(str(export_result["path"]))
            st.download_button(
                "下载异常 CSV",
                data=export_path.read_bytes(),
                file_name=import_error_export_filename(selected_run_id),
                mime="text/csv",
            )
```

- [ ] **Step 5: Update Streamlit fake tests**

In `test_import_tab_applies_history_reuse_after_generated_claims`, add fake `markdown`, `expander`, and `download_button` methods; add `import_errors`, `error_count`, `warning_count`, and `quality_summary` attributes to the fake import result; patch:

```python
monkeypatch.setattr(streamlit_app, "list_import_batches", lambda limit=10: {"items": []})
```

- [ ] **Step 6: Run Streamlit tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests/test_streamlit_app.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/trade_entity_graph/ui/streamlit_app.py tests/test_streamlit_app.py
git commit -m "feat: show import quality in Streamlit"
```

---

### Task 8: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/task-breakdown.md`

- [ ] **Step 1: Update Chinese README**

In `README.md`, update the current development status sentence to include:

```markdown
以及 M9 真实数据试运行与导入质量闭环。M9 支持字段映射配置、行级导入异常记录、导入批次查询、质量报告和异常 CSV 导出。
```

Add a short M9 subsection:

```markdown
### M9 真实数据导入质量闭环

M9 面向真实 Excel/CSV 试运行：导入时会按默认字段映射识别常见中英文字段别名，并把字段缺失、必填值为空、TEU 格式错误、未知企业引用、无效关系企业对等问题写入 `import_error`。

可通过 API 查看导入批次和质量报告：`GET /imports`、`GET /imports/{run_id}`、`GET /imports/{run_id}/errors`、`GET /imports/{run_id}/quality-report`。
```

- [ ] **Step 2: Update English README**

In `README.en.md`, add:

```markdown
M9 adds the real-data import QA loop: configurable field mapping, row-level import errors, import batch queries, quality reports, and import-error CSV export.
```

- [ ] **Step 3: Update task breakdown**

In `docs/task-breakdown.md`, add M9 to the milestone table:

```markdown
| M9 | 真实数据试运行与导入质量闭环 | 支持真实文件字段映射、行级异常沉淀、批次查询、质量报告和异常导出 | P1 | 真实脏数据可部分导入，异常可追溯、可查询、可导出 |
```

Append current status:

```markdown
- M9：支持默认字段映射配置、导入行级异常记录、导入批次查询、质量报告和异常 CSV 导出，真实数据试运行时可保留有效行并沉淀坏行原因。
```

- [ ] **Step 4: Run full verification**

Run:

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Expected: all tests PASS and ruff prints `All checks passed!`.

- [ ] **Step 5: Commit docs**

```powershell
git add README.md README.en.md docs/task-breakdown.md
git commit -m "docs: document M9 import quality workflow"
```

---

## Final Verification

Run these commands before reporting completion:

```powershell
git status --short
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Expected:

- `git status --short` is clean after the last commit.
- `pytest` passes.
- `ruff` prints `All checks passed!`.

## Self-Review

- Spec coverage: Tasks cover schema, field mapping, row-level import errors, batch query service, API endpoints, Streamlit quality UI, CSV error export, tests, and documentation.
- Scope check: The plan excludes React, PostgreSQL, permissions, path search, two-hop graph expansion, and public web verification.
- Type consistency: `ImportErrorRecord`, `quality_summary`, `error_count`, `warning_count`, `list_import_batches`, `get_import_batch_detail`, `list_import_errors`, `get_import_quality_report`, and `export_import_errors` use consistent names across tasks.
- No unresolved markers remain in this plan.
