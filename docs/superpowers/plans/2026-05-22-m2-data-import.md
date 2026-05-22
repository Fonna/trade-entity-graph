# M2 Data Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M2 import foundation that reads Excel/CSV inputs and writes `import_batch`, `entity`, `entity_alias`, `order_evidence`, and optional `relationship_claim` records into SQLite.

**Architecture:** Keep import code in `src/trade_entity_graph/importers/` with small loaders per target table and one orchestration module. Read tabular files into source-row objects, resolve fields through explicit aliases, and pass normalized rows into loaders that use the existing SQLite connection helpers. This plan deliberately stops before M3 order-role edge generation.

**Tech Stack:** Python 3.12 via `uv`, SQLite, pandas/openpyxl for Excel and CSV reads, pytest for TDD, ruff for linting.

---

## Scope

M2 includes these P0 outcomes from `docs/task-breakdown.md`:

- `IMP-01`: Read order standardization Excel/CSV files and report workbook/sheet metadata.
- `IMP-02`: Read entity cleaning results and create `entity` plus `entity_alias` records.
- `IMP-03`: Read existing relationship candidate results and create `relationship_claim` records.
- `IMP-04`: Create a unique `run_id` in `import_batch` for each import run.
- M2 acceptance: generate `import_batch`, `entity`, `entity_alias`, and `order_evidence` from a minimal sample.

Out of scope for this plan:

- M3 `order_role_edge` generation.
- M4 candidate scoring derived from role edges.
- API endpoints and Streamlit pages.
- Two-hop graph query or path query.

## File Structure

- Create `src/trade_entity_graph/importers/models.py`: shared dataclasses for source rows and import results.
- Create `src/trade_entity_graph/importers/field_mapping.py`: field alias resolution for known source columns.
- Modify `src/trade_entity_graph/importers/excel_importer.py`: inspect and read Excel/CSV into source rows.
- Create `src/trade_entity_graph/importers/batch_loader.py`: insert `import_batch` rows.
- Modify `src/trade_entity_graph/importers/entity_loader.py`: load entities and aliases.
- Create `src/trade_entity_graph/importers/evidence_loader.py`: load order evidence.
- Modify `src/trade_entity_graph/importers/relationship_loader.py`: load existing relationship candidates.
- Create `src/trade_entity_graph/importers/pipeline.py`: orchestrate an import run.
- Modify `scripts/import_workbook.py`: expose import-run CLI options while keeping inspect mode.
- Create focused tests: `tests/test_field_mapping.py`, `tests/test_excel_importer.py`, `tests/test_batch_loader.py`, `tests/test_entity_loader.py`, `tests/test_evidence_loader.py`, `tests/test_relationship_loader.py`, and `tests/test_import_pipeline.py`.

---

### Task 1: Field Mapping Foundation

**Files:**
- Create: `src/trade_entity_graph/importers/models.py`
- Create: `src/trade_entity_graph/importers/field_mapping.py`
- Test: `tests/test_field_mapping.py`

- [ ] **Step 1: Write the failing field mapping tests**

Create `tests/test_field_mapping.py`:

```python
from trade_entity_graph.importers.field_mapping import get_value, normalize_key


def test_normalize_key_removes_spaces_and_common_separators() -> None:
    assert normalize_key(" Customer Name ") == "customername"
    assert normalize_key("客户-名称") == "客户名称"


def test_get_value_reads_first_matching_alias() -> None:
    row = {"客户名称": "ACME Trading", "TEU": 2.5}

    assert get_value(row, "customer_name") == "ACME Trading"
    assert get_value(row, "teu") == 2.5


def test_get_value_returns_default_for_missing_field() -> None:
    assert get_value({"订单号": "SO-1"}, "destination_country", default="") == ""
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_field_mapping.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'trade_entity_graph.importers.field_mapping'`.

- [ ] **Step 3: Add source-row models**

Create `src/trade_entity_graph/importers/models.py`:

```python
"""Shared import models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ImportSourceRow:
    """One row read from a source workbook or CSV file."""

    source_file: str
    source_sheet: str
    source_row: int
    values: dict[str, Any]


@dataclass(frozen=True)
class ImportInputs:
    """Input files used by one M2 import run."""

    orders_path: Path | None = None
    entities_path: Path | None = None
    relationships_path: Path | None = None
    imported_by: str = "local_user"


@dataclass
class ImportRunResult:
    """Summary returned after an import run."""

    run_id: str
    entity_count: int = 0
    alias_count: int = 0
    evidence_count: int = 0
    claim_count: int = 0
    skipped_rows: list[str] = field(default_factory=list)
```

