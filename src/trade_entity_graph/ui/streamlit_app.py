"""Streamlit MVP workbench."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import streamlit as st

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
    """Render one-hop graph JSON."""

    st.subheader("一跳关系图谱")
    center_entity_id = st.text_input("中心企业 ID")
    include_rejected = st.checkbox("包含已否定的人工关系")
    if center_entity_id:
        graph = get_ego_graph(center_entity_id, include_rejected=include_rejected)
        st.metric("节点数", graph["summary"]["node_count"])
        st.metric("边数", graph["summary"]["edge_count"])
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
    claim_id = st.text_input("候选关系 ID")
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
