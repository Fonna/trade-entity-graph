# Structured Supplemental Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured supplemental evidence for relationship candidates and curated relationships while deferring P1 auxiliary order-role edges.

**Architecture:** Add one SQLite table and service helpers for supplemental evidence. Keep order evidence and supplemental evidence separate in storage, then combine them at the relationship evidence boundary with explicit record-type tags.

**Tech Stack:** Python 3.12, SQLite, FastAPI, Streamlit, pytest, ruff.

---

## File Structure

- Modify `src/trade_entity_graph/db/schema.sql`: add `relationship_external_evidence` and indexes.
- Modify `src/trade_entity_graph/db/connection.py`: add legacy table initialization support by relying on `CREATE TABLE IF NOT EXISTS`; no column migration is required.
- Modify `src/trade_entity_graph/services/relationship_service.py`: add external evidence creation/listing and combined evidence tagging.
- Modify `src/trade_entity_graph/services/review_service.py`: accept optional external evidence on ordinary decisions, history decisions, pending verification, supersede, and manual relationship creation.
- Modify `src/trade_entity_graph/api/routers/relationships.py`: add request model and endpoint plumbing.
- Modify `src/trade_entity_graph/ui/streamlit_app.py`: add helper functions, evidence rendering sections, and optional form fields.
- Modify tests: `tests/test_database_schema.py`, `tests/test_relationship_service.py`, `tests/test_api_p0.py`, `tests/test_streamlit_app.py`.
- Modify docs: `README.md`, `README.en.md`, `docs/task-breakdown.md`, `docs/technical-plan.md`, `docs/local-relationship-reuse-guide.md`.

---

### Task 1: Schema

**Files:**
- Modify: `src/trade_entity_graph/db/schema.sql`
- Test: `tests/test_database_schema.py`

- [ ] **Step 1: Write failing schema tests**

Add `relationship_external_evidence` to `EXPECTED_TABLES`, add indexes `idx_relationship_external_evidence_relationship` and `idx_relationship_external_evidence_claim`, and add a test that initializes a database and asserts these columns exist: `external_evidence_id`, `relationship_id`, `claim_id`, `evidence_type`, `source_title`, `source_url`, `source_name`, `evidence_summary`, `evidence_date`, `confidence_level`, `created_by`, `created_at`.

- [ ] **Step 2: Run schema test and verify RED**

Run `uv --cache-dir .uv-cache run pytest tests/test_database_schema.py::test_relationship_external_evidence_schema_has_traceability_columns -q`.
Expected: fail because the table does not exist.

- [ ] **Step 3: Implement schema**

Add the table and indexes to `schema.sql` using `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.

- [ ] **Step 4: Run schema tests and verify GREEN**

Run `uv --cache-dir .uv-cache run pytest tests/test_database_schema.py -q`.
Expected: pass.

---

### Task 2: Relationship Service

**Files:**
- Modify: `src/trade_entity_graph/services/relationship_service.py`
- Modify: `src/trade_entity_graph/services/review_service.py`
- Test: `tests/test_relationship_service.py`

- [ ] **Step 1: Write failing service tests**

Add tests that:

1. Create supplemental evidence on a `relationship_claim` and assert `get_relationship_evidence(claim_id)` returns a row with `evidence_record_type='external_evidence'`.
2. Review a claim with optional external evidence and assert the evidence is bound to both `claim_id` and the new `relationship_id`.
3. Create a manual relationship with optional external evidence and assert the evidence is bound to the manual `relationship_id`.

- [ ] **Step 2: Run service tests and verify RED**

Run `uv --cache-dir .uv-cache run pytest tests/test_relationship_service.py -q`.
Expected: fail because helper functions and optional evidence arguments do not exist.

- [ ] **Step 3: Implement service helpers**

Add evidence normalization, validation, insertion, target resolution, listing, and combined evidence tags. Keep empty optional evidence ignored by review functions.

- [ ] **Step 4: Run service tests and verify GREEN**

Run `uv --cache-dir .uv-cache run pytest tests/test_relationship_service.py -q`.
Expected: pass.

---

### Task 3: API

**Files:**
- Modify: `src/trade_entity_graph/api/routers/relationships.py`
- Test: `tests/test_api_p0.py`

- [ ] **Step 1: Write failing API tests**

Add tests for `POST /relationships/{id}/external-evidence` and for `POST /relationships/{claim_id}/decision` with `external_evidence` in the body.

- [ ] **Step 2: Run API tests and verify RED**

Run `uv --cache-dir .uv-cache run pytest tests/test_api_p0.py -q`.
Expected: fail because endpoint and request model plumbing are missing.

- [ ] **Step 3: Implement API plumbing**

Add `ExternalEvidenceRequest`, include it in decision/manual request models, and expose the new endpoint.

- [ ] **Step 4: Run API tests and verify GREEN**

Run `uv --cache-dir .uv-cache run pytest tests/test_api_p0.py -q`.
Expected: pass.

---

### Task 4: Streamlit UI

**Files:**
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Test: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write failing UI tests**

Add tests for the helper that builds optional evidence payloads from form values and the helper that splits combined evidence into order and supplemental evidence tables.

- [ ] **Step 2: Run UI tests and verify RED**

Run `uv --cache-dir .uv-cache run pytest tests/test_streamlit_app.py -q`.
Expected: fail because helper functions do not exist.

- [ ] **Step 3: Implement UI helpers and forms**

Add optional evidence input rendering, payload creation, split evidence rendering, and wire the payload into review/manual actions.

- [ ] **Step 4: Run UI tests and verify GREEN**

Run `uv --cache-dir .uv-cache run pytest tests/test_streamlit_app.py -q`.
Expected: pass.

---

### Task 5: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/task-breakdown.md`
- Modify: `docs/technical-plan.md`
- Modify: `docs/local-relationship-reuse-guide.md`

- [ ] **Step 1: Update docs**

Document structured supplemental evidence and update stale status and verification counts. State that P1 auxiliary role edges remain deferred.

- [ ] **Step 2: Run full verification**

Run:

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Expected: all tests pass and ruff reports no errors.

- [ ] **Step 3: Inspect git status**

Run `git status --short --branch` and confirm only intended files changed.

- [ ] **Step 4: Commit**

Commit with `feat: add structured supplemental evidence`.