- [ ] **Step 4: Add field alias resolution**

Create `src/trade_entity_graph/importers/field_mapping.py`:

```python
"""Field alias helpers for import sources."""

from __future__ import annotations

from typing import Any

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "canonical_name": ("canonical_name", "standard_name", "标准名", "企业标准名"),
    "original_name": ("original_name", "raw_name", "原始名", "原始企业名"),
    "clean_name": ("clean_name", "cleaned_name", "清洗名", "清洗后名称"),
    "alias_name": ("alias_name", "alias", "别名", "企业别名"),
    "country": ("country", "国家", "国家地区"),
    "entity_type": ("entity_type", "主体类型", "企业类型"),
    "order_id": ("order_id", "订单号", "业务编号", "so_no"),
    "customer_name": ("customer_name", "客户名称", "下单客户"),
    "shipper_name": ("shipper_name", "发货人", "shipper"),
    "consignee_name": ("consignee_name", "收货人", "consignee"),
    "notify_name": ("notify_name", "通知人", "notify"),
    "teu": ("teu", "TEU", "箱量TEU"),
    "product_name": ("product_name", "产品名称", "货品名称"),
    "function_category": ("function_category", "功能分类", "产品功能"),
    "destination_country": ("destination_country", "目的国", "目的国家"),
    "destination_port": ("destination_port", "目的港", "目的港口"),
    "order_date": ("order_date", "订单日期", "出运日期"),
    "from_entity_id": ("from_entity_id", "source_entity_id", "起点主体ID"),
    "to_entity_id": ("to_entity_id", "target_entity_id", "终点主体ID"),
    "candidate_relation_type": ("candidate_relation_type", "关系类型", "候选关系类型"),
    "confidence_level": ("confidence_level", "置信度等级", "置信等级"),
    "confidence_score": ("confidence_score", "置信度分数", "score"),
    "order_count": ("order_count", "订单数"),
    "total_teu": ("total_teu", "总TEU", "teu_total"),
    "recommendation_reason": ("recommendation_reason", "推荐理由", "reason"),
}


def normalize_key(value: str) -> str:
    """Normalize a source column name for alias matching."""

    return "".join(ch for ch in value.strip().lower() if ch not in {" ", "_", "-"})


def get_value(row: dict[str, Any], field_name: str, default: Any = None) -> Any:
    """Return the value for a logical field from a source row."""

    normalized_row = {normalize_key(key): value for key, value in row.items()}
    for alias in FIELD_ALIASES[field_name]:
        value = normalized_row.get(normalize_key(alias), default)
        if value is not default:
            return value
    return default
```

- [ ] **Step 5: Run the tests and verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_field_mapping.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/trade_entity_graph/importers/models.py src/trade_entity_graph/importers/field_mapping.py tests/test_field_mapping.py
git commit -m "feat: add import field mapping foundation"
```

---

### Task 2: Workbook and CSV Reader

**Files:**
- Modify: `src/trade_entity_graph/importers/excel_importer.py`
- Test: `tests/test_excel_importer.py`

- [ ] **Step 1: Write failing reader tests**

Create `tests/test_excel_importer.py`:

```python
import pandas as pd

from trade_entity_graph.importers.excel_importer import inspect_workbook, read_tabular_rows


def test_inspect_workbook_reports_excel_sheets(tmp_path) -> None:
    workbook = tmp_path / "orders.xlsx"
    frame = pd.DataFrame({"订单号": ["SO-1", "SO-2"], "TEU": [1.0, 2.0]})
    with pd.ExcelWriter(workbook) as writer:
        frame.to_excel(writer, index=False, sheet_name="Orders")

    metadata = inspect_workbook(workbook)

    assert metadata["name"] == "orders.xlsx"
    assert metadata["suffix"] == ".xlsx"
    assert metadata["sheets"] == [
        {"name": "Orders", "rows": 2, "columns": ["订单号", "TEU"]}
    ]


