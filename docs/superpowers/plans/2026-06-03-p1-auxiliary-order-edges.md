# P1 Auxiliary Order Edges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate P1 `shipper_to_notify` and `consignee_to_notify` order-role evidence edges.

**Architecture:** Extend the existing role-pair tuple in `relationship_service.py`. Downstream candidate aggregation, graph, path, API, UI, and evidence detail already consume `order_role_edge`, so they inherit the new evidence edges automatically.

**Tech Stack:** Python 3.12, SQLite, pytest, ruff.

---

### Task 1: Tests First

**Files:**
- Modify: `tests/test_relationship_service.py`
- Modify as needed after RED: `tests/test_api_p0.py`, `tests/test_demo_acceptance.py`

- [ ] Write failing tests expecting `shipper_to_notify` and `consignee_to_notify` when notify is a valid entity.
- [ ] Verify RED with `uv --cache-dir .uv-cache run pytest tests/test_relationship_service.py -q`.

### Task 2: Implementation

**Files:**
- Modify: `src/trade_entity_graph/services/relationship_service.py`

- [ ] Add the two P1 role-pair definitions.
- [ ] Run `uv --cache-dir .uv-cache run pytest tests/test_relationship_service.py -q` and verify GREEN.
- [ ] Run affected API/demo tests and update expected counts if needed.

### Task 3: Docs, Demo, Verification

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/task-breakdown.md`
- Modify: `docs/technical-plan.md`

- [ ] Update docs from “P1 auxiliary edges deferred” to implemented.
- [ ] Reinitialize the local SQLite demo database and reimport/seed demo data.
- [ ] Run full verification: `uv --cache-dir .uv-cache run pytest` and `uv --cache-dir .uv-cache run ruff check .`.
- [ ] Commit with `feat: add p1 auxiliary order edges`.
