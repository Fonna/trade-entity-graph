# M10 Path Query and Two-Hop Graph Design

## Goal

M10 turns the imported relationship graph from a one-hop exploration tool into an answer tool for two practical business questions:

1. Which entities appear within two hops of this center entity?
2. How are two selected entities connected through order evidence, candidate relationships, or curated relationships?

## Scope

In scope:

- Add service-layer graph expansion for `depth=1` and `depth=2` with a hard node limit.
- Add service-layer path search between two entity ids with configurable `max_depth`, default 3.
- Include edge provenance in every path step: `order_role_edge`, `relationship_claim`, or `curated_relationship`.
- Hide rejected/deprecated curated relationships by default, preserving the existing default behavior.
- Expose FastAPI endpoints for depth-based ego graph and path search.
- Add Streamlit controls for two-hop expansion and two-entity path query.
- Add tests and documentation updates.

Out of scope:

- No Neo4j or persistent graph database.
- No new schema tables.
- No complex ML scoring model.
- No React frontend.
- No fuzzy name matching in the path query; inputs remain entity ids for M10.

## Approach

Use the existing SQLite service-layer pattern. `graph_service.py` remains the graph boundary and builds an in-memory adjacency list from three existing data sources:

- `order_role_edge` for order evidence edges.
- `relationship_claim` for reviewable generated candidates.
- `curated_relationship` for final/manual relationships.

For M10 the service returns deterministic JSON structures and keeps API/UI adapters thin. This avoids adding infrastructure while making the feature testable through service tests first.

## Data Model and Edge Semantics

M10 uses existing rows only. Each graph edge returned to clients includes:

- `id`: source record id.
- `source` and `target`: entity ids.
- `source_label` and `target_label`: entity names.
- `record_type`: one of `order_role_edge`, `relationship_claim`, `curated_relationship`.
- `relation_type`: role pair, candidate relation type, or curated relation type.
- `status`: `evidence`, candidate status, or curated status.
- `order_count` and `total_teu` when available.
- `label`: short human-readable label.

Path search treats edges as undirected for discovery. The returned path still preserves the original edge direction and adds path-local `path_from` and `path_to` fields when useful.

## Service Design

Public functions:

```python
def get_ego_graph(
    center_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
    depth: int = 1,
    max_nodes: int = 50,
) -> dict[str, Any]:
    """Return graph or path payload."""


def find_entity_paths(
    from_entity_id: str,
    to_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
    max_depth: int = 3,
    max_paths: int = 5,
) -> dict[str, Any]:
    """Return graph or path payload."""
```

`get_ego_graph` keeps its existing default behavior because `depth=1` is the default.

`find_entity_paths` returns:

```json
{
  "from_entity_id": "ENT_A",
  "to_entity_id": "ENT_D",
  "max_depth": 3,
  "path_count": 1,
  "paths": [
    {
      "node_ids": ["ENT_A", "ENT_B", "ENT_D"],
      "nodes": [{"id": "ENT_A", "label": "A"}],
      "edges": [{"id": "EDG_1", "record_type": "order_role_edge"}],
      "score": 0.7,
      "explanation": "A connects to D through B."
    }
  ],
  "summary": {"path_count": 1, "truncated": false}
}
```

Ranking is deterministic and simple:

1. Shorter paths first.
2. Higher edge confidence/source priority next: curated verified, history matched, candidate, order evidence.
3. Higher total order count/TEU as tie-breaker.

## API Design

- `GET /entities/{entity_id}/ego-graph?depth=1&max_nodes=50&include_rejected=false`
  - Extends existing endpoint while preserving defaults.
  - Rejects `depth < 1`, `depth > 2`, or excessive `max_nodes` through FastAPI query validation.

- `GET /paths?from_entity_id=ENT_A&to_entity_id=ENT_D&max_depth=3&max_paths=5&include_rejected=false`
  - Uses explicit parameter names to avoid Python reserved-word ambiguity.
  - Returns 404 if either endpoint entity does not exist.
  - Returns `path_count=0` when both entities exist but no path is found.

## Streamlit Design

Graph tab changes:

- Existing center entity input remains.
- Add depth selector with values 1 and 2.
- Add max node input with default 50.
- Show graph summary; if the service says results were truncated, show a warning.

Path query section:

- Inputs: start entity id, target entity id, max depth.
- Button: query path.
- Render each path as a compact table of steps: start, end, relation type, source, status, evidence summary.
- If no path exists, show an info message instead of an error.

## Error Handling

- Service raises `ValueError` for invalid depth and unknown endpoint ids in path search.
- API converts unknown entity `ValueError` to 404 and validation errors to 422 through query constraints.
- UI catches exceptions and displays user-facing messages through existing `format_error_message`.

## Testing

- Service tests seed minimal SQLite rows and verify:
  - one-hop default compatibility;
  - two-hop expansion includes second layer and reports summary;
  - max node truncation sets a warning flag;
  - path search finds an indirect path and returns edge provenance;
  - path search hides rejected relationships by default.
- API tests verify endpoint payloads and validation.
- Streamlit tests verify controls call services/API wrappers and render no-path/path states.

## Acceptance Criteria

- Existing one-hop graph tests and API behavior remain compatible.
- A user can retrieve a two-hop graph with a bounded node count.
- A user can query paths between two entity ids and see explanatory edge steps.
- No graph query can return unbounded nodes by default.
- `uv --cache-dir .uv-cache run pytest` and `uv --cache-dir .uv-cache run ruff check .` pass.