def test_read_tabular_rows_reads_excel_source_context(tmp_path) -> None:
    workbook = tmp_path / "orders.xlsx"
    pd.DataFrame({"订单号": ["SO-1"], "TEU": [1.0]}).to_excel(
        workbook, index=False, sheet_name="Orders"
    )

    rows = read_tabular_rows(workbook, sheet_name="Orders")

    assert len(rows) == 1
    assert rows[0].source_file == "orders.xlsx"
    assert rows[0].source_sheet == "Orders"
    assert rows[0].source_row == 2
    assert rows[0].values["订单号"] == "SO-1"


def test_read_tabular_rows_reads_csv_source_context(tmp_path) -> None:
    csv_path = tmp_path / "entities.csv"
    pd.DataFrame({"标准名": ["ACME TRADING"], "原始名": ["Acme Trading Ltd"]}).to_csv(
        csv_path, index=False
    )

    rows = read_tabular_rows(csv_path)

    assert len(rows) == 1
    assert rows[0].source_file == "entities.csv"
    assert rows[0].source_sheet == "entities"
    assert rows[0].source_row == 2
    assert rows[0].values["标准名"] == "ACME TRADING"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_excel_importer.py -v
```

Expected: FAIL because `inspect_workbook` does not return `sheets` and `read_tabular_rows` does not exist.

- [ ] **Step 3: Implement the reader**

Replace `src/trade_entity_graph/importers/excel_importer.py` with:

```python
"""Excel and CSV import entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from trade_entity_graph.importers.models import ImportSourceRow

EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
CSV_SUFFIXES = {".csv"}


def _clean_cell(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value


def _dataframe_to_rows(frame: pd.DataFrame, path: Path, sheet_name: str) -> list[ImportSourceRow]:
    rows: list[ImportSourceRow] = []
    for offset, record in enumerate(frame.to_dict(orient="records"), start=2):
        values = {str(key): _clean_cell(value) for key, value in record.items()}
        rows.append(ImportSourceRow(path.name, sheet_name, offset, values))
    return rows


def inspect_workbook(path: str | Path) -> dict[str, object]:
    """Return workbook metadata for import pre-checks."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)

    suffix = target.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        workbook = pd.ExcelFile(target)
        sheets = []
        for sheet_name in workbook.sheet_names:
            frame = workbook.parse(sheet_name=sheet_name)
            sheets.append(
                {
                    "name": sheet_name,
                    "rows": int(len(frame)),
                    "columns": [str(column) for column in frame.columns],
                }
            )
    elif suffix in CSV_SUFFIXES:
        frame = pd.read_csv(target)
        sheets = [
            {
                "name": target.stem,
                "rows": int(len(frame)),
                "columns": [str(column) for column in frame.columns],
            }
        ]
    else:
        raise ValueError(f"Unsupported import file suffix: {target.suffix}")

    return {"path": str(target), "name": target.name, "suffix": target.suffix, "sheets": sheets}


def read_tabular_rows(path: str | Path, sheet_name: str | None = None) -> list[ImportSourceRow]:
    """Read an Excel sheet or CSV file into source rows."""

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)

    suffix = target.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        workbook = pd.ExcelFile(target)
        selected_sheet = sheet_name or workbook.sheet_names[0]
        frame = workbook.parse(sheet_name=selected_sheet)
        return _dataframe_to_rows(frame, target, selected_sheet)

    if suffix in CSV_SUFFIXES:
        frame = pd.read_csv(target)
        return _dataframe_to_rows(frame, target, target.stem)

    raise ValueError(f"Unsupported import file suffix: {target.suffix}")
```

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_excel_importer.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/trade_entity_graph/importers/excel_importer.py tests/test_excel_importer.py
git commit -m "feat: read Excel and CSV import rows"
```

---

### Task 3: Import Batch Loader

**Files:**
- Create: `src/trade_entity_graph/importers/batch_loader.py`
- Test: `tests/test_batch_loader.py`

- [ ] **Step 1: Write failing batch loader tests**

Create `tests/test_batch_loader.py`:

