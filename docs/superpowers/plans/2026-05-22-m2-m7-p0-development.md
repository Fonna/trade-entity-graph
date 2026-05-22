# M2-M7 P0 Development Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved M2-M7 P0 demo loop: import data, generate order-role edges, aggregate candidates, query one-hop graphs, expose FastAPI endpoints, and provide a Streamlit MVP shell over the service layer.

**Architecture:** Use a service-layer-first modular monolith. Importers write SQLite tables, services implement business logic, FastAPI routers and Streamlit call services as thin adapters. Keep P1 features out of this implementation.

**Tech Stack:** Python 3.12 via `uv`, SQLite, pandas/openpyxl, NetworkX, FastAPI, Streamlit, pytest, ruff.

---

## Task 1: M2 Import Foundation

**Files:**
- Create: `src/trade_entity_graph/importers/models.py`
- Create: `src/trade_entity_graph/importers/field_mapping.py`
- Create: `src/trade_entity_graph/importers/batch_loader.py`
- Create: `src/trade_entity_graph/importers/evidence_loader.py`
- Modify: `src/trade_entity_graph/importers/excel_importer.py`
- Modify: `src/trade_entity_graph/importers/entity_loader.py`
- Modify: `src/trade_entity_graph/importers/relationship_loader.py`
- Create: `src/trade_entity_graph/importers/pipeline.py`
- Modify: `src/trade_entity_graph/db/schema.sql`
- Test: `tests/test_import_pipeline.py`

- [ ] **Step 1: Write failing M2 tests**

Create `tests/test_import_pipeline.py` with a CSV-driven import test that asserts `import_batch`, `entity`, `entity_alias`, `order_evidence`, and optional `relationship_claim` rows are created, and that order role names are preserved on `order_evidence`.

- [ ] **Step 2: Run M2 tests to verify red**

Run: `uv --cache-dir .uv-cache run pytest tests\test_import_pipeline.py -v`

Expected: fail because importer models, loaders, and pipeline do not exist.

- [ ] **Step 3: Implement M2 importers**

Add source-row dataclasses, logical field alias lookup, Excel/CSV readers, batch loader, entity loader, evidence loader, relationship claim loader, and import orchestration.

- [ ] **Step 4: Run M2 tests to verify green**

Run: `uv --cache-dir .uv-cache run pytest tests\test_import_pipeline.py -v`

Expected: pass.

## Task 2: M3-M4 Relationship Services

**Files:**
- Modify: `src/trade_entity_graph/services/relationship_service.py`
- Test: `tests/test_relationship_service.py`

- [ ] **Step 1: Write failing M3-M4 tests**

Create `tests/test_relationship_service.py` with tests that import sample entities and orders, generate the four P0 `order_role_edge` types, filter invalid placeholders, and aggregate `relationship_claim` rows with confidence and recommendation reasons.

- [ ] **Step 2: Run service tests to verify red**

Run: `uv --cache-dir .uv-cache run pytest tests\test_relationship_service.py -v`

Expected: fail because service functions do not exist.

- [ ] **Step 3: Implement relationship services**

Implement `generate_order_role_edges()`, entity-name resolution through aliases, invalid role filtering, `aggregate_relationship_claims()`, `get_relationship_detail()`, and `get_relationship_evidence()`.

- [ ] **Step 4: Run service tests to verify green**

Run: `uv --cache-dir .uv-cache run pytest tests\test_relationship_service.py -v`

Expected: pass.

## Task 3: M5 Entity, Graph, Review, and Export Services

**Files:**
- Modify: `src/trade_entity_graph/services/entity_service.py`
- Modify: `src/trade_entity_graph/services/graph_service.py`
- Modify: `src/trade_entity_graph/services/review_service.py`
- Modify: `src/trade_entity_graph/services/export_service.py`
- Test: `tests/test_services_p0_flow.py`

- [ ] **Step 1: Write failing P0 service-flow tests**

Create `tests/test_services_p0_flow.py` with tests for entity search/detail, one-hop graph JSON, confirm/reject/modify/manual review writes, audit/decision rows, and CSV export rows.

- [ ] **Step 2: Run flow tests to verify red**

Run: `uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py -v`

Expected: fail because services are placeholders.

- [ ] **Step 3: Implement M5 service layer**

Implement the service functions specified in the design document. Keep returned objects as plain dictionaries/lists so both API and Streamlit can reuse them.

- [ ] **Step 4: Run flow tests to verify green**

Run: `uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py -v`

Expected: pass.

## Task 4: M6 FastAPI Adapters

**Files:**
- Modify: `src/trade_entity_graph/config.py`
- Modify: `src/trade_entity_graph/api/main.py`
- Modify: `src/trade_entity_graph/api/routers/entities.py`
- Modify: `src/trade_entity_graph/api/routers/relationships.py`
- Modify: `src/trade_entity_graph/api/routers/graph.py`
- Modify: `src/trade_entity_graph/api/routers/imports.py`
- Modify: `src/trade_entity_graph/api/routers/exports.py`
- Test: `tests/test_api_p0.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api_p0.py` using `fastapi.testclient.TestClient`. The test sets a temporary database path through `TEG_DATABASE_PATH`, imports sample data, and verifies search, detail, graph, relationship detail, review, import, and export endpoints.

- [ ] **Step 2: Run API tests to verify red**

Run: `uv --cache-dir .uv-cache run pytest tests\test_api_p0.py -v`

Expected: fail because routers are placeholders.

- [ ] **Step 3: Implement API routers**

Make routers thin wrappers over service and importer functions. Update `config.py` so settings read environment values when `get_settings()` is called.

- [ ] **Step 4: Run API tests to verify green**

Run: `uv --cache-dir .uv-cache run pytest tests\test_api_p0.py -v`

Expected: pass.

## Task 5: M7 Streamlit MVP Workbench

**Files:**
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Modify: `README.md`
- Modify: `README.en.md`
- Test: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write failing Streamlit smoke test**

Create `tests/test_streamlit_app.py` asserting the Streamlit module exposes a callable `main()` and tab-render helper functions are importable without starting a server.

- [ ] **Step 2: Run Streamlit test to verify red**

Run: `uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py -v`

Expected: fail until helper functions exist.

- [ ] **Step 3: Implement Streamlit tabs**

Implement Import, Search, Graph, Relationship Detail, Review, and Export tabs as service-layer callers. Keep UI simple and defensive.

- [ ] **Step 4: Run Streamlit test to verify green**

Run: `uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py -v`

Expected: pass.

## Task 6: Final Verification

**Files:**
- Modify: `docs/task-breakdown.md`

- [ ] **Step 1: Update development status docs**

Document that M2-M7 P0 has a service-layer-first implementation and list verification commands.

- [ ] **Step 2: Run full verification**

Run:

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Expected: all tests pass and ruff reports `All checks passed!`.

## Self-Review

- Spec coverage: Tasks cover M2, M3, M4, M5, M6, and M7 P0 from the approved design.
- Placeholder scan: no unfilled placeholder markers remain.
- Type consistency: importers return dataclasses or dictionaries; services return plain dictionaries/lists; API returns those values as JSON.
- Scope check: P1 features remain excluded.
