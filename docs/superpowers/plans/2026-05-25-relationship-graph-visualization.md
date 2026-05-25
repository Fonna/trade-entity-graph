# Relationship Graph Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Streamlit relationship graph visualization that shows final relationships, pending candidate relationships, and order evidence edges around a searched center entity, with candidate `claim_id` handoff to the existing manual review tab.

**Architecture:** Extend the existing graph service so `get_ego_graph()` returns pending `relationship_claim` edges in the same one-hop graph payload while hiding claims already reviewed into `curated_relationship`. Add pure Streamlit UI helpers for SVG rendering and `session_state` handoff, then wire them into the existing graph and review tabs without duplicating review submission logic.

**Tech Stack:** Python 3.12, SQLite, Streamlit, NetworkX, pytest, existing `trade_entity_graph` services.

---

## File Structure

- Modify `src/trade_entity_graph/services/graph_service.py`
  - Keep responsibility as the one-hop graph query service.
  - Extend `get_ego_graph()` to include unreviewed candidate edges and candidate endpoint nodes.
  - Preserve backward-compatible fields used by current tests: `id`, `source`, `target`, `edge_type`, `relation_type`, `status`, `order_count`, `teu`.
- Modify `src/trade_entity_graph/ui/streamlit_app.py`
  - Add pure helper functions for SVG generation and selected-claim state.
  - Update `render_graph_tab()` to display SVG plus candidate handoff controls.
  - Update `render_review_tab()` so the claim input defaults from graph selection.
- Modify `tests/test_services_p0_flow.py`
  - Add service-level tests for pending candidate edges and reviewed-candidate hiding.
- Modify `tests/test_streamlit_app.py`
  - Add unit tests for SVG output and selected-claim state helpers.
- Modify `tests/test_demo_acceptance.py`
  - Add demo acceptance assertion that pending candidates are visible in `get_ego_graph()`.
- No schema migration, new dependency, or new API route is required.

---

### Task 1: Service Graph Includes Pending Candidate Edges

**Files:**
- Modify: `src/trade_entity_graph/services/graph_service.py`
- Test: `tests/test_services_p0_flow.py`

- [ ] **Step 1: Write the failing service test**

Append this test to `tests/test_services_p0_flow.py` after `test_entity_search_detail_graph_review_and_export_p0_flow`:

```python
def test_ego_graph_includes_pending_claims_and_hides_reviewed_claims(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    beta_claim_id = _claim_id(db_path, "ACME TRADING", "BETA FACTORY")

    graph = get_ego_graph(acme_id, db_path=db_path)

    pending_claim_edges = [
        edge for edge in graph["edges"] if edge["edge_type"] == "relationship_claim"
    ]
    pending_claim_ids = {edge["id"] for edge in pending_claim_edges}

    assert beta_claim_id in pending_claim_ids
    beta_claim_edge = next(edge for edge in pending_claim_edges if edge["id"] == beta_claim_id)
    assert beta_claim_edge["record_type"] == "relationship_claim"
    assert beta_claim_edge["relation_type"] == "trading_partner_candidate"
    assert beta_claim_edge["status"] == "candidate"
    assert beta_claim_edge["confidence_level"] == "medium"
    assert beta_claim_edge["confidence_score"] == 0.55
    assert beta_claim_edge["order_count"] == 2
    assert beta_claim_edge["total_teu"] == 7.5
    assert "2 orders" in beta_claim_edge["label"]

    reviewed = decide_relationship(
        beta_claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Confirmed by graph review",
        operator="tester",
        db_path=db_path,
    )
    reviewed_graph = get_ego_graph(acme_id, db_path=db_path)

    reviewed_pending_ids = {
        edge["id"]
        for edge in reviewed_graph["edges"]
        if edge["edge_type"] == "relationship_claim"
    }
    curated_ids = {
        edge["id"]
        for edge in reviewed_graph["edges"]
        if edge["edge_type"] == "curated_relationship"
    }

    assert beta_claim_id not in reviewed_pending_ids
    assert reviewed["relationship_id"] in curated_ids
```