```python
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.batch_loader import create_import_batch, finish_import_batch


def test_create_import_batch_persists_run_context(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        run_id = create_import_batch(
            connection,
            source_file="orders.xlsx",
            source_path="D:/data/orders.xlsx",
            imported_by="tester",
            field_mapping_version="mvp-0.1",
            rule_version="mvp-0.1",
        )
        row = connection.execute("SELECT * FROM import_batch WHERE run_id = ?", (run_id,)).fetchone()

    assert run_id.startswith("RUN_")
    assert row["source_file"] == "orders.xlsx"
    assert row["imported_by"] == "tester"
    assert row["success_rows"] == 0
    assert row["error_rows"] == 0


def test_finish_import_batch_updates_counts(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        run_id = create_import_batch(
            connection,
            source_file="orders.xlsx",
            source_path=None,
            imported_by="tester",
            field_mapping_version="mvp-0.1",
            rule_version="mvp-0.1",
        )
        finish_import_batch(connection, run_id, success_rows=3, error_rows=1, error_summary="1 skipped")
        row = connection.execute("SELECT * FROM import_batch WHERE run_id = ?", (run_id,)).fetchone()

    assert row["success_rows"] == 3
    assert row["error_rows"] == 1
    assert row["error_summary"] == "1 skipped"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_batch_loader.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'trade_entity_graph.importers.batch_loader'`.

- [ ] **Step 3: Implement the batch loader**

Create `src/trade_entity_graph/importers/batch_loader.py`:

```python
"""Import batch persistence."""

from __future__ import annotations

import sqlite3

from trade_entity_graph.utils.ids import new_id


def create_import_batch(
    connection: sqlite3.Connection,
    *,
    source_file: str,
    source_path: str | None,
    imported_by: str,
    field_mapping_version: str,
    rule_version: str,
) -> str:
    """Insert one import batch and return its run id."""

    run_id = new_id("RUN")
    connection.execute(
        """
        INSERT INTO import_batch (
            run_id, source_file, source_path, imported_by, field_mapping_version, rule_version
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (run_id, source_file, source_path, imported_by, field_mapping_version, rule_version),
    )
    connection.commit()
    return run_id


def finish_import_batch(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    success_rows: int,
    error_rows: int,
    error_summary: str | None,
) -> None:
    """Update import row counts after loaders finish."""

    connection.execute(
        """
        UPDATE import_batch
        SET success_rows = ?, error_rows = ?, error_summary = ?
        WHERE run_id = ?
        """,
        (success_rows, error_rows, error_summary, run_id),
    )
    connection.commit()
```

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_batch_loader.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/trade_entity_graph/importers/batch_loader.py tests/test_batch_loader.py
git commit -m "feat: persist import batches"
```

---

### Task 4: Entity and Order Evidence Loaders

**Files:**
- Modify: `src/trade_entity_graph/importers/entity_loader.py`
- Create: `src/trade_entity_graph/importers/evidence_loader.py`
- Test: `tests/test_entity_loader.py`
- Test: `tests/test_evidence_loader.py`

- [ ] **Step 1: Write failing entity loader tests**

Create `tests/test_entity_loader.py`:

```python
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.batch_loader import create_import_batch
from trade_entity_graph.importers.entity_loader import load_entities
from trade_entity_graph.importers.models import ImportSourceRow


