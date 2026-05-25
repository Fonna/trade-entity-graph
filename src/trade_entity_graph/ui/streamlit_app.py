"""Streamlit MVP workbench."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, MutableMapping, TypedDict

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components

from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.entity_service import get_entity_detail, search_entities
from trade_entity_graph.services.export_service import export_relationship_rows
from trade_entity_graph.services.graph_service import get_ego_graph
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    generate_order_role_edges,
    get_relationship_detail,
    get_relationship_evidence,
)
from trade_entity_graph.services.review_service import (
    create_manual_relationship,
    decide_relationship,
)

TAB_LABELS = ["数据导入", "企业搜索", "关系图谱", "关系详情", "人工审核", "导出"]

SELECTED_CLAIM_STATE_KEY = "selected_claim_id"
REVIEW_CLAIM_WIDGET_KEY = "review_claim_id"


class IntroSection(TypedDict):
    title: str
    items: list[str]


INTRO_SECTIONS: list[IntroSection] = [
    {
        "title": "数据基础",
        "items": [
            "企业文件中的标准名会生成企业主体，作为后续图谱分析的主数据。",
            "原始名、清洗名、别名会记录为企业别名，用于匹配订单中的不同写法。",
        ],
    },
    {
        "title": "关系建立逻辑",
        "items": [
            "订单里的下单客户、发货人、收货人、通知人会先匹配标准名和别名。",
            "匹配成功后系统使用 entity_id 建立订单角色边，避免只靠文本名称建关系。",
        ],
    },
    {
        "title": "关系结果含义",
        "items": [
            "订单角色边是证据，说明两个企业在同一票订单中出现过角色关联。",
            "系统会聚合证据形成候选关系，人工审核后再作为更可信的关系使用。",
        ],
    },
    {
        "title": "推荐操作流程",
        "items": [
            "先在数据导入页导入企业和订单文件，再搜索企业确认主体与别名。",
            "随后查看一跳关系图谱和关系证据，必要时在人工审核页确认、否定或补充关系。",
            "审核完成后，可以在导出页导出中心企业的关系明细。",
        ],
    },
    {
        "title": "文件字段要求",
        "items": [
            "企业文件至少需要标准名；国家和主体类型暂时可选，不影响基础导入。",
            "建议提供原始名或清洗名，以提升订单角色名称匹配率。",
            "订单文件常用字段包括订单号、下单客户、发货人、收货人、通知人、TEU、产品名称、目的国。",
            "导入时系统会把原始文件复制到 data/raw/imports/<run_id>/ 作为归档，不移动原文件。",
        ],
    },
]


def get_selected_claim_id(
    *, state: MutableMapping[str, Any] | None = None
) -> str:
    """Return the claim id selected from the graph tab."""

    target_state = st.session_state if state is None else state
    return str(target_state.get(SELECTED_CLAIM_STATE_KEY, "") or "")


def set_selected_claim_id(
    claim_id: str,
    *, state: MutableMapping[str, Any] | None = None,
) -> str:
    """Persist a selected claim id for the manual review tab."""

    target_state = st.session_state if state is None else state
    target_state[SELECTED_CLAIM_STATE_KEY] = claim_id
    target_state[REVIEW_CLAIM_WIDGET_KEY] = claim_id
    return claim_id


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


def get_candidate_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Return pending relationship claim edges from a graph payload."""

    return [
        edge
        for edge in graph.get("edges", [])
        if edge.get("edge_type") == "relationship_claim"
    ]


def render_intro() -> None:
    """Render concise product guidance above the main workflow tabs."""

    with st.expander("基础逻辑与使用方法", expanded=True):
        st.caption("这部分用于帮助第一次使用时理解数据如何进入图谱、关系如何产生。")
        for section in INTRO_SECTIONS:
            st.markdown(f"**{section['title']}**")
            for item in section["items"]:
                st.markdown(f"- {item}")


def render_import_tab() -> None:
    """Render the import workflow."""

    st.subheader("导入 Excel/CSV")
    entities_path = st.text_input("企业清洗结果文件路径")
    orders_path = st.text_input("订单明细文件路径")
    relationships_path = st.text_input("已有关系候选文件路径")
    imported_by = st.text_input("导入人", value="local_user")
    if st.button("开始导入"):
        result = run_import(
            ImportInputs(
                entities_path=Path(entities_path) if entities_path else None,
                orders_path=Path(orders_path) if orders_path else None,
                relationships_path=Path(relationships_path) if relationships_path else None,
                imported_by=imported_by,
            )
        )
        edge_result = generate_order_role_edges(run_id=result.run_id)
        claim_result = aggregate_relationship_claims(run_id=result.run_id)
        st.success(f"导入完成，批次号：{result.run_id}")
        if result.archived_files:
            st.info(f"原始文件已归档到 data/raw/imports/{result.run_id}/")
            st.dataframe(result.archived_files)
        st.json({**result.__dict__, **edge_result, **claim_result})


