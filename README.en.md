# Trade Entity Graph
## 2026-06-03 Status Update

- Added structured supplemental evidence: `relationship_external_evidence` can link to either a relationship candidate or a curated relationship and stores evidence type, title, URL, source, summary, date, confidence level, and creator.
- FastAPI now provides `POST /relationships/{relationship_id}/external-evidence`; review and manual relationship requests can include `external_evidence`.
- Streamlit relationship details now separate order evidence and supplemental evidence; the review page accepts optional supplemental evidence.
- P1 auxiliary order-role edges are now implemented: in addition to the four P0 order-role edge types, the importer now generates `shipper_to_notify` and `consignee_to_notify`.
- Latest verification: `uv --cache-dir .uv-cache run pytest` returned `208 passed`, and `uv --cache-dir .uv-cache run ruff check .` returned `All checks passed!`.


English | [中文](README.md)

`trade-entity-graph` is an entity relationship asset system for direct-customer overseas trade and first-leg ocean freight order analysis. It turns one-off Excel analysis outputs into a reusable system for importing, reviewing, tracing, visualizing, and exporting company relationship networks.

## Product Summary

Build a reusable, auditable, evidence-backed, human-reviewable, and graph-visualized company relationship system. The system manages company cross-relationships discovered from orders and supports searching any entity, expanding its network, reviewing evidence, and analyzing relationship opportunities.

## Core Principles

- Order-role relationships are not final business relationships: an order co-occurrence such as `customer -> notify party` is evidence, not proof of a same-group, subsidiary, or trading-partner relationship.
- Final relationships must be explainable: every curated relationship should trace back to order evidence, manual decisions, public sources, or sales feedback.
- Human decisions never overwrite raw evidence: confirming, rejecting, editing, or creating relationships appends decision records while preserving original evidence.
- A-B and B-C do not imply A-C: cross-relationships must be displayed, reviewed, and curated independently.
- The MVP prioritizes the full loop: import data, reuse entities, generate edges, review relationships, show an ego graph, and export results before introducing heavy graph databases.

## MVP Scope

- Import existing order analysis outputs and company-name cleaning results;
- Build an entity master table and alias table;
- Preserve order-role relationships such as “Company A is customer, Company B is notify party”;
- Build a relationship candidate table;
- Provide review actions to confirm, reject, edit, and manually create relationships;
- Write confirmed decisions into the curated relationship table;
- Support entity search, bounded one-hop/two-hop ego graph visualization, and two-entity path query;
- Show order evidence and manual decisions when a relationship is selected;
- Export relationship details for a center entity.

## Technology Choices

| Area | MVP Choice | Notes |
| --- | --- | --- |
| Data processing | Python + Pandas/Polars | Read Excel/CSV and generate entities, evidence, edges, and candidates |
| Storage | SQLite first, PostgreSQL optional | SQLite for local MVP; PostgreSQL when multi-user collaboration is needed |
| Graph query | Relational edge tables + NetworkX | No Neo4j for MVP; query local subgraphs first |
| Backend API | FastAPI | Search, graph, relationship details, review writes, and exports |
| Frontend | Streamlit first, React optional | Validate workflows quickly before building a production frontend |
| Export | Excel/CSV | Export relationship details, nodes, edges, and review results |

## Repository Layout

```text
trade-entity-graph/
  README.md
  README.en.md
  pyproject.toml
  .env.example
  data/
    raw/
    processed/
    exports/
  docs/
    task-breakdown.md
    technical-plan.md
  src/trade_entity_graph/
    config.py
    db/
    importers/
    services/
    api/
    ui/
    utils/
  scripts/
  tests/
```

## Quick Start

The repository has completed the M0/M1 baseline and now includes the M2-M10 P0/P1 demo loop: Excel/CSV import, source-file archiving, order-role edge generation, relationship candidate aggregation, one-hop/two-hop graph query, two-entity path query, FastAPI endpoints, Chinese Streamlit workbench, export support, demo acceptance data, and the M9 real-data import QA loop with configurable field mapping, row-level import errors, import batch queries, quality reports, and import-error CSV export. M10 adds bounded two-hop expansion, `GET /paths`, and a Streamlit path-query workflow. On 2026-06-03, structured supplemental evidence was added for relationship candidates and curated relationships. P1 auxiliary order-role edges (`shipper_to_notify`, `consignee_to_notify`) are now implemented.

All Python environments, dependency installation, and Python commands in this project should use `uv` to avoid polluting the global Python environment.

```powershell
uv python pin 3.12
uv sync --extra dev
uv run python scripts\init_db.py
uv run python scripts\run_api.py
```

Start the Streamlit prototype:

```powershell
uv run python scripts\run_ui.py
```

### M8 Demo Data and Acceptance

Generate and import demo data with about 50 entities, 80+ orders, and broad relationship coverage:

```powershell
uv --cache-dir .uv-cache run python scripts\generate_demo_data.py
uv --cache-dir .uv-cache run python scripts\init_db.py
uv --cache-dir .uv-cache run python scripts\import_demo_data.py
uv --cache-dir .uv-cache run python scripts\seed_demo_reviews.py
```