def test_load_entities_creates_entity_and_aliases(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        run_id = create_import_batch(
            connection,
            source_file="entities.csv",
            source_path=None,
            imported_by="tester",
            field_mapping_version="mvp-0.1",
            rule_version="mvp-0.1",
        )
        result = load_entities(
            connection,
            [
                ImportSourceRow(
                    "entities.csv",
                    "entities",
                    2,
                    {"标准名": "ACME TRADING", "原始名": "Acme Trading Ltd", "清洗名": "ACME TRADING LTD"},
                )
            ],
            run_id=run_id,
            source="entity_cleaning",
        )
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        alias_rows = connection.execute("SELECT alias_name, alias_type FROM entity_alias").fetchall()

    assert result.entity_count == 1
    assert result.alias_count == 2
    assert entity_count == 1
    assert {(row["alias_name"], row["alias_type"]) for row in alias_rows} == {
        ("Acme Trading Ltd", "original_name"),
        ("ACME TRADING LTD", "clean_name"),
    }
```

- [ ] **Step 2: Run entity tests and verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_entity_loader.py -v
```

Expected: FAIL with `ImportError` because `load_entities` is not defined.

- [ ] **Step 3: Implement entity loading**

Replace `src/trade_entity_graph/importers/entity_loader.py` with:

```python
"""Entity and alias loading for M2 imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from trade_entity_graph.importers.field_mapping import get_value
from trade_entity_graph.importers.models import ImportSourceRow
from trade_entity_graph.utils.ids import new_id
from trade_entity_graph.utils.normalization import normalize_company_name


@dataclass
class EntityLoadResult:
    entity_count: int = 0
    alias_count: int = 0
    skipped_rows: list[str] = field(default_factory=list)


def _find_entity_id(connection: sqlite3.Connection, canonical_name: str) -> str | None:
    row = connection.execute(
        "SELECT entity_id FROM entity WHERE canonical_name = ?",
        (canonical_name,),
    ).fetchone()
    return row["entity_id"] if row else None


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
        canonical_name = normalize_company_name(get_value(row.values, "canonical_name", ""))
        if not canonical_name:
            result.skipped_rows.append(f"{row.source_file}:{row.source_row}: missing canonical_name")
            continue
        entity_id = _find_entity_id(connection, canonical_name)
        if entity_id is None:
            entity_id = new_id("ENT")
            connection.execute(
                "INSERT INTO entity (entity_id, canonical_name, country, entity_type) VALUES (?, ?, ?, ?)",
                (
                    entity_id,
                    canonical_name,
                    get_value(row.values, "country"),
                    get_value(row.values, "entity_type"),
                ),
            )
        seen_entities.add(entity_id)
        for alias_field, alias_type in (("original_name", "original_name"), ("clean_name", "clean_name"), ("alias_name", "alias")):
            alias_name = get_value(row.values, alias_field)
            if alias_name:
                connection.execute(
                    """
                    INSERT INTO entity_alias (alias_id, entity_id, alias_name, alias_type, source, run_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (new_id("ALS"), entity_id, str(alias_name).strip(), alias_type, source, run_id),
                )
                result.alias_count += 1
    result.entity_count = len(seen_entities)
    connection.commit()
    return result
```

- [ ] **Step 4: Write failing evidence loader tests**

Create `tests/test_evidence_loader.py`:

```python
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.batch_loader import create_import_batch
from trade_entity_graph.importers.evidence_loader import load_order_evidence
from trade_entity_graph.importers.models import ImportSourceRow


def test_load_order_evidence_preserves_order_and_source_context(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        run_id = create_import_batch(
            connection,
            source_file="orders.xlsx",
            source_path=None,
            imported_by="tester",
            field_mapping_version="mvp-0.1",
            rule_version="mvp-0.1",
        )
        result = load_order_evidence(
            connection,
            [
                ImportSourceRow(
                    "orders.xlsx",
                    "Orders",
                    2,
                    {"订单号": "SO-1", "TEU": "2.5", "产品名称": "Widgets", "目的国": "US"},
                )
            ],
            run_id=run_id,
        )
        row = connection.execute("SELECT * FROM order_evidence").fetchone()

    assert result.evidence_count == 1
    assert row["order_id"] == "SO-1"
    assert row["teu"] == 2.5
    assert row["product_name"] == "Widgets"
    assert row["destination_country"] == "US"
    assert row["source_file"] == "orders.xlsx"
    assert row["source_sheet"] == "Orders"
    assert row["source_row"] == 2
```

- [ ] **Step 5: Run evidence tests and verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_evidence_loader.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'trade_entity_graph.importers.evidence_loader'`.

- [ ] **Step 6: Implement evidence loading**

Create `src/trade_entity_graph/importers/evidence_loader.py`:

```python
"""Order evidence loading for M2 imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from trade_entity_graph.importers.field_mapping import get_value
from trade_entity_graph.importers.models import ImportSourceRow
from trade_entity_graph.utils.ids import new_id


@dataclass
class EvidenceLoadResult:
    evidence_count: int = 0
    skipped_rows: list[str] = field(default_factory=list)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def load_order_evidence(
    connection: sqlite3.Connection,
    rows: list[ImportSourceRow],
    *,
    run_id: str,
) -> EvidenceLoadResult:
    """Load source order rows into `order_evidence`."""

    result = EvidenceLoadResult()
    for row in rows:
        order_id = get_value(row.values, "order_id")
        if not order_id:
            result.skipped_rows.append(f"{row.source_file}:{row.source_row}: missing order_id")
            continue
        connection.execute(
            """
            INSERT INTO order_evidence (
                evidence_id, order_id, teu, product_name, function_category,
                destination_country, destination_port, order_date, source_file,
                source_sheet, source_row, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("EVD"),
                str(order_id),
                _to_float(get_value(row.values, "teu")),
                get_value(row.values, "product_name"),
                get_value(row.values, "function_category"),
                get_value(row.values, "destination_country"),
                get_value(row.values, "destination_port"),
                get_value(row.values, "order_date"),
                row.source_file,
                row.source_sheet,
                row.source_row,
                run_id,
            ),
        )
        result.evidence_count += 1
    connection.commit()
    return result