- [ ] **Step 2: Run the service test to verify it fails**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py::test_ego_graph_includes_pending_claims_and_hides_reviewed_claims -q
```

Expected: FAIL because `get_ego_graph()` does not yet return `relationship_claim` edges.

- [ ] **Step 3: Implement pending-claim edges in `graph_service.py`**

Replace `src/trade_entity_graph/services/graph_service.py` with this implementation:

```python
"""One-hop graph query service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection

PENDING_CLAIM_STATUSES = ("candidate", "pending_verify")


def _entity_node(row: Any, *, center_entity_id: str) -> dict[str, Any]:
    return {
        "id": row["entity_id"],
        "label": row["canonical_name"],
        "entity_type": row["entity_type"],
        "tags": row["tags"],
        "is_center": row["entity_id"] == center_entity_id,
    }


def _order_edge(row: Any) -> dict[str, Any]:
    return {
        "id": row["edge_id"],
        "source": row["from_entity_id"],
        "target": row["to_entity_id"],
        "edge_type": "order_role_edge",
        "record_type": "order_role_edge",
        "relation_type": row["role_pair_type"],
        "status": "evidence",
        "confidence_level": None,
        "confidence_score": None,
        "order_count": 1,
        "total_teu": row["teu"],
        "teu": row["teu"],
        "label": row["role_pair_type"],
    }


def _curated_edge(row: Any) -> dict[str, Any]:
    return {
        "id": row["relationship_id"],
        "source": row["from_entity_id"],
        "target": row["to_entity_id"],
        "edge_type": "curated_relationship",
        "record_type": "curated_relationship",
        "relation_type": row["relation_type"],
        "status": row["relation_status"],
        "confidence_level": row["confidence_level"],
        "confidence_score": row["confidence_score"],
        "order_count": None,
        "total_teu": None,
        "teu": None,
        "label": f"{row['relation_type']} / {row['relation_status']}",
    }


def _claim_edge(row: Any) -> dict[str, Any]:
    reason = row["recommendation_reason"] or ""
    order_count = row["order_count"] or 0
    total_teu = row["total_teu"] or 0
    label_parts = [row["candidate_relation_type"], f"{order_count} orders"]
    if total_teu:
        label_parts.append(f"{total_teu:g} TEU")
    return {
        "id": row["claim_id"],
        "source": row["from_entity_id"],
        "target": row["to_entity_id"],
        "edge_type": "relationship_claim",
        "record_type": "relationship_claim",
        "relation_type": row["candidate_relation_type"],
        "status": row["relation_status"],
        "confidence_level": row["confidence_level"],
        "confidence_score": row["confidence_score"],
        "order_count": order_count,
        "total_teu": total_teu,
        "teu": total_teu,
        "label": " / ".join(label_parts),
        "recommendation_reason": reason,
    }


def get_ego_graph(
    center_entity_id: str,
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
) -> dict[str, Any]:
    """Return one-hop nodes and edges around a center entity."""

    with get_connection(db_path) as connection:
        entity_rows = connection.execute(
            """
            SELECT DISTINCT e.*
            FROM entity e
            WHERE e.entity_id = ?
               OR e.entity_id IN (
                    SELECT to_entity_id FROM order_role_edge WHERE from_entity_id = ?
                    UNION
                    SELECT from_entity_id FROM order_role_edge WHERE to_entity_id = ?
                    UNION
                    SELECT to_entity_id FROM curated_relationship WHERE from_entity_id = ?
                    UNION
                    SELECT from_entity_id FROM curated_relationship WHERE to_entity_id = ?
                    UNION
                    SELECT to_entity_id
                    FROM relationship_claim rc
                    WHERE rc.from_entity_id = ?
                      AND rc.relation_status IN ('candidate', 'pending_verify')
                      AND NOT EXISTS (
                          SELECT 1
                          FROM curated_relationship cr
                          WHERE cr.decision_source = rc.claim_id
                      )
                    UNION
                    SELECT from_entity_id
                    FROM relationship_claim rc
                    WHERE rc.to_entity_id = ?
                      AND rc.relation_status IN ('candidate', 'pending_verify')
                      AND NOT EXISTS (
                          SELECT 1
                          FROM curated_relationship cr
                          WHERE cr.decision_source = rc.claim_id
                      )
               )
            ORDER BY e.canonical_name
            """,
            (
                center_entity_id,
                center_entity_id,
                center_entity_id,
                center_entity_id,
                center_entity_id,
                center_entity_id,
                center_entity_id,
            ),
        ).fetchall()
        order_edges = connection.execute(
            """
            SELECT * FROM order_role_edge
            WHERE from_entity_id = ? OR to_entity_id = ?
            ORDER BY order_id, role_pair_type
            """,
            (center_entity_id, center_entity_id),
        ).fetchall()
        curated_sql = """
            SELECT * FROM curated_relationship
            WHERE from_entity_id = ? OR to_entity_id = ?
            ORDER BY created_at
        """
        curated_params = (center_entity_id, center_entity_id)
        if not include_rejected:
            curated_sql = """
                SELECT * FROM curated_relationship
                WHERE (from_entity_id = ? OR to_entity_id = ?)
                  AND relation_status != 'rejected'
                ORDER BY created_at
            """
        curated_edges = connection.execute(curated_sql, curated_params).fetchall()
        claim_edges = connection.execute(
            """
            SELECT *
            FROM relationship_claim rc
            WHERE (rc.from_entity_id = ? OR rc.to_entity_id = ?)
              AND rc.relation_status IN ('candidate', 'pending_verify')
              AND NOT EXISTS (
                  SELECT 1
                  FROM curated_relationship cr
                  WHERE cr.decision_source = rc.claim_id
              )
            ORDER BY rc.confidence_score DESC, rc.order_count DESC, rc.created_at
            """,
            (center_entity_id, center_entity_id),
        ).fetchall()

        edges = [_order_edge(row) for row in order_edges]
        edges.extend(_curated_edge(row) for row in curated_edges)
        edges.extend(_claim_edge(row) for row in claim_edges)

        return {
            "center_entity_id": center_entity_id,
            "nodes": [_entity_node(row, center_entity_id=center_entity_id) for row in entity_rows],
            "edges": edges,
            "summary": {
                "node_count": len(entity_rows),
                "edge_count": len(edges),
                "candidate_edge_count": len(claim_edges),
                "curated_edge_count": len(curated_edges),
                "order_edge_count": len(order_edges),
            },
        }
```

- [ ] **Step 4: Run the service test to verify it passes**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py::test_ego_graph_includes_pending_claims_and_hides_reviewed_claims -q
```

Expected: PASS.

- [ ] **Step 5: Run the existing P0 service flow test**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py -q
```

Expected: all tests in `tests/test_services_p0_flow.py` PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src\trade_entity_graph\services\graph_service.py tests\test_services_p0_flow.py
git commit -m "feat: include pending claims in ego graph"
```

---

### Task 2: SVG Renderer and Selected-Claim State Helpers

**Files:**
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Test: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write the failing UI helper tests**

Append these tests to `tests/test_streamlit_app.py`:

```python
def test_graph_svg_renderer_outputs_candidate_and_curated_styles() -> None:
    graph = {
        "center_entity_id": "ENT_CENTER",
        "nodes": [
            {"id": "ENT_CENTER", "label": "CENTER CO", "entity_type": "customer", "tags": None},
            {"id": "ENT_FACTORY", "label": "FACTORY CO", "entity_type": "factory", "tags": None},
            {"id": "ENT_BUYER", "label": "BUYER CO", "entity_type": "buyer", "tags": None},
        ],
        "edges": [
            {
                "id": "REL_1",
                "source": "ENT_CENTER",
                "target": "ENT_FACTORY",
                "edge_type": "curated_relationship",
                "record_type": "curated_relationship",
                "relation_type": "trading_partner",
                "status": "verified",
                "label": "trading_partner / verified",
            },
            {
                "id": "CLM_1",
                "source": "ENT_CENTER",
                "target": "ENT_BUYER",
                "edge_type": "relationship_claim",
                "record_type": "relationship_claim",
                "relation_type": "subsidiary_candidate",
                "status": "candidate",
                "label": "subsidiary_candidate / 2 orders",
            },
        ],
        "summary": {"node_count": 3, "edge_count": 2},
    }

    svg = streamlit_app.render_graph_svg(graph, width=640, height=360)

    assert "<svg" in svg
    assert "CENTER CO" in svg
    assert "FACTORY CO" in svg
    assert "BUYER CO" in svg
    assert "CLM_1" in svg
    assert "stroke-dasharray" in svg
    assert "待审核候选" in svg


def test_selected_claim_state_helpers_round_trip() -> None:
    state: dict[str, str] = {}

    selected = streamlit_app.set_selected_claim_id("CLM_123", state=state)

    assert selected == "CLM_123"
    assert state["selected_claim_id"] == "CLM_123"
    assert state["review_claim_id"] == "CLM_123"
    assert streamlit_app.get_selected_claim_id(state=state) == "CLM_123"
```

- [ ] **Step 2: Run the UI helper tests to verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py::test_graph_svg_renderer_outputs_candidate_and_curated_styles tests\test_streamlit_app.py::test_selected_claim_state_helpers_round_trip -q
```

Expected: FAIL because `render_graph_svg`, `set_selected_claim_id`, and `get_selected_claim_id` do not exist.

- [ ] **Step 3: Add imports and state constants**

In `src/trade_entity_graph/ui/streamlit_app.py`, update imports near the top:

```python
import html
from pathlib import Path
from typing import Any, MutableMapping, TypedDict

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
```

Add this constant below `TAB_LABELS`:

```python
SELECTED_CLAIM_STATE_KEY = "selected_claim_id"
REVIEW_CLAIM_WIDGET_KEY = "review_claim_id"
```

- [ ] **Step 4: Add selected-claim state helpers**

Add these functions after `INTRO_SECTIONS`:

```python
def get_selected_claim_id(
    *, state: MutableMapping[str, Any] | None = None
) -> str:
    """Return the claim id selected from the graph tab."""

    target_state = st.session_state if state is None else state
    return str(target_state.get(SELECTED_CLAIM_STATE_KEY, "") or "")


def set_selected_claim_id(
    claim_id: str,
    *,
    state: MutableMapping[str, Any] | None = None,
) -> str:
    """Persist a selected claim id for the manual review tab."""

    target_state = st.session_state if state is None else state
    target_state[SELECTED_CLAIM_STATE_KEY] = claim_id
    target_state[REVIEW_CLAIM_WIDGET_KEY] = claim_id
    return claim_id
```

- [ ] **Step 5: Add SVG rendering helpers**

Add these functions after the state helpers:

```python
def _edge_style(edge: dict[str, Any]) -> dict[str, str]:
    edge_type = edge.get("edge_type")
    status = edge.get("status")
    if edge_type == "relationship_claim":
        return {"color": "#f59e0b", "dash": "10 7", "width": "3"}
    if edge_type == "curated_relationship" and status == "rejected":
        return {"color": "#ef4444", "dash": "6 6", "width": "2"}
    if edge_type == "curated_relationship":
        return {"color": "#2563eb", "dash": "", "width": "3"}
    return {"color": "#64748b", "dash": "3 7", "width": "1.8"}


def _node_label(node: dict[str, Any]) -> str:
    label = str(node.get("label") or node.get("id") or "")
    return label if len(label) <= 22 else f"{label[:19]}..."


def render_graph_svg(graph: dict[str, Any], *, width: int = 900, height: int = 520) -> str:
    """Render a one-hop graph payload as standalone SVG HTML."""

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    center_entity_id = graph.get("center_entity_id")
    if not nodes:
        escaped_center = html.escape(str(center_entity_id or ""))
        return (
            f"<div style='padding:24px;border:1px solid #e2e8f0;border-radius:16px;'>"
            f"未找到企业或暂无节点：<code>{escaped_center}</code></div>"
        )

    nx_graph = nx.Graph()
    for node in nodes:
        nx_graph.add_node(node["id"])
    for edge in edges:
        if edge.get("source") in nx_graph and edge.get("target") in nx_graph:
            nx_graph.add_edge(edge["source"], edge["target"])

    if len(nx_graph.nodes) == 1:
        positions = {next(iter(nx_graph.nodes)): (0.0, 0.0)}
    else:
        positions = nx.spring_layout(nx_graph, seed=42)
    if center_entity_id in positions:
        positions[center_entity_id] = (0.0, 0.0)

    xs = [point[0] for point in positions.values()]
    ys = [point[1] for point in positions.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 0.1)
    span_y = max(max_y - min_y, 0.1)

    def project(node_id: str) -> tuple[float, float]:
        x, y = positions[node_id]
        px = 70 + ((x - min_x) / span_x) * (width - 140)
        py = 70 + ((y - min_y) / span_y) * (height - 140)
        return px, py

    edge_markup: list[str] = []
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in positions or target not in positions:
            continue
        x1, y1 = project(source)
        x2, y2 = project(target)
        style = _edge_style(edge)
        dash = f" stroke-dasharray='{style['dash']}'" if style["dash"] else ""
        title = html.escape(f"{edge.get('id', '')} {edge.get('label', '')}")
        edge_markup.append(
            f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
            f"stroke='{style['color']}' stroke-width='{style['width']}'{dash}>"
            f"<title>{title}</title></line>"
        )

    node_by_id = {node["id"]: node for node in nodes}
    node_markup: list[str] = []
    for node_id in nx_graph.nodes:
        node = node_by_id[node_id]
        x, y = project(node_id)
        is_center = node_id == center_entity_id
        radius = 34 if is_center else 27
        fill = "#0f172a" if is_center else "#eff6ff"
        stroke = "#0f172a" if is_center else "#93c5fd"
        text_color = "#ffffff" if is_center else "#1e3a8a"
        label = html.escape(_node_label(node))
        full_label = html.escape(str(node.get("label") or node_id))
        node_markup.append(
            f"<g><circle cx='{x:.1f}' cy='{y:.1f}' r='{radius}' fill='{fill}' "
            f"stroke='{stroke}' stroke-width='2'><title>{full_label}</title></circle>"
            f"<text x='{x:.1f}' y='{y + 4:.1f}' text-anchor='middle' "
            f"font-size='11' font-weight='700' fill='{text_color}'>{label}</text></g>"
        )

    empty_hint = ""
    if not edges:
        empty_hint = (
            f"<text x='{width / 2:.1f}' y='{height - 34}' text-anchor='middle' "
            "fill='#64748b' font-size='14'>暂无一跳关系</text>"
        )

    return f"""
    <div style="border:1px solid #dbe5ef;border-radius:18px;padding:12px;background:#f8fafc;">
      <svg viewBox="0 0 {width} {height}" width="100%" height="{height}"
           role="img" aria-label="relationship graph">
        <rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#f8fafc" />
        {"".join(edge_markup)}
        {"".join(node_markup)}
        {empty_hint}
      </svg>
      <div style="display:flex;gap:16px;flex-wrap:wrap;color:#334155;font-size:13px;">
        <span><b style="color:#2563eb;">蓝色实线</b> 最终关系</span>
        <span><b style="color:#f59e0b;">橙色虚线</b> 待审核候选</span>
        <span><b style="color:#64748b;">灰色点线</b> 订单证据</span>
      </div>
    </div>
    """
```

- [ ] **Step 6: Run the UI helper tests to verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py::test_graph_svg_renderer_outputs_candidate_and_curated_styles tests\test_streamlit_app.py::test_selected_claim_state_helpers_round_trip -q
```

Expected: PASS.

- [ ] **Step 7: Run all Streamlit module tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py -q
```

Expected: all tests in `tests/test_streamlit_app.py` PASS.

- [ ] **Step 8: Commit Task 2**

```powershell
git add src\trade_entity_graph\ui\streamlit_app.py tests\test_streamlit_app.py
git commit -m "feat: render relationship graph svg"
```

---

### Task 3: Wire Graph Tab to Candidate Handoff and Review Defaults

**Files:**
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Test: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write the failing UI integration test**

Append this test to `tests/test_streamlit_app.py`:

```python
def test_streamlit_app_exposes_graph_handoff_helpers() -> None:
    assert callable(streamlit_app.render_graph_svg)
    assert callable(streamlit_app.get_selected_claim_id)
    assert callable(streamlit_app.set_selected_claim_id)
    assert streamlit_app.SELECTED_CLAIM_STATE_KEY == "selected_claim_id"
    assert streamlit_app.REVIEW_CLAIM_WIDGET_KEY == "review_claim_id"
```

This test may already pass after Task 2. Keep it because it protects the integration contract used by the graph and review tabs.

- [ ] **Step 2: Add candidate edge helper**

Add this helper near `render_graph_svg()` in `src/trade_entity_graph/ui/streamlit_app.py`:

```python
def get_candidate_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Return pending relationship claim edges from a graph payload."""

    return [
        edge
        for edge in graph.get("edges", [])
        if edge.get("edge_type") == "relationship_claim"
    ]
