"""Streamlit MVP workbench."""

from __future__ import annotations

import html
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, TypedDict

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components

from trade_entity_graph.importers.models import ImportInputs
from trade_entity_graph.importers.pipeline import run_import
from trade_entity_graph.services.entity_service import get_entity_detail, search_entities
from trade_entity_graph.services.export_service import export_relationship_rows
from trade_entity_graph.services.graph_service import find_entity_paths, get_ego_graph
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
from trade_entity_graph.services.import_quality_service import (
    export_import_errors,
    find_duplicate_import,
    get_import_batch_detail,
    list_import_batches,
    list_import_errors,
)
from trade_entity_graph.services.relationship_service import (
    aggregate_relationship_claims,
    generate_order_role_edges,
    get_relationship_detail,
    get_relationship_evidence,
)
from trade_entity_graph.services.review_queue_service import (
    REVIEW_QUEUE_CONFIDENCE_LEVELS,
    REVIEW_QUEUE_STATUSES,
    list_review_queue,
)
from trade_entity_graph.services.review_service import (
    create_manual_relationship,
    decide_relationship,
    keep_history_for_claim,
    mark_claim_pending_verify,
    supersede_history_with_claim,
)

TAB_LABELS = ["数据导入", "企业搜索", "关系图谱", "关系详情", "待审核队列", "人工审核", "导出"]

SELECTED_CLAIM_STATE_KEY = "selected_claim_id"
REVIEW_CLAIM_WIDGET_KEY = "review_claim_id"
REVIEW_SUCCESS_FLASH_STATE_KEY = "review_success_flash"
REVIEW_CLEAR_CLAIM_STATE_KEY = "review_clear_claim_after_success"
DEFAULT_RELATION_TYPE = "trading_partner"
RELATION_TYPE_OPTIONS: tuple[str, ...] = (
    "trading_partner",
    "same_group",
    "subsidiary",
    "factory_node",
    "sales_center",
    "logistics_service",
    "same_entity",
    "co_order_role",
    "unknown",
    "rejected_relation",
)
RELATION_TYPE_LABELS: dict[str, str] = {
    "trading_partner": "普通贸易伙伴",
    "same_group": "同集团",
    "subsidiary": "子公司或海外公司",
    "factory_node": "海外工厂或生产节点",
    "sales_center": "销售中心",
    "logistics_service": "物流/货代/仓储/清关服务关系",
    "same_entity": "同一主体",
    "co_order_role": "订单角色共现",
    "unknown": "暂不确定",
    "rejected_relation": "否定关系",
}
CANDIDATE_TO_FINAL_RELATION_TYPE: dict[str, str] = {
    "trading_partner_candidate": "trading_partner",
    "factory_candidate": "factory_node",
    "sales_center_candidate": "sales_center",
    "same_group_candidate": "same_group",
    "subsidiary_candidate": "subsidiary",
    "logistics_service_candidate": "logistics_service",
    "same_entity_candidate": "same_entity",
    "co_order_role_candidate": "co_order_role",
    "unknown_candidate": "unknown",
}
TABLE_COLUMN_LABELS: dict[str, str] = {
    "entity_id": "企业ID",
    "canonical_name": "标准企业名称",
    "country": "国家/地区",
    "entity_type": "主体类型",
    "tags": "标签",
    "status": "状态",
    "id": "记录ID",
    "source": "起点企业ID",
    "target": "终点企业ID",
    "source_label": "起点企业",
    "target_label": "终点企业",
    "edge_type": "边类型",
    "record_type": "记录类型",
    "relation_type": "关系类型",
    "relation_status": "关系状态",
    "candidate_relation_type": "候选关系类型",
    "confidence_level": "置信等级",
    "confidence_score": "置信分",
    "order_count": "订单数",
    "total_teu": "总TEU",
    "teu": "TEU",
    "label": "标签",
    "recommendation_reason": "推荐理由",
    "relationship_id": "关系ID",
    "claim_id": "候选关系ID",
    "from_entity_id": "起点企业ID",
    "from_name": "起点企业",
    "to_entity_id": "终点企业ID",
    "to_name": "终点企业",
    "source_type": "来源类型",
    "decision_note": "判断备注",
    "verified_by": "审核人",
    "verified_at": "审核时间",
    "evidence_id": "证据ID",
    "order_id": "订单ID",
    "source_file": "来源文件",
    "source_sheet": "来源工作表",
    "source_row": "来源行",
    "run_id": "批次号",
    "imported_at": "导入时间",
    "last_activity_at": "最近处理时间",
    "queue_priority": "队列优先级",
    "review_action_hint": "建议处理方式",
    "role_pair_summary": "角色组合",
    "destination_summary": "目的国摘要",
    "product_summary": "产品摘要",
    "source_role": "来源角色",
    "original_path": "原始路径",
    "archived_path": "归档路径",
    "success_rows": "成功行数",
    "error_rows": "异常行数",
    "warning_rows": "警告行数",
    "blocking_error_count": "阻断异常数",
    "warning_count": "警告数",
    "file_role": "文件角色",
    "sheet_name": "工作表",
    "row_number": "行号",
    "column_name": "列名",
    "normalized_field": "标准字段",
    "raw_value": "原始值",
    "error_type": "异常类型",
    "severity": "严重级别",
    "message": "异常说明",
}
DISPLAY_VALUE_LABELS: dict[str, dict[str, str]] = {
    "entity_type": {
        "group": "集团",
        "subsidiary": "子公司/分支机构",
        "customer": "客户",
        "shipper": "发货人",
        "consignee": "收货人",
        "notify": "通知人",
        "buyer": "买方",
        "factory": "工厂",
    },
    "status": {
        "active": "有效",
        "inactive": "停用",
        "candidate": "候选",
        "pending_verify": "待验证",
        "history_conflict": "历史冲突",
        "history_matched": "匹配历史结论",
        "verified": "已确认",
        "rejected": "已否定",
        "deprecated": "已失效",
        "evidence": "证据",
    },
    "relation_status": {
        "candidate": "候选",
        "pending_verify": "待验证",
        "history_conflict": "历史冲突",
        "history_matched": "匹配历史结论",
        "verified": "已确认",
        "rejected": "已否定",
        "deprecated": "已失效",
    },
    "confidence_level": {
        "high": "高",
        "medium": "中",
        "low": "低",
    },
    "edge_type": {
        "relationship_claim": "候选关系",
        "curated_relationship": "最终关系",
        "order_role_edge": "订单角色边",
    },
    "record_type": {
        "relationship_claim": "候选关系",
        "curated_relationship": "最终关系",
        "order_role_edge": "订单角色边",
    },
    "severity": {"blocking": "阻断异常", "warning": "警告"},
    "error_type": {
        "missing_required_field": "缺少必需字段",
        "missing_required_value": "必填值为空",
        "unknown_entity_reference": "企业无法匹配",
        "invalid_numeric_value": "数值格式错误",
        "invalid_relationship_pair": "无效关系企业对",
        "field_mapping_error": "字段映射警告",
    },
}
ERROR_MESSAGE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Unknown relationship claim: ", "未找到候选关系："),
    ("Unknown curated relationship: ", "未找到最终关系："),
    (
        "Superseded relationship must be current-effective and match the claim pair",
        "被替代的历史关系必须仍然有效，并且与当前候选关系的企业对一致",
    ),
    ("Claim must be in one of ", "候选关系当前状态不允许执行该操作："),
    (
        "Claim already has a reviewed relationship: ",
        "该候选关系已存在审核后的最终关系：",
    ),
    (
        "Claim already finalized by history review: ",
        "该候选关系已被历史审核定稿：",
    ),
    (
        "Claim already finalized by history review",
        "该候选关系已被历史审核定稿",
    ),
    (
        "Claim has effective historical relationship context; use history-aware review action",
        "该候选关系存在有效历史关系，请使用历史关系相关的审核动作",
    ),
    (
        "No historical relationship found for claim: ",
        "未找到该候选关系对应的历史关系：",
    ),
    ("Unsupported action_type: ", "不支持的审核动作："),
    (
        "Claim must be in an allowed, unfinalized state to keep history",
        "候选关系必须处于允许且未定稿状态，才能沿用历史结论",
    ),
    (
        "Claim must be in an allowed, unfinalized state to mark pending verify",
        "候选关系必须处于允许且未定稿状态，才能标记为待验证",
    ),
)


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