```

- [ ] **Step 7: Run loader tests and verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_entity_loader.py tests\test_evidence_loader.py -v
```

Expected: `2 passed`.

- [ ] **Step 8: Commit Task 4**

```powershell
git add src/trade_entity_graph/importers/entity_loader.py src/trade_entity_graph/importers/evidence_loader.py tests/test_entity_loader.py tests/test_evidence_loader.py
git commit -m "feat: load entities and order evidence"
```

---

### Task 5: Existing Relationship Candidate Loader

**Files:**
- Modify: `src/trade_entity_graph/importers/relationship_loader.py`
- Test: `tests/test_relationship_loader.py`

- [ ] **Step 1: Write failing relationship loader tests**

Create `tests/test_relationship_loader.py`:

```python
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.batch_loader import create_import_batch
from trade_entity_graph.importers.models import ImportSourceRow
from trade_entity_graph.importers.relationship_loader import load_relationship_claims


def test_load_relationship_claims_creates_claims(tmp_path) -> None:
    db_path = initialize_database(tmp_path / "trade_entity_graph.db")

    with get_connection(db_path) as connection:
        connection.execute("INSERT INTO entity (entity_id, canonical_name) VALUES (?, ?)", ("ENT_A", "ACME"))
        connection.execute("INSERT INTO entity (entity_id, canonical_name) VALUES (?, ?)", ("ENT_B", "BETA"))
        run_id = create_import_batch(
            connection,
            source_file="relationships.csv",
            source_path=None,
            imported_by="tester",
            field_mapping_version="mvp-0.1",
            rule_version="mvp-0.1",
        )
        result = load_relationship_claims(
            connection,
            [
                ImportSourceRow(
                    "relationships.csv",
                    "relationships",
                    2,
                    {
                        "起点主体ID": "ENT_A",
                        "终点主体ID": "ENT_B",
                        "关系类型": "trading_partner_candidate",
                        "置信度等级": "high",
                        "置信度分数": "0.82",
                        "订单数": "5",
                        "总TEU": "12.5",
                        "推荐理由": "5 orders and 12.5 TEU",
                    },
                )
            ],
            run_id=run_id,
        )
        row = connection.execute("SELECT * FROM relationship_claim").fetchone()

    assert result.claim_count == 1
    assert row["from_entity_id"] == "ENT_A"
    assert row["to_entity_id"] == "ENT_B"
    assert row["candidate_relation_type"] == "trading_partner_candidate"
    assert row["confidence_score"] == 0.82
    assert row["order_count"] == 5
    assert row["total_teu"] == 12.5
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_relationship_loader.py -v
```

Expected: FAIL with `ImportError` because `load_relationship_claims` is not defined.

- [ ] **Step 3: Implement relationship claim loading**

Replace `src/trade_entity_graph/importers/relationship_loader.py` with:

```python
"""Relationship candidate loading for M2 imports."""

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
```

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_relationship_loader.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/trade_entity_graph/importers/relationship_loader.py tests/test_relationship_loader.py
git commit -m "feat: load relationship claims"
```

---

### Task 6: Import Pipeline and CLI

**Files:**
- Create: `src/trade_entity_graph/importers/pipeline.py`
- Modify: `scripts/import_workbook.py`
- Test: `tests/test_import_pipeline.py`

- [ ] **Step 1: Write failing pipeline tests**

Create `tests/test_import_pipeline.py`:

```python
import pandas as pd

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import