def render_search_tab() -> None:
    """Render entity search."""

    st.subheader("企业搜索")
    query = st.text_input("企业名称或别名")
    if query:
        matches = search_entities(query)
        st.dataframe(matches)
        selected = st.text_input("查看详情的企业 ID")
        if selected:
            st.json(get_entity_detail(selected))


def render_graph_tab() -> None:
    """Render one-hop graph visualization and candidate handoff."""

    st.subheader("一跳关系图谱")
    center_entity_id = st.text_input("中心企业 ID")
    include_rejected = st.checkbox("包含已否定的人工关系")
    if not center_entity_id:
        st.info("请输入中心企业 ID 后查看一跳关系图谱。")
        return

    graph = get_ego_graph(center_entity_id, include_rejected=include_rejected)
    summary = graph["summary"]
    metric_cols = st.columns(4)
    metric_cols[0].metric("节点数", summary["node_count"])
    metric_cols[1].metric("边数", summary["edge_count"])
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

def render_relationship_detail_tab() -> None:
    """Render relationship details and evidence."""

    st.subheader("关系详情")
    relationship_id = st.text_input("关系 ID 或候选关系 ID")
    if relationship_id:
        st.json(get_relationship_detail(relationship_id))
        st.dataframe(get_relationship_evidence(relationship_id))


def render_review_tab() -> None:
    """Render manual review actions."""

    st.subheader("人工审核")
    selected_claim_id = get_selected_claim_id()
    if selected_claim_id and REVIEW_CLAIM_WIDGET_KEY not in st.session_state:
        st.session_state[REVIEW_CLAIM_WIDGET_KEY] = selected_claim_id
    claim_id = st.text_input("候选关系 ID", key=REVIEW_CLAIM_WIDGET_KEY)
    action_type = st.selectbox("审核动作", ["confirm", "reject", "modify"])
    relation_type = st.text_input("关系类型", value="trading_partner")
    reason = st.text_area("判断理由")
    operator = st.text_input("操作人", value="local_user")
    if st.button("提交审核") and claim_id:
        st.json(
            decide_relationship(
                claim_id,
                action_type=action_type,
                relation_type=relation_type,
                reason=reason,
                operator=operator,
            )
        )

    st.divider()
    st.subheader("人工新增关系")
    from_entity_id = st.text_input("起点企业 ID")
    to_entity_id = st.text_input("终点企业 ID")
    manual_relation_type = st.text_input("人工关系类型", value="trading_partner")
    manual_reason = st.text_area("人工新增理由")
    if st.button("创建人工关系") and from_entity_id and to_entity_id:
        st.json(
            create_manual_relationship(
                from_entity_id,
                to_entity_id,
                relation_type=manual_relation_type,
                reason=manual_reason,
                operator=operator,
            )
        )


def render_export_tab() -> None:
    """Render export preview."""

    st.subheader("导出关系明细")
    center_entity_id = st.text_input("导出中心企业 ID")
    include_rejected = st.checkbox("导出时包含已否定关系")
    if center_entity_id:
        rows = export_relationship_rows(center_entity_id, include_rejected=include_rejected)
        st.dataframe(rows)
        st.download_button(
            "下载 JSON",
            data=str(rows),
            file_name=f"{center_entity_id}_relationships.txt",
        )


def main() -> None:
    st.set_page_config(page_title="企业关系图谱", layout="wide")
    st.title("企业关系图谱")
    st.caption("MVP P0 工作台：导入、搜索、图谱、审核和导出闭环。")
    render_intro()
    tabs = st.tabs(TAB_LABELS)
    with tabs[0]:
        render_import_tab()
    with tabs[1]:
        render_search_tab()
    with tabs[2]:
        render_graph_tab()
    with tabs[3]:
        render_relationship_detail_tab()
    with tabs[4]:
        render_review_tab()
    with tabs[5]:
        render_export_tab()


if __name__ == "__main__":
    main()
