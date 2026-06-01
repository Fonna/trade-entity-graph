# Confirmed Relationship Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an import entry for already-confirmed relationships that writes directly to final curated relationships while preserving candidate import behavior.

**Architecture:** Extend the existing import pipeline with a new `confirmed_relationships` source role, a focused curated-relationship loader, and result/API/UI fields for imported final relationship counts. Keep candidate imports on `relationship_claim`; confirmed imports write `curated_relationship`, `relationship_decision`, and `audit_log` for traceability.

**Tech Stack:** Python, SQLite, FastAPI, Streamlit, pytest, ruff.

---

### Task 1: Pipeline and Loader

**Files:**
- Modify: `src/trade_entity_graph/importers/models.py`
- Modify: `src/trade_entity_graph/importers/relationship_loader.py`
- Modify: `src/trade_entity_graph/importers/field_mappings/default.json`
- Modify: `src/trade_entity_graph/importers/pipeline.py`
- Test: `tests/test_import_pipeline.py`

- [ ] Write failing tests for direct confirmed relationship import into `curated_relationship`, decision/audit writes, required `relation_type`, endpoint validation, duplicate source archive role, and result `curated_relationship_count`.
- [ ] Run targeted tests and confirm they fail because `confirmed_relationships_path` and the loader are missing.
- [ ] Add `confirmed_relationships_path` and `curated_relationship_count` to import models.
- [ ] Add a `confirmed_relationships` field-mapping role with endpoint aliases, `relation_type`, status/confidence/source/note aliases.
- [ ] Implement `load_confirmed_relationships` with endpoint resolution, numeric parsing, self-pair validation, default status/source/verified metadata, decision rows, and audit rows.
- [ ] Wire the new role into source discovery, archive, field mapping, import errors, and pipeline result counting.
- [ ] Run targeted tests and confirm they pass.

### Task 2: API and Streamlit Entry

**Files:**
- Modify: `src/trade_entity_graph/api/routers/imports.py`
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Test: `tests/test_api_p0.py`
- Test: `tests/test_streamlit_app.py`

- [ ] Write failing tests that API accepts `confirmed_relationships_path`, includes it in duplicate checking and failure details, and returns `curated_relationship_count`.
- [ ] Write failing Streamlit tests that the import tab has a confirmed relationship path input, passes it into `ImportInputs`, includes it in duplicate checking, and shows the result count in JSON.
- [ ] Implement API request/input plumbing and response field.
- [ ] Implement Streamlit input, duplicate source role, and import call plumbing.
- [ ] Run targeted API/UI tests and confirm they pass.

### Task 3: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/technical-plan.md`
- Modify: `docs/local-relationship-reuse-guide.md` if import semantics need clarification

- [ ] Update documentation to distinguish candidate relationship import from confirmed relationship import.
- [ ] Document expected confirmed relationship file columns and defaults.
- [ ] Run `uv --cache-dir .uv-cache run pytest tests/test_import_pipeline.py tests/test_api_p0.py tests/test_streamlit_app.py -q`.
- [ ] Run `uv --cache-dir .uv-cache run ruff check .`.
- [ ] Commit and push the branch.