def test_run_import_loads_entities_orders_and_batch(tmp_path) -> None:
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.csv"
    db_path = tmp_path / "trade_entity_graph.db"

    pd.DataFrame({"标准名": ["ACME", "BETA"], "原始名": ["Acme Trading Ltd", "Beta Factory Inc"]}).to_csv(
        entities_path, index=False
    )
    pd.DataFrame({"订单号": ["SO-1", "SO-2"], "TEU": ["1.5", "2.0"], "产品名称": ["Widgets", "Gadgets"]}).to_csv(
        orders_path, index=False
    )

    result = run_import(
        ImportInputs(orders_path=orders_path, entities_path=entities_path, imported_by="tester"),
        db_path=db_path,
    )

    with get_connection(db_path) as connection:
        batch_count = connection.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0]
        entity_count = connection.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        alias_count = connection.execute("SELECT COUNT(*) FROM entity_alias").fetchone()[0]
        evidence_count = connection.execute("SELECT COUNT(*) FROM order_evidence").fetchone()[0]

    assert result.run_id.startswith("RUN_")
    assert result.entity_count == 2
    assert result.alias_count == 2
    assert result.evidence_count == 2
    assert result.claim_count == 0
    assert batch_count == 1
    assert entity_count == 2
    assert alias_count == 2
    assert evidence_count == 2
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_import_pipeline.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'trade_entity_graph.importers.pipeline'`.

- [ ] **Step 3: Implement the pipeline**

Create `src/trade_entity_graph/importers/pipeline.py`:

```python
"""M2 import pipeline orchestration."""

from __future__ import annotations

from pathlib import Path

from trade_entity_graph.config import get_settings
from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.importers.batch_loader import create_import_batch, finish_import_batch
from trade_entity_graph.importers.entity_loader import load_entities
from trade_entity_graph.importers.evidence_loader import load_order_evidence
from trade_entity_graph.importers.excel_importer import read_tabular_rows
from trade_entity_graph.importers.models import ImportInputs, ImportRunResult
from trade_entity_graph.importers.relationship_loader import load_relationship_claims


def _primary_source(inputs: ImportInputs) -> Path:
    for path in (inputs.orders_path, inputs.entities_path, inputs.relationships_path):
        if path is not None:
            return Path(path)
    raise ValueError("At least one import input path is required")


def run_import(inputs: ImportInputs, *, db_path: str | Path | None = None) -> ImportRunResult:
    """Run the M2 import pipeline for the provided input files."""

    settings = get_settings()
    target_db = initialize_database(db_path)
    source_path = _primary_source(inputs)
    with get_connection(target_db) as connection:
        run_id = create_import_batch(
            connection,
            source_file=source_path.name,
            source_path=str(source_path),
            imported_by=inputs.imported_by,
            field_mapping_version=settings.field_mapping_version,
            rule_version=settings.rule_version,
        )
        result = ImportRunResult(run_id=run_id)
        if inputs.entities_path is not None:
            entity_result = load_entities(
                connection,
                read_tabular_rows(inputs.entities_path),
                run_id=run_id,
                source="entity_cleaning",
            )
            result.entity_count = entity_result.entity_count
            result.alias_count = entity_result.alias_count
            result.skipped_rows.extend(entity_result.skipped_rows)
        if inputs.orders_path is not None:
            evidence_result = load_order_evidence(
                connection,
                read_tabular_rows(inputs.orders_path),
                run_id=run_id,
            )
            result.evidence_count = evidence_result.evidence_count
            result.skipped_rows.extend(evidence_result.skipped_rows)
        if inputs.relationships_path is not None:
            claim_result = load_relationship_claims(
                connection,
                read_tabular_rows(inputs.relationships_path),
                run_id=run_id,
            )
            result.claim_count = claim_result.claim_count
            result.skipped_rows.extend(claim_result.skipped_rows)
        finish_import_batch(
            connection,
            run_id,
            success_rows=result.entity_count + result.evidence_count + result.claim_count,
            error_rows=len(result.skipped_rows),
            error_summary="; ".join(result.skipped_rows) if result.skipped_rows else None,
        )
        return result