def store_review_success_for_refresh(
    claim_id: str,
    result: dict[str, Any],
    *,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    """Persist a success message and request claim cleanup on the next rerun."""

    target_state = st.session_state if state is None else state
    target_state[REVIEW_SUCCESS_FLASH_STATE_KEY] = {
        "claim_id": claim_id,
        "result": result,
    }
    target_state[REVIEW_CLEAR_CLAIM_STATE_KEY] = True


def consume_review_refresh_state(
    *, state: MutableMapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """Clear reviewed claim selection before widgets are recreated."""

    target_state = st.session_state if state is None else state
    if target_state.pop(REVIEW_CLEAR_CLAIM_STATE_KEY, False):
        target_state.pop(SELECTED_CLAIM_STATE_KEY, None)
        target_state.pop(REVIEW_CLAIM_WIDGET_KEY, None)
    flash = target_state.pop(REVIEW_SUCCESS_FLASH_STATE_KEY, None)
    return flash if isinstance(flash, dict) else None


def request_streamlit_rerun() -> bool:
    """Request a Streamlit rerun when available."""

    rerun = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if not callable(rerun):
        return False
    rerun()
    return True


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


def _relation_type_index(relation_type: str) -> int:
    if relation_type in RELATION_TYPE_OPTIONS:
        return RELATION_TYPE_OPTIONS.index(relation_type)
    return RELATION_TYPE_OPTIONS.index(DEFAULT_RELATION_TYPE)


def final_relation_type_for_candidate(candidate_relation_type: str | None) -> str:
    """Map a candidate relation type to the safest likely final value."""

    if not candidate_relation_type:
        return DEFAULT_RELATION_TYPE
    return CANDIDATE_TO_FINAL_RELATION_TYPE.get(
        candidate_relation_type,
        DEFAULT_RELATION_TYPE,
    )


def format_relation_type_option(relation_type: str) -> str:
    """Return a user-friendly label while keeping the raw option value stable."""

    description = RELATION_TYPE_LABELS.get(relation_type)
    return f"{relation_type}（{description}）" if description else relation_type


def _format_display_value(column: str, value: Any) -> Any:
    if value is None or value == "":
        return "-"
    if column in {"relation_type", "candidate_relation_type"}:
        text = str(value)
        if text.endswith("_candidate"):
            final_type = final_relation_type_for_candidate(text)
            label = RELATION_TYPE_LABELS.get(final_type, text)
            return f"{label}（候选）"
        return RELATION_TYPE_LABELS.get(text, value)
    return DISPLAY_VALUE_LABELS.get(column, {}).get(str(value), value)


def localize_table_records(records: Any) -> Any:
    """Return table records with Chinese headers and common display values."""

    if not isinstance(records, list):
        return records
    localized_rows = []
    for row in records:
        if not isinstance(row, dict):
            localized_rows.append(row)
            continue
        localized_rows.append(
            {
                TABLE_COLUMN_LABELS.get(key, key): _format_display_value(key, value)
                for key, value in row.items()
            }
        )
    return localized_rows


def format_import_quality_status(summary: dict[str, Any]) -> str:
    """Return a short Chinese status label for an import quality summary."""
    blocking_count = int(summary.get("blocking_error_count") or 0)
    warning_count = int(summary.get("warning_count") or 0)
    if blocking_count == 0 and warning_count == 0:
        return "无异常"
    if blocking_count == 0:
        return f"仅警告：{warning_count} 条"
    return f"阻断异常：{blocking_count} 条，警告：{warning_count} 条"


def import_error_export_filename(run_id: str) -> str:
    """Return the CSV filename used for one import error export."""
    return f"{run_id}_import_errors.csv"


def format_error_message(error: Exception) -> str:
    """Translate known backend errors before showing them to users."""

    message = str(error)
    for english, chinese in ERROR_MESSAGE_PREFIXES:
        if message.startswith(english):
            return f"{chinese}{message.removeprefix(english)}"
    return message


def show_table(records: Any) -> None:
    """Render a Streamlit dataframe with localized business-facing labels."""

    st.dataframe(localize_table_records(records))


def _short_edge_label(edge: dict[str, Any]) -> str:
    label = str(edge.get("relation_type") or edge.get("label") or "")
    return label if len(label) <= 28 else f"{label[:25]}..."


def _edge_endpoint_label(edge: dict[str, Any], label_key: str, id_key: str) -> str:
    return str(
        edge.get(label_key)
        or edge.get(label_key.replace("_label", "_name"))
        or edge.get(id_key)
        or "-"
    )


def with_edge_display_names(
    edge: dict[str, Any], node_labels_by_id: dict[str, str]
) -> dict[str, Any]:
    """Return an edge copy with readable endpoint names filled from graph nodes."""

    enriched = dict(edge)
    source = str(edge.get("source") or "")
    target = str(edge.get("target") or "")
    enriched.setdefault("source_label", node_labels_by_id.get(source, source or "-"))
    enriched.setdefault("target_label", node_labels_by_id.get(target, target or "-"))
    return enriched


def format_entity_reference(
    entity: dict[str, Any] | None, *, fallback_id: str = ""
) -> str:
    """Format an entity id/name pair for manual review context."""

    if not entity:
        return f"未找到企业：{fallback_id}" if fallback_id else "未找到企业"

    entity_id = str(entity.get("entity_id") or fallback_id or "-")
    name = str(entity.get("canonical_name") or entity.get("label") or "-")
    return f"{name} ({entity_id})"


def format_relationship_detail_summary(detail: dict[str, Any] | None) -> str:
    """Format relationship/candidate details with endpoint names for reviewers."""

    if not detail:
        return "未找到候选关系或最终关系，请检查 ID 是否正确。"

    relationship_id = (
        detail.get("claim_id") or detail.get("relationship_id") or detail.get("id") or "-"
    )
    from_entity_id = str(detail.get("from_entity_id") or detail.get("source") or "")
    to_entity_id = str(detail.get("to_entity_id") or detail.get("target") or "")
    from_entity = format_entity_reference(
        {
            "entity_id": from_entity_id,
            "canonical_name": detail.get("from_name") or detail.get("source_label"),
        },
        fallback_id=from_entity_id,
    )
    to_entity = format_entity_reference(
        {
            "entity_id": to_entity_id,
            "canonical_name": detail.get("to_name") or detail.get("target_label"),
        },
        fallback_id=to_entity_id,
    )
    relation_type = (
        detail.get("candidate_relation_type") or detail.get("relation_type") or "-"
    )
    confidence = detail.get("confidence_level") or "-"
    order_count = detail.get("order_count") or 0
    return (
        f"{relationship_id} | {from_entity} -> {to_entity} | "
        f"{relation_type} | {confidence} | {order_count} orders"
    )


def _history_context(detail: dict[str, Any]) -> dict[str, Any]:
    context = detail.get("history_context")
    return context if isinstance(context, dict) else {}


def _history_relationship(context: dict[str, Any]) -> dict[str, Any]:
    relationship = context.get("history_relationship")
    return relationship if isinstance(relationship, dict) else {}


def _history_relationship_id(context: dict[str, Any]) -> str:
    relationship = _history_relationship(context)
    return str(
        context.get("history_relationship_id")
        or relationship.get("relationship_id")
        or "-"
    )


def format_manual_review_context(detail: dict[str, Any] | None) -> str:
    """Return a business-facing review summary with names before IDs."""

    if not detail:
        return "未找到候选关系或最终关系，请检查 ID 是否正确。"

    context = _history_context(detail)
    history = _history_relationship(context)
    relation_type = (
        detail.get("candidate_relation_type") or detail.get("relation_type") or "-"
    )
    history_relation_type = (
        context.get("relation_type") or history.get("relation_type") or "-"
    )
    history_status = (
        context.get("status")
        or context.get("relation_status")
        or history.get("relation_status")
        or "-"
    )
    conflict_reason = (
        context.get("conflict_reason")
        or context.get("reason")
        or detail.get("recommendation_reason")
        or "-"
    )
    confidence_score = detail.get("confidence_score")
    confidence_score_text = "-" if confidence_score in (None, "") else confidence_score
    order_count = detail.get("order_count") or 0
    total_teu = detail.get("total_teu")
    total_teu_text = "-" if total_teu in (None, "") else total_teu

    lines = [
        f"- 主体 A：{detail.get('from_name') or detail.get('source_label') or '-'}",
        f"- 主体 B：{detail.get('to_name') or detail.get('target_label') or '-'}",
        f"- 新候选关系：{relation_type}",
        f"- 候选状态：{detail.get('relation_status') or '-'}",
        f"- 置信度：{detail.get('confidence_level') or '-'} / {confidence_score_text}",
        f"- 订单证据：{order_count} orders / {total_teu_text} TEU",
        f"- 推荐理由：{detail.get('recommendation_reason') or '-'}",
    ]
    if context:
        lines.extend(
            [
                f"- 历史结论：{history_relation_type} / {history_status}",
                f"- 历史审核人：{history.get('verified_by') or '-'}",
                f"- 历史审核时间：{history.get('verified_at') or '-'}",
                f"- 历史备注：{history.get('decision_note') or '-'}",
                f"- 冲突原因：{conflict_reason}",
            ]
        )
    return "\n".join(lines)


def format_technical_identifier_summary(detail: dict[str, Any] | None) -> str:
    """Return secondary identifiers for debugging and traceability."""

    if not detail:
        return "无技术 ID。"

    context = _history_context(detail)
    identifiers = {
        "claim_id": detail.get("claim_id"),
        "relationship_id": detail.get("relationship_id") or detail.get("id"),
        "from_entity_id": detail.get("from_entity_id") or detail.get("source"),
        "to_entity_id": detail.get("to_entity_id") or detail.get("target"),
        "history_relationship_id": _history_relationship_id(context) if context else None,
    }
    return "\n".join(
        f"- {key}：{value}" for key, value in identifiers.items() if value
    )


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
    edge_label_markup: list[str] = []
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
        relation_label = html.escape(_short_edge_label(edge))
        if relation_label:
            label_width = min(max(len(relation_label) * 5.5 + 16, 54), 190)
            label_height = 18
            label_x = min(max(((x1 + x2) / 2) - (label_width / 2), 8), width - label_width - 8)
            label_y = min(max(((y1 + y2) / 2) - (label_height / 2), 8), height - label_height - 8)
            text_x = label_x + (label_width / 2)
            text_y = label_y + 12
            edge_label_markup.append(
                f"<g><rect class='edge-label-bg' x='{label_x:.1f}' y='{label_y:.1f}' "
                f"width='{label_width:.1f}' height='{label_height}' rx='7' "
                "fill='#ffffff' fill-opacity='0.9' stroke='#cbd5e1' "
                "stroke-width='0.8' />"
                f"<text class='edge-label-text' x='{text_x:.1f}' y='{text_y:.1f}' "
                "text-anchor='middle' font-size='9.5' font-weight='700' "
                f"fill='{style['color']}'>{relation_label}</text></g>"
            )

    node_by_id = {node["id"]: node for node in nodes}
    node_markup: list[str] = []
    for node_id in nx_graph.nodes:
        node = node_by_id[node_id]
        x, y = project(node_id)
        is_center = node_id == center_entity_id
        radius = 34 if is_center else 27
        fill = "#172554" if is_center else "#ffffff"
        stroke = "#0f172a" if is_center else "#2563eb"
        label = html.escape(_node_label(node))
        full_label = html.escape(str(node.get("label") or node_id))
        label_width = min(max(len(label) * 6.5 + 24, 88), 230)
        label_height = 24
        label_center_y = y + radius + 20
        if label_center_y + (label_height / 2) > height - 8:
            label_center_y = y - radius - 20
        label_x = min(max(x - (label_width / 2), 8), width - label_width - 8)
        label_y = label_center_y - (label_height / 2)
        text_x = label_x + (label_width / 2)
        text_y = label_center_y + 4
        center_badge = ""
        if is_center:
            center_badge = (
                f"<text x='{x:.1f}' y='{y + 4:.1f}' text-anchor='middle' "
                "font-size='12' font-weight='800' fill='#ffffff'>主体</text>"
            )
        node_markup.append(
            f"<g><circle class='node-circle' cx='{x:.1f}' cy='{y:.1f}' "
            f"r='{radius}' fill='{fill}' stroke='{stroke}' stroke-width='2.5'>"
            f"<title>{full_label}</title></circle>{center_badge}"
            f"<rect class='node-label-bg' x='{label_x:.1f}' y='{label_y:.1f}' "
            f"width='{label_width:.1f}' height='{label_height}' rx='9' "
            "fill='#ffffff' fill-opacity='0.96' stroke='#cbd5e1' "
            "stroke-width='1.1' />"
            f"<text class='node-label-text' x='{text_x:.1f}' y='{text_y:.1f}' "
            "text-anchor='middle' font-size='11' font-weight='800' "
            f"fill='#0f172a'>{label}</text></g>"
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
        <defs>
          <pattern id="soft-grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M 32 0 L 0 0 0 32" fill="none" stroke="#dbeafe" stroke-width="1"/>
          </pattern>
        </defs>
        <rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#f1f5f9" />
        <rect x="0" y="0" width="{width}" height="{height}" rx="18"
              fill="url(#soft-grid)" opacity="0.45" />
        {"".join(edge_markup)}
        {"".join(edge_label_markup)}
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
        for edge in graph.get("edges", []) or []
        if edge.get("edge_type") == "relationship_claim" and edge.get("id")
    ]


def graph_summary_counts(graph: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    """Return graph summary counts, falling back to payload lengths."""

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    summary = graph.get("summary") or {}
    candidate_edge_count = len(get_candidate_edges(graph))
    curated_edge_count = len(
        [edge for edge in edges if edge.get("edge_type") == "curated_relationship"]
    )
    return (
        summary.get("node_count", len(nodes)),
        summary.get("edge_count", len(edges)),
        summary.get("candidate_edge_count", candidate_edge_count),
        summary.get("curated_edge_count", curated_edge_count),
    )


def path_entity_label(path_item: dict[str, Any], edge: dict[str, Any], endpoint: str) -> str:
    """Return the displayed entity label in the actual path traversal direction."""

    endpoint_id = edge.get(endpoint)
    if not endpoint_id:
        source_fallbacks = ("source_label", "from_name", "source", "from_entity_id")
        target_fallbacks = ("target_label", "to_name", "target", "to_entity_id")
        fallback_keys = source_fallbacks if endpoint == "path_from" else target_fallbacks
        for key in fallback_keys:
            if edge.get(key):
                return str(edge[key])
        return "-"

    labels_by_id = {
        str(node.get("id")): node.get("label") or node.get("canonical_name") or node.get("id")
        for node in path_item.get("nodes") or []
        if node.get("id")
    }
    return str(labels_by_id.get(str(endpoint_id)) or endpoint_id)


def format_candidate_edge_label(edge: dict[str, Any]) -> str:
    """Return a selectbox label for a candidate edge."""

    source_label = _edge_endpoint_label(edge, "source_label", "source")
    target_label = _edge_endpoint_label(edge, "target_label", "target")
    return (
        f"{edge.get('id') or '-'} | {source_label} -> {target_label} | "
        f"{edge.get('relation_type') or '-'} | "
        f"{edge.get('confidence_level') or '-'} | {edge.get('order_count') or 0} orders"
    )


def format_queue_item_label(item: dict[str, Any]) -> str:
    """Return a compact label for one global review queue item."""

    return (
        f"{item.get('claim_id') or '-'} | {item.get('from_name') or '-'} -> "
        f"{item.get('to_name') or '-'} | {item.get('relation_status') or '-'} | "
        f"{item.get('confidence_level') or '-'} | {item.get('order_count') or 0} orders"
    )


def render_intro() -> None:
    """Render concise product guidance above the main workflow tabs."""

    with st.expander("基础逻辑与使用方法", expanded=True):
        st.caption("这部分用于帮助第一次使用时理解数据如何进入图谱、关系如何产生。")
        for section in INTRO_SECTIONS:
            st.markdown(f"**{section['title']}**")
            for item in section["items"]:
                st.markdown(f"- {item}")


def _render_import_batch_detail(run_id: str) -> None:
    """Render one import batch detail panel without letting backend errors crash UI."""

    try:
        detail = get_import_batch_detail(run_id)
    except Exception as exc:
        st.error(format_error_message(exc))
        return

    st.markdown("**批次质量状态**")
    st.info(format_import_quality_status(detail.get("quality_summary", {})))
    st.markdown("**归档文件**")
    show_table(detail.get("archived_files", []))
    st.markdown("**导入计数**")
    st.json(detail.get("counts", {}))

    try:
        error_result = list_import_errors(run_id, limit=500)
    except Exception as exc:
        st.error(format_error_message(exc))
        return

    error_items = error_result.get("items", [])
    st.markdown("**导入异常**")
    show_table(error_items)
    if not error_items:
        return

    if st.button("生成异常 CSV"):
        try:
            export_result = export_import_errors(run_id)
            export_path = Path(str(export_result["path"]))
            st.download_button(
                "下载异常 CSV",
                data=export_path.read_bytes(),
                file_name=import_error_export_filename(run_id),
                mime="text/csv",
            )
        except Exception as exc:
            st.error(format_error_message(exc))


def _render_import_quality_history() -> None:
    """Render recent import quality history and optional selected batch detail."""

    st.markdown("---")
    st.subheader("最近导入批次")
    try:
        batches = list_import_batches(limit=10)
    except Exception as exc:
        st.error(format_error_message(exc))
        batches = {"items": []}
    show_table(batches.get("items", []))

    selected_run_id = st.text_input("查看批次详情的 run_id")
    if selected_run_id:
        _render_import_batch_detail(selected_run_id)

def render_import_tab() -> None:
    """Render the import workflow."""

    st.subheader("导入 Excel/CSV")
    entities_path = st.text_input("企业清洗结果文件路径")
    orders_path = st.text_input("订单明细文件路径")
    relationships_path = st.text_input("已有关系候选文件路径")
    imported_by = st.text_input("导入人", value="local_user")
    confirm_duplicate_import = st.checkbox("确认重复导入")
    if st.button("开始导入"):
        source_files = [
            (source_role, Path(source_path))
            for source_role, source_path in (
                ("entities", entities_path),
                ("orders", orders_path),
                ("relationships", relationships_path),
            )
            if source_path
        ]
        duplicate_import = find_duplicate_import(source_files)
        if duplicate_import and not confirm_duplicate_import:
            st.warning(
                "检测到重复导入："
                f"run_id={duplicate_import.get('run_id')}, "
                f"imported_at={duplicate_import.get('imported_at')}, "
                f"imported_by={duplicate_import.get('imported_by')}。"
                "如需继续，请勾选确认重复导入。"
            )
            _render_import_quality_history()
            return
        try:
            result = run_import(
                ImportInputs(
                    entities_path=Path(entities_path) if entities_path else None,
                    orders_path=Path(orders_path) if orders_path else None,
                    relationships_path=Path(relationships_path) if relationships_path else None,
                    imported_by=imported_by,
                )
            )
            edge_result = generate_order_role_edges(run_id=result.run_id)
            edge_count = edge_result.get("edge_count", 0)
            history_reuse = {"history_matched": 0, "history_conflict": 0, "unchanged": 0}
            if edge_count > 0:
                claim_result = aggregate_relationship_claims(run_id=result.run_id)
                history_reuse = apply_history_reuse_to_claims(run_id=result.run_id)
            elif result.claim_count > 0:
                claim_result = {"claim_count": result.claim_count}
                history_reuse = apply_history_reuse_to_claims(run_id=result.run_id)
            else:
                claim_result = {"claim_count": 0}
        except Exception as exc:
            st.error(format_error_message(exc))
        else:
            st.success(f"导入完成，批次号：{result.run_id}")
            if result.archived_files:
                st.info(f"原始文件已归档到 data/raw/imports/{result.run_id}/")
                show_table(result.archived_files)
            st.json(
                {**result.__dict__, **edge_result, **claim_result, "history_reuse": history_reuse}
            )
            quality_summary = getattr(result, "quality_summary", None)
            if quality_summary:
                st.markdown("**导入质量摘要**")
                st.info(format_import_quality_status(quality_summary))
                error_count_by_type = quality_summary.get("error_count_by_type") or {}
                show_table(
                    [
                        {"error_type": error_type, "count": count}
                        for error_type, count in error_count_by_type.items()
                    ]
                )
            import_errors = getattr(result, "import_errors", None)
            if import_errors:
                with st.expander("查看本次导入异常"):
                    show_table(import_errors)
    _render_import_quality_history()


def render_search_tab() -> None:
    """Render entity search."""

    st.subheader("企业搜索")
    query = st.text_input("企业名称或别名")
    if query:
        matches = search_entities(query)
        show_table(matches)
        selected = st.text_input("查看详情的企业 ID")
        if selected:
            st.json(get_entity_detail(selected))


def render_graph_tab() -> None:
    """Render bounded graph visualization, path query, and candidate handoff."""

    st.subheader("一跳关系图谱")
    center_entity_id = st.text_input("中心企业 ID")
    include_rejected = st.checkbox("包含已否定的人工关系")
    depth = int(st.number_input("Graph depth", min_value=1, max_value=2, value=1, step=1))
    max_nodes = int(st.number_input("Max nodes", min_value=1, max_value=200, value=50, step=5))
    if not center_entity_id:
        st.info("请输入中心企业 ID 后查看一跳关系图谱。")
        return

    graph = get_ego_graph(
        center_entity_id,
        include_rejected=include_rejected,
        depth=depth,
        max_nodes=max_nodes,
    )
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_count, edge_count, candidate_edge_count, curated_edge_count = graph_summary_counts(
        graph
    )
    metric_cols = st.columns(4)
    metric_cols[0].metric("节点数", node_count)
    metric_cols[1].metric("边数", edge_count)
    metric_cols[2].metric("待审核候选", candidate_edge_count)
    metric_cols[3].metric("最终关系", curated_edge_count)

    components.html(render_graph_svg(graph), height=620, scrolling=True)

    node_labels_by_id = {
        str(node.get("id")): str(node.get("label") or node.get("id") or "-")
        for node in nodes
    }
    candidate_edges = [
        with_edge_display_names(edge, node_labels_by_id)
        for edge in get_candidate_edges(graph)
    ]
    if candidate_edges:
        st.markdown("**待审核候选关系**")
        candidate_ids = [edge["id"] for edge in candidate_edges]
        label_by_id = {
            edge["id"]: format_candidate_edge_label(edge) for edge in candidate_edges
        }
        selected_claim_id = st.selectbox(
            "选择要带到人工审核 tab 的候选关系",
            candidate_ids,
            format_func=lambda claim_id: label_by_id.get(claim_id, claim_id),
        )
        selected_edge = next(
            (edge for edge in candidate_edges if edge.get("id") == selected_claim_id),
            {},
        )
        st.info(format_relationship_detail_summary(selected_edge))
        st.json(selected_edge)
        if st.button("带到人工审核 tab", key="graph_to_review_button"):
            set_selected_claim_id(selected_claim_id)
            st.success(f"已选择候选关系 {selected_claim_id}，请切换到人工审核 tab 继续处理。")
    else:
        st.info("当前中心企业暂无待审核候选关系。")

    st.markdown("**\u4e24\u4f01\u4e1a\u8def\u5f84\u67e5\u8be2**")
    path_from_entity_id = st.text_input("from_entity_id")
    path_to_entity_id = st.text_input("to_entity_id")
    path_max_depth = int(
        st.number_input("Path max_depth", min_value=1, max_value=5, value=3, step=1)
    )
    path_max_paths = int(
        st.number_input("Path max_paths", min_value=1, max_value=20, value=5, step=1)
    )
    if st.button("\u67e5\u8be2\u8def\u5f84") and path_from_entity_id and path_to_entity_id:
        try:
            path_result = find_entity_paths(
                path_from_entity_id,
                path_to_entity_id,
                include_rejected=include_rejected,
                max_depth=path_max_depth,
                max_paths=path_max_paths,
            )
        except ValueError as exc:
            st.error(format_error_message(exc))
        else:
            path_rows: list[dict[str, Any]] = []
            for path_index, path_item in enumerate(path_result.get("paths") or [], start=1):
                for step_index, edge in enumerate(path_item.get("edges") or [], start=1):
                    path_rows.append(
                        {
                            "path": path_index,
                            "step": step_index,
                            "from_name": path_entity_label(path_item, edge, "path_from"),
                            "to_name": path_entity_label(path_item, edge, "path_to"),
                            "relation_type": edge.get("relation_type") or "-",
                            "record_type": edge.get("record_type") or edge.get("edge_type") or "-",
                            "status": edge.get("status") or edge.get("relation_status") or "-",
                            "evidence": edge.get("evidence")
                            or edge.get("recommendation_reason")
                            or edge.get("label")
                            or edge.get("order_id")
                            or "-",
                        }
                    )
            if path_rows:
                st.dataframe(path_rows)
            else:
                st.info("\u672a\u627e\u5230\u8def\u5f84 / No path found")

    with st.expander("节点与边数据"):
        show_table(nodes)
        show_table(edges)


def render_relationship_detail_tab() -> None:
    """Render relationship details and evidence."""

    st.subheader("关系详情")
    relationship_id = st.text_input("关系 ID 或候选关系 ID")
    if relationship_id:
        st.json(get_relationship_detail(relationship_id))
        show_table(get_relationship_evidence(relationship_id))


def render_review_queue_tab() -> None:
    """Render the global pending review queue."""

    st.subheader("全局待审核队列")
    st.caption("跨企业查看所有未定稿候选关系，适合每次导入后按优先级集中审核。")
    statuses = st.multiselect(
        "关系状态",
        REVIEW_QUEUE_STATUSES,
        default=list(REVIEW_QUEUE_STATUSES),
        format_func=lambda value: DISPLAY_VALUE_LABELS["relation_status"].get(value, value),
    )
    confidence_levels = st.multiselect(
        "置信等级（可选）",
        REVIEW_QUEUE_CONFIDENCE_LEVELS,
        default=[],
        format_func=lambda value: DISPLAY_VALUE_LABELS["confidence_level"].get(value, value),
    )
    run_id = st.text_input("批次号筛选（可选）")
    keyword = st.text_input("企业名称 / 候选关系 ID / 推荐理由关键词（可选）")
    limit = st.number_input("显示条数", min_value=1, max_value=500, value=100, step=10)
    if not statuses:
        st.warning("请至少选择一个关系状态。")
        return

    queue = list_review_queue(
        statuses=tuple(statuses),
        run_id=run_id or None,
        keyword=keyword or None,
        confidence_levels=tuple(confidence_levels) if confidence_levels else None,
        limit=int(limit),
    )
    summary = queue["summary"]
    status_counts = summary["status_counts"]
    metric_cols = st.columns(5)
    metric_cols[0].metric("待处理总数", summary["total_count"])
    metric_cols[1].metric("历史冲突", status_counts.get("history_conflict", 0))
    metric_cols[2].metric("匹配历史", status_counts.get("history_matched", 0))
    metric_cols[3].metric("普通候选", status_counts.get("candidate", 0))
    metric_cols[4].metric("待验证", status_counts.get("pending_verify", 0))

    items = queue["items"]
    if not items:
        st.info("当前筛选条件下没有待审核关系。")
        return

    show_table(items)
    claim_ids = [item["claim_id"] for item in items]
    label_by_id = {item["claim_id"]: format_queue_item_label(item) for item in items}
    selected_claim_id = st.selectbox(
        "选择要处理的候选关系",
        claim_ids,
        format_func=lambda claim_id: label_by_id.get(claim_id, claim_id),
    )
    selected_detail = get_relationship_detail(selected_claim_id)
    st.markdown(format_manual_review_context(selected_detail))
    with st.expander("查看订单证据"):
        show_table(get_relationship_evidence(selected_claim_id))
    if st.button("带到人工审核 tab", key="review_queue_to_review_button"):
        set_selected_claim_id(selected_claim_id)
        st.success(f"已选择候选关系 {selected_claim_id}，请切换到人工审核 tab 继续处理。")


def render_review_tab() -> None:
    """Render manual review actions."""

    st.subheader("\u4eba\u5de5\u5ba1\u6838")
    success_flash = consume_review_refresh_state()
    if success_flash:
        st.success(f"已完成审核：{success_flash.get('claim_id')}，待审核队列已刷新。")
        st.json(success_flash.get("result", {}))

    selected_claim_id = get_selected_claim_id()
    if selected_claim_id and REVIEW_CLAIM_WIDGET_KEY not in st.session_state:
        st.session_state[REVIEW_CLAIM_WIDGET_KEY] = selected_claim_id
    claim_id = st.text_input("\u5019\u9009\u5173\u7cfb ID", key=REVIEW_CLAIM_WIDGET_KEY)
    relationship_detail = None
    if claim_id:
        relationship_detail = get_relationship_detail(claim_id)
        st.markdown(format_manual_review_context(relationship_detail))
        with st.expander("\u67e5\u770b\u6280\u672f ID"):
            st.markdown(format_technical_identifier_summary(relationship_detail))
            st.json(relationship_detail)

    history_context = (
        relationship_detail.get("history_context") if relationship_detail else None
    )
    action_labels = {
        "confirm": "\u786e\u8ba4\u5173\u7cfb",
        "reject": "\u5426\u5b9a\u5173\u7cfb",
        "modify": "\u4fee\u6539\u5173\u7cfb\u7c7b\u578b",
        "keep_history": "\u6cbf\u7528\u5386\u53f2\u7ed3\u8bba",
        "supersede_history": (
            "\u63a5\u53d7\u65b0\u8bc1\u636e\uff0c"
            "\u66ff\u4ee3\u5386\u53f2\u7ed3\u8bba"
        ),
        "mark_pending_verify": "\u6682\u4e0d\u5224\u65ad\uff0c\u6807\u8bb0\u5f85\u9a8c\u8bc1",
    }
    action_options = (
        ["keep_history", "supersede_history", "mark_pending_verify"]
        if history_context
        else ["confirm", "reject", "modify"]
    )
    action_type = st.selectbox(
        "\u5ba1\u6838\u52a8\u4f5c",
        action_options,
        format_func=lambda action: action_labels.get(action, action),
    )
    candidate_relation_type = (
        relationship_detail.get("candidate_relation_type")
        if relationship_detail
        else None
    )
    default_relation_type = final_relation_type_for_candidate(candidate_relation_type)
    if action_type == "reject":
        default_relation_type = "rejected_relation"
    relation_type = None
    if action_type in {"confirm", "modify", "reject", "supersede_history"}:
        relation_type = st.selectbox(
            "\u5173\u7cfb\u7c7b\u578b",
            RELATION_TYPE_OPTIONS,
            index=_relation_type_index(default_relation_type),
            format_func=format_relation_type_option,
        )
    reason = st.text_area("\u5224\u65ad\u7406\u7531")
    operator = st.text_input("\u64cd\u4f5c\u4eba", value="local_user")
    if st.button("\u63d0\u4ea4\u5ba1\u6838") and claim_id:
        try:
            if action_type == "keep_history":
                result = keep_history_for_claim(
                    claim_id,
                    reason=reason,
                    operator=operator,
                )
            elif action_type == "mark_pending_verify":
                result = mark_claim_pending_verify(
                    claim_id,
                    reason=reason,
                    operator=operator,
                )
            elif action_type == "supersede_history":
                result = supersede_history_with_claim(
                    claim_id,
                    old_relationship_id=(
                        _history_relationship_id(history_context)
                        if isinstance(history_context, dict)
                        else None
                    ),
                    relation_type=relation_type or default_relation_type,
                    reason=reason,
                    operator=operator,
                )
            else:
                result = decide_relationship(
                    claim_id,
                    action_type=action_type,
                    relation_type=relation_type or default_relation_type,
                    reason=reason,
                    operator=operator,
                )
        except ValueError as exc:
            st.error(format_error_message(exc))
        else:
            store_review_success_for_refresh(claim_id, result)
            if not request_streamlit_rerun():
                st.success(f"已完成审核：{claim_id}，待审核队列将在下次刷新后更新。")
                st.json(result)

    st.divider()
    st.subheader("\u4eba\u5de5\u65b0\u589e\u5173\u7cfb")
    from_entity_id = st.text_input("\u8d77\u70b9\u4f01\u4e1a ID")
    to_entity_id = st.text_input("\u7ec8\u70b9\u4f01\u4e1a ID")
    if from_entity_id:
        from_entity_label = format_entity_reference(
            get_entity_detail(from_entity_id), fallback_id=from_entity_id
        )
        st.caption(f"\u8d77\u70b9\u4f01\u4e1a\uff1a{from_entity_label}")
    if to_entity_id:
        to_entity_label = format_entity_reference(
            get_entity_detail(to_entity_id), fallback_id=to_entity_id
        )
        st.caption(f"\u7ec8\u70b9\u4f01\u4e1a\uff1a{to_entity_label}")
    manual_relation_type = st.selectbox(
        "\u4eba\u5de5\u5173\u7cfb\u7c7b\u578b",
        RELATION_TYPE_OPTIONS,
        index=_relation_type_index(DEFAULT_RELATION_TYPE),
        format_func=format_relation_type_option,
    )
    manual_reason = st.text_area("\u4eba\u5de5\u65b0\u589e\u7406\u7531")
    if st.button("\u521b\u5efa\u4eba\u5de5\u5173\u7cfb") and from_entity_id and to_entity_id:
        try:
            result = create_manual_relationship(
                from_entity_id,
                to_entity_id,
                relation_type=manual_relation_type,
                reason=manual_reason,
                operator=operator,
            )
        except ValueError as exc:
            st.error(format_error_message(exc))
        else:
            st.json(result)


def render_export_tab() -> None:
    """Render export preview."""

    st.subheader("导出关系明细")
    center_entity_id = st.text_input("导出中心企业 ID")
    include_rejected = st.checkbox("导出时包含已否定关系")
    if center_entity_id:
        rows = export_relationship_rows(center_entity_id, include_rejected=include_rejected)
        show_table(rows)
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
        render_review_queue_tab()
    with tabs[5]:
        render_review_tab()
    with tabs[6]:
        render_export_tab()


if __name__ == "__main__":
    main()