The demo files live under `data/demo/`. After import, the system keeps pending candidates for manual review and pre-seeds reviewed relationships covering `same_group`, `subsidiary`, `factory_node`, `sales_center`, `trading_partner`, `logistics_service`, and `rejected_relation`.

Run smoke tests:

```powershell
uv run pytest
```

During import, the system copies original Excel/CSV files to `data/raw/imports/<run_id>/` and records each file role, original path, archived path, file size, and SHA256 in the SQLite `import_source_file` table.

### M9 Real-Data Import QA Loop

M9 targets dry runs with real Excel/CSV files. The default field mapping recognizes common Chinese and English aliases and can be configured for source-specific column names. Import validation keeps valid rows while writing missing fields, blank required values, TEU format errors, unknown entity references, and invalid relationship pairs to `import_error`.

Import batches and quality results are available through `GET /imports`, `GET /imports/{run_id}`, `GET /imports/{run_id}/errors`, and `GET /imports/{run_id}/quality-report`. The Streamlit data import page shows recent batches, quality summaries, row-level errors, and import-error CSV export.

### M10 Two-Hop Graph and Two-Entity Path Query

M10 expands graph exploration while keeping it bounded: `GET /entities/{entity_id}/ego-graph?depth=2&max_nodes=50` preserves the default one-hop behavior, can expand to depth two, and limits returned nodes with `max_nodes`. Rejected relationships remain hidden by default and can be included with `include_rejected=true`.

Two-entity path query is available through `GET /paths?from_entity_id=<A>&to_entity_id=<C>&max_depth=3&max_paths=5`. The response includes explainable paths, path nodes, edge provenance, statuses, and scores. In Streamlit, the graph tab now has `Graph depth` / `Max nodes` controls and a two-entity path-query section that renders `step/from_name/to_name/relation_type/record_type/status/evidence`; unknown entities and no-path results show visible prompts.

## Data Flow

```mermaid
flowchart TD
  A[Import order details and existing analysis outputs]
  A0[Archive source files to data/raw/imports/run_id]
  B[Clean names and match entities]
  C[Generate order-role edges]
  D[Aggregate relationship candidates]
  E[Create verification/review queue]
  F[Human edit, confirm, reject, or add evidence]
  G[Write curated relationships]
  H[Search and graph visualization]
  I[Export/BI/opportunity list]

  A --> A0
  A0 --> B
  B --> C
  C --> D
  D --> E
  E --> F
  F --> G
  G --> H
  G --> I
  C --> H
```

## Core Data Objects

- `entity`: Entity master data; all relationships and evidence bind to `entity_id`.
- `entity_alias`: Original names, cleaned names, short names, historical names, and manually added aliases.
- `order_evidence`: Order evidence with order number, TEU, destination, product, source file, sheet, row, and `run_id`.
- `order_role_edge`: Evidence edges between customers, shippers, consignees, and notify parties.
- `relationship_claim`: System-generated relationship candidates.
- `curated_relationship`: Final confirmed, rejected, pending, or manually created relationships.
- `relationship_decision`: Human review actions with before/after state, reason, operator, and timestamp.
- `import_batch`: Import metadata, including source files, mapping version, rule version, success count, and error count.
- `import_source_file`: Per-source archive metadata, including file role, original path, archived path, file size, and SHA256.
- `audit_log`: Audit trail for key operations.

## Key Documents

- `企业关系图谱系统_PRD.md`: Product requirements document.
- `MVP研发任务拆解.md`: Original MVP task breakdown.
- `docs/task-breakdown.md`: Organized development task list.
- `docs/technical-plan.md`: MVP technical plan, data model, APIs, and UI breakdown.
- `docs/superpowers/plans/2026-05-22-import-source-file-archive.md`: Source-file archive implementation plan and execution record.

## Current Development Status

As of 2026-06-03, the current branch includes the M2-M10 P0/P1 loop, source-file archiving, historical relationship reuse, the global review queue, the Chinese Streamlit workbench, demo acceptance data, the M9 real-data import QA loop, the M10 two-hop graph and two-entity path-query workflow, and structured supplemental evidence. Latest verification:

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

Result: `208 passed`, ruff `All checks passed!`.

## Recommended Development Order

1. M0: Project scaffold and baseline conventions.
2. M1: Database schema and initialization script.
3. M2: Excel/CSV import and field mapping.
4. M3: Order-role edge generation and aggregate statistics.
5. M4: Relationship candidate generation, scoring, and recommendation reasons.
6. M5: NetworkX local graph query service.
7. M6: FastAPI endpoints for search, graph, details, reviews, the global review queue, and exports.
8. M7: Streamlit MVP pages and the review queue workbench.
9. M8: Review persistence, audit logs, acceptance demo.
10. M9: Real-data dry runs, import quality reports, and import-error workflow.
11. M10: Two-hop graph expansion, `GET /paths` two-entity path query, and Streamlit path-query workflow.
12. Structured supplemental evidence: attach public information, sales feedback, business documents, and manual notes to candidates or curated relationships; P1 auxiliary order-role edges are now implemented.

## Remote Repository

```text
git@github.com:Fonna/trade-entity-graph.git
```