```

- [ ] **Step 4: Update the import CLI**

Replace `scripts/import_workbook.py` with:

```python
"""Inspect or import Excel/CSV workbooks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trade_entity_graph.importers.excel_importer import inspect_workbook
from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or import Excel/CSV files.")
    parser.add_argument("path", nargs="?", help="Path to inspect when --inspect-only is used")
    parser.add_argument("--inspect-only", action="store_true", help="Print workbook metadata only")
    parser.add_argument("--orders", help="Path to the order evidence Excel/CSV file")
    parser.add_argument("--entities", help="Path to the entity cleaning Excel/CSV file")
    parser.add_argument("--relationships", help="Path to the relationship candidate Excel/CSV file")
    parser.add_argument("--db-path", help="SQLite database path")
    parser.add_argument("--imported-by", default="local_user", help="Operator recorded on import_batch")
    args = parser.parse_args()

    if args.inspect_only:
        if not args.path:
            parser.error("path is required with --inspect-only")
        print(inspect_workbook(args.path))
        return

    result = run_import(
        ImportInputs(
            orders_path=Path(args.orders) if args.orders else None,
            entities_path=Path(args.entities) if args.entities else None,
            relationships_path=Path(args.relationships) if args.relationships else None,
            imported_by=args.imported_by,
        ),
        db_path=args.db_path,
    )
    print(result)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run pipeline tests and verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_import_pipeline.py -v
```

Expected: `1 passed`.

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/trade_entity_graph/importers/pipeline.py scripts/import_workbook.py tests/test_import_pipeline.py
git commit -m "feat: orchestrate M2 import pipeline"
```

---

### Task 7: M2 Verification and Documentation Alignment

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/task-breakdown.md`

- [ ] **Step 1: Update status wording in README files**

In `README.md`, replace the M0 status sentence with:

```markdown
当前仓库已完成 M0 脚手架和 M1 数据库初始化基础，下一阶段聚焦 M2 数据导入闭环：读取 Excel/CSV、生成导入批次、企业主体、别名、订单证据和已有关系候选。
```

In `README.en.md`, replace the matching status sentence with:

```markdown
The repository has completed the M0 scaffold and M1 database initialization foundation. The next phase focuses on the M2 import loop: reading Excel/CSV files and generating import batches, entities, aliases, order evidence, and existing relationship candidates.
```

- [ ] **Step 2: Add M2 verification notes to `docs/task-breakdown.md`**

Append this section after the first-version acceptance checklist:

````markdown
## M2 验证命令

M2 数据导入完成后，使用以下命令验收：

```powershell
uv --cache-dir .uv-cache run pytest tests/test_field_mapping.py tests/test_excel_importer.py tests/test_batch_loader.py tests/test_entity_loader.py tests/test_evidence_loader.py tests/test_relationship_loader.py tests/test_import_pipeline.py -v
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

通过标准：M2 专项测试、全量测试和 ruff 均为 0 failures / 0 errors。
````

- [ ] **Step 3: Run full verification**

Run:

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Expected:

```text
pytest: all tests passed
ruff: All checks passed!
```

- [ ] **Step 4: Commit Task 7**

```powershell
git add README.md README.en.md docs/task-breakdown.md
git commit -m "docs: document M2 import verification"
```

---

## Self-Review

Spec coverage:

- `IMP-01` is covered by Task 2.
- `IMP-02` is covered by Task 4 and Task 6.
- `IMP-03` is covered by Task 5 and Task 6.
- `IMP-04` is covered by Task 3 and Task 6.
- M2 closed-loop verification is covered by Task 6 and Task 7.

Placeholder scan:

- This plan contains no unfilled placeholder markers.
- This plan does not contain a deferred code placeholder.
- This plan includes exact paths, exact commands, concrete tests, and concrete implementation code.

Type consistency:

- `ImportSourceRow`, `ImportInputs`, and `ImportRunResult` are defined in Task 1 and used consistently in Tasks 2, 4, and 6.
- Loader result attributes use `entity_count`, `alias_count`, `evidence_count`, `claim_count`, and `skipped_rows` consistently.
- `run_id` is created by `create_import_batch` and passed to all loaders consistently.

## Final Verification Gate

Before marking M2 complete, run:

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Completion requires both commands to exit with code 0.


## Current Status

M2 was completed as part of the broader M2-M7 P0 implementation and later extended with source-file archiving.

Current import outputs include `import_batch`, `import_source_file`, `entity`, `entity_alias`, `order_evidence`, and optional `relationship_claim` rows. Latest full-suite verification on 2026-05-22 reported 14 passed and ruff 0 errors.