```

- [ ] **Step 3: Replace `render_graph_tab()` with visual graph UI**

Replace the current `render_graph_tab()` function with:

```python
def render_graph_tab() -> None:
    """Render one-hop graph visualization and candidate handoff."""

    st.subheader("涓€璺冲叧绯诲浘璋?")
    center_entity_id = st.text_input("涓績浼佷笟 ID")
    include_rejected = st.checkbox("鍖呭惈宸插惁瀹氱殑浜哄伐鍏崇郴")
    if not center_entity_id:
        st.info("请输入中心企业 ID 后查看一跳关系图谱。")
        return

    graph = get_ego_graph(center_entity_id, include_rejected=include_rejected)
    summary = graph["summary"]
    metric_cols = st.columns(4)
    metric_cols[0].metric("鑺傜偣鏁?, summary["node_count"])
    metric_cols[1].metric("杈规暟", summary["edge_count"])
    metric_cols[2].metric("待审核候选", summary.get("candidate_edge_count", 0))
    metric_cols[3].metric("最终关系", summary.get("curated_edge_count", 0))

    components.html(render_graph_svg(graph), height=620, scrolling=True)

    candidate_edges = get_candidate_edges(graph)
    if candidate_edges:
        st.markdown("**待审核候选关系**")
        selected_claim_id = st.selectbox(
            "选择要带到人工审核 tab 的候选关系",
            [edge["id"] for edge in candidate_edges],
            format_func=lambda claim_id: next(
                (
                    f"{edge['id']} | {edge['relation_type']} | "
                    f"{edge.get('confidence_level') or '-'} | "
                    f"{edge.get('order_count') or 0} orders"
                    for edge in candidate_edges
                    if edge["id"] == claim_id
                ),
                claim_id,
            ),
        )
        selected_edge = next(edge for edge in candidate_edges if edge["id"] == selected_claim_id)
        st.json(selected_edge)
        if st.button("带到人工审核 tab"):
            set_selected_claim_id(selected_claim_id)
            st.success(f"已选择候选关系 {selected_claim_id}，请切换到人工审核 tab 继续处理。")
    else:
        st.info("当前中心企业暂无待审核候选关系。")

    with st.expander("节点与边数据"):
        st.dataframe(graph["nodes"])
        st.dataframe(graph["edges"])
```

- [ ] **Step 4: Update `render_review_tab()` claim input**

In `render_review_tab()`, replace:

```python
    claim_id = st.text_input("鍊欓€夊叧绯?ID")
```

with:

```python
    claim_id = st.text_input(
        "鍊欓€夊叧绯?ID",
        value=get_selected_claim_id(),
        key=REVIEW_CLAIM_WIDGET_KEY,
    )
```

- [ ] **Step 5: Add helper exposure to the existing callable test**

In `test_streamlit_app_exposes_mvp_tab_renderers`, add:

```python
    assert callable(streamlit_app.render_graph_svg)
    assert callable(streamlit_app.get_candidate_edges)
    assert callable(streamlit_app.get_selected_claim_id)
    assert callable(streamlit_app.set_selected_claim_id)
```

- [ ] **Step 6: Run Streamlit tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py -q
```

Expected: all tests in `tests/test_streamlit_app.py` PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add src\trade_entity_graph\ui\streamlit_app.py tests\test_streamlit_app.py
git commit -m "feat: hand off graph claims to review tab"
```

---

### Task 4: Demo Acceptance Coverage for Pending Candidate Visibility

**Files:**
- Modify: `tests/test_demo_acceptance.py`

- [ ] **Step 1: Write the failing demo acceptance assertion**

In `tests/test_demo_acceptance.py`, add `decide_relationship` import:

```python
from trade_entity_graph.services.review_service import decide_relationship
```

Append this test at the end of the file:

```python
def test_demo_pending_candidate_is_visible_then_hidden_after_review(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "demo"
    db_path = tmp_path / "trade_entity_graph.db"
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(tmp_path / "archives"))
    write_demo_data(output_dir)
    import_demo_data(output_dir=output_dir, db_path=db_path)
    seed_demo_reviews(db_path=db_path)

    with get_connection(db_path) as connection:
        pending_claim = connection.execute(
            """
            SELECT *
            FROM relationship_claim rc
            WHERE NOT EXISTS (
                SELECT 1
                FROM curated_relationship cr
                WHERE cr.decision_source = rc.claim_id
            )
            ORDER BY rc.confidence_score DESC, rc.order_count DESC
            LIMIT 1
            """
        ).fetchone()

    assert pending_claim is not None
    center_id = pending_claim["from_entity_id"]
    claim_id = pending_claim["claim_id"]

    graph = get_ego_graph(center_id, db_path=db_path)
    pending_graph_claims = {
        edge["id"]
        for edge in graph["edges"]
        if edge["edge_type"] == "relationship_claim"
    }

    assert claim_id in pending_graph_claims

    reviewed = decide_relationship(
        claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Demo candidate confirmed from graph",
        operator="tester",
        db_path=db_path,
    )
    graph_after_review = get_ego_graph(center_id, db_path=db_path)
    pending_after_review = {
        edge["id"]
        for edge in graph_after_review["edges"]
        if edge["edge_type"] == "relationship_claim"
    }
    curated_after_review = {
        edge["id"]
        for edge in graph_after_review["edges"]
        if edge["edge_type"] == "curated_relationship"
    }

    assert claim_id not in pending_after_review
    assert reviewed["relationship_id"] in curated_after_review
```

- [ ] **Step 2: Run the demo acceptance test**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py::test_demo_pending_candidate_is_visible_then_hidden_after_review -q
```

Expected: PASS if Task 1 is complete. If it fails, inspect whether the selected pending claim touches the center through `from_entity_id` and whether `decision_source` is written by `decide_relationship()`.

- [ ] **Step 3: Run all demo acceptance tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_demo_acceptance.py -q
```

Expected: all tests in `tests/test_demo_acceptance.py` PASS.

- [ ] **Step 4: Commit Task 4**

```powershell
git add tests\test_demo_acceptance.py
git commit -m "test: cover graph candidate review flow"
```

---

### Task 5: Full Verification and Manual Smoke Check

**Files:**
- No planned source edits.

- [ ] **Step 1: Run the focused graph and UI tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py tests\test_streamlit_app.py tests\test_demo_acceptance.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run the full test suite**

Run:

```powershell
uv --cache-dir .uv-cache run pytest
```

Expected: full test suite PASS. If `.pytest_cache` write-permission warnings appear but pytest exits with code 0, record the warning in the final notes.

- [ ] **Step 3: Optional local UI smoke run**

Run the Streamlit app if manual visual verification is needed:

```powershell
uv --cache-dir .uv-cache run python scripts\run_ui.py
```

Expected: Streamlit starts, the graph tab renders an SVG for a valid demo `entity_id`, and selecting a candidate fills the manual review tab claim ID after switching tabs.

- [ ] **Step 4: Inspect final git status**

Run:

```powershell
git status --short
```

Expected: only intentional source/test changes are tracked or staged, and local log files remain untracked.

- [ ] **Step 5: Final commit if Task 5 required edits**

If Task 5 required fixes, commit those exact files:

```powershell
git add src\trade_entity_graph\services\graph_service.py src\trade_entity_graph\ui\streamlit_app.py tests\test_services_p0_flow.py tests\test_streamlit_app.py tests\test_demo_acceptance.py
git commit -m "fix: stabilize graph visualization"
```

If Task 5 required no edits, do not create an empty commit.

---

## Self-Review

- Spec coverage: Task 1 covers graph service candidate visibility, reviewed-candidate hiding, rejected final relationship behavior preservation, and summary counts. Tasks 2 and 3 cover SVG visualization, visual edge categories, candidate detail display, and manual-review tab handoff. Task 4 covers the demo acceptance flow. Task 5 covers verification.
- Incomplete-marker scan: no incomplete markers remain in the plan. Every code-changing step includes concrete code or an exact replacement.
- Type consistency: graph edges use `edge_type`, `record_type`, `relation_type`, `status`, `confidence_level`, `confidence_score`, `order_count`, `total_teu`, `teu`, and `label` consistently across service, UI, and tests.
- Scope check: the plan stays within one-hop Streamlit visualization and does not add graph-page review submission, two-hop search, schema changes, or new dependencies.
