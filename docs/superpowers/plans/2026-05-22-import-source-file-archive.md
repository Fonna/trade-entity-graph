# Import Source File Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Implementation note: initially developed locally; later committed and pushed after user requested repository publication.

**Goal:** Archive every source file used by an import run and record per-file archive metadata for traceability.

**Architecture:** Keep the existing service-layer import pipeline. Add a small archive helper that copies source files into `data/raw/imports/<run_id>/`, computes file metadata, and persists one row per source file. The import pipeline calls this helper after creating the `run_id` and returns archived file details in `ImportRunResult`.

**Tech Stack:** Python 3.12, SQLite, pathlib, shutil, hashlib, pytest, ruff.

---

### Task 1: Schema And Result Contract

**Files:**
- Modify: `src/trade_entity_graph/db/schema.sql`
- Modify: `src/trade_entity_graph/importers/models.py`
- Test: `tests/test_import_pipeline.py`

- [x] **Step 1: Write the failing test**

Add assertions to an import pipeline test that expects:

```python
with get_connection(db_path) as connection:
    archived_rows = connection.execute(
        """
        SELECT source_role, original_path, archived_path, file_name, file_size_bytes, sha256
        FROM import_source_file
        WHERE run_id = ?
        ORDER BY source_role
        """,
        (result.run_id,),
    ).fetchall()

assert {row["source_role"] for row in archived_rows} == {"entities", "orders"}
assert len(result.archived_files) == 2
assert all(row["sha256"] for row in archived_rows)
assert all(Path(row["archived_path"]).exists() for row in archived_rows)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv --cache-dir .uv-cache run pytest tests\test_import_pipeline.py::test_run_import_loads_entities_orders_and_role_names -v`

Expected: FAIL because `import_source_file` or `archived_files` does not exist.

- [x] **Step 3: Add schema and dataclasses**

Add `import_source_file` table to `schema.sql`, and add `ImportRunResult.archived_files` to `models.py`.

- [x] **Step 4: Run test again**

Expected: test still fails until archive persistence is implemented.

### Task 2: Archive Helper

**Files:**
- Create: `src/trade_entity_graph/importers/source_archive.py`
- Modify: `src/trade_entity_graph/importers/pipeline.py`
- Test: `tests/test_import_pipeline.py`

- [x] **Step 1: Implement minimal archiver**

Create a helper that accepts a run id and role/path pairs, copies files to `data/raw/imports/<run_id>/`, computes SHA256, records metadata, and returns archived-file metadata dictionaries.

- [x] **Step 2: Wire pipeline**

Call the archiver immediately after `create_import_batch` and before reading source rows. Store returned items in `ImportRunResult.archived_files`.

- [x] **Step 3: Run focused tests**

Run: `uv --cache-dir .uv-cache run pytest tests\test_import_pipeline.py -v`

Expected: import pipeline tests pass.

### Task 3: UI Copy And Verification

**Files:**
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Modify: `tests/test_streamlit_app.py`

- [x] **Step 1: Show archive path in import UI**

After import, show a short success note and dataframe/JSON entry with archived files so users can see where files were copied.

- [x] **Step 2: Update UI constants/test if needed**

Keep the UI text Chinese and include the archive directory concept in the intro.

- [x] **Step 3: Verify**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_import_pipeline.py tests\test_streamlit_app.py -v
uv --cache-dir .uv-cache run ruff check src\trade_entity_graph\importers src\trade_entity_graph\ui tests\test_import_pipeline.py tests\test_streamlit_app.py
```

Expected: tests and ruff pass.


## Implementation Status

Completed on 2026-05-22 and pushed to `origin/main` in commit `4dc6c27 feat: add import source archiving`.

Validation evidence:

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Result: full test suite 14 passed; ruff reported no errors. Streamlit AppTest also passed for the Chinese UI guide and archive-path text.
