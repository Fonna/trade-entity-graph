from trade_entity_graph.ui import streamlit_app


def test_streamlit_app_exposes_mvp_tab_renderers() -> None:
    assert callable(streamlit_app.main)
    assert callable(streamlit_app.render_intro)
    assert callable(streamlit_app.render_import_tab)
    assert callable(streamlit_app.render_search_tab)
    assert callable(streamlit_app.render_graph_tab)
    assert callable(streamlit_app.render_relationship_detail_tab)
    assert callable(streamlit_app.render_review_tab)
    assert callable(streamlit_app.render_export_tab)
    assert callable(streamlit_app.render_graph_svg)
    assert callable(streamlit_app.get_candidate_edges)
    assert callable(streamlit_app.get_selected_claim_id)
    assert callable(streamlit_app.set_selected_claim_id)


def test_streamlit_app_uses_chinese_tab_labels() -> None:
    assert streamlit_app.TAB_LABELS == [
        "数据导入",
        "企业搜索",
        "关系图谱",
        "关系详情",
        "人工审核",
        "导出",
    ]


def test_streamlit_app_documents_basic_logic_and_usage() -> None:
    section_titles = [section["title"] for section in streamlit_app.INTRO_SECTIONS]

    assert section_titles == [
        "数据基础",
        "关系建立逻辑",
        "关系结果含义",
        "推荐操作流程",
        "文件字段要求",
    ]

    intro_text = "\n".join(
        "\n".join([section["title"], *section["items"]])
        for section in streamlit_app.INTRO_SECTIONS
    )
    assert "标准名" in intro_text
    assert "entity_id" in intro_text
    assert "订单角色边" in intro_text
    assert "人工审核" in intro_text
    assert "国家" in intro_text
    assert "主体类型" in intro_text
    assert "data/raw/imports" in intro_text


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
    assert "class='edge-label-bg'" in svg
    assert "class='edge-label-text'" in svg
    assert "trading_partner" in svg
    assert "subsidiary_candidate" in svg


def test_graph_svg_renderer_places_readable_backgrounds_behind_node_labels() -> None:
    graph = {
        "center_entity_id": "ENT_CENTER",
        "nodes": [
            {
                "id": "ENT_CENTER",
                "label": "CENTER COMPANY WITH LONG NAME",
                "entity_type": "customer",
                "tags": None,
            },
            {
                "id": "ENT_FACTORY",
                "label": "FACTORY COMPANY",
                "entity_type": "factory",
                "tags": None,
            },
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
            }
        ],
    }

    svg = streamlit_app.render_graph_svg(graph, width=640, height=360)

    assert "class='node-label-bg'" in svg
    assert "class='node-label-text'" in svg
    assert "CENTER COMPANY WITH..." in svg


def test_candidate_edges_returns_pending_relationship_claim_edges() -> None:
    graph = {
        "edges": [
            {"id": "CLM_1", "edge_type": "relationship_claim"},
            {"id": "REL_1", "edge_type": "curated_relationship"},
            {"id": "ORD_1", "edge_type": "order_role"},
            {"id": "CLM_2", "edge_type": "relationship_claim"},
        ]
    }

    assert streamlit_app.get_candidate_edges(graph) == [
        {"id": "CLM_1", "edge_type": "relationship_claim"},
        {"id": "CLM_2", "edge_type": "relationship_claim"},
    ]


def test_candidate_edges_skips_claim_edges_without_usable_id() -> None:
    graph = {
        "edges": [
            {"id": "CLM_1", "edge_type": "relationship_claim"},
            {"edge_type": "relationship_claim"},
            {"id": "", "edge_type": "relationship_claim"},
            {"id": None, "edge_type": "relationship_claim"},
        ]
    }

    assert streamlit_app.get_candidate_edges(graph) == [
        {"id": "CLM_1", "edge_type": "relationship_claim"},
    ]


def test_candidate_edge_label_uses_fallbacks_for_partial_edges() -> None:
    label = streamlit_app.format_candidate_edge_label(
        {"id": "CLM_1", "edge_type": "relationship_claim"}
    )

    assert label == "CLM_1 | - -> - | - | - | 0 orders"


def test_candidate_edge_label_includes_entity_names_for_review_context() -> None:
    label = streamlit_app.format_candidate_edge_label(
        {
            "id": "CLM_1",
            "edge_type": "relationship_claim",
            "source_label": "ACME TRADING",
            "target_label": "BETA FACTORY",
            "relation_type": "trading_partner_candidate",
            "confidence_level": "medium",
            "order_count": 2,
        }
    )

    assert (
        label
        == "CLM_1 | ACME TRADING -> BETA FACTORY | "
        "trading_partner_candidate | medium | 2 orders"
    )


def test_graph_summary_counts_falls_back_to_payload_lengths() -> None:
    graph = {
        "nodes": [{"id": "ENT_1"}, {"id": "ENT_2"}],
        "edges": [
            {"id": "CLM_1", "edge_type": "relationship_claim"},
            {"edge_type": "relationship_claim"},
            {"id": "REL_1", "edge_type": "curated_relationship"},
            {"id": "ORD_1", "edge_type": "order_role"},
        ],
    }

    assert streamlit_app.graph_summary_counts(graph) == (2, 4, 1, 1)


def test_graph_summary_counts_prefers_summary_values() -> None:
    graph = {
        "nodes": [{"id": "ENT_1"}],
        "edges": [{"id": "CLM_1", "edge_type": "relationship_claim"}],
        "summary": {
            "node_count": 10,
            "edge_count": 20,
            "candidate_edge_count": 30,
            "curated_edge_count": 40,
        },
    }

    assert streamlit_app.graph_summary_counts(graph) == (10, 20, 30, 40)


def test_selected_claim_state_helpers_round_trip() -> None:
    state: dict[str, str] = {}

    selected = streamlit_app.set_selected_claim_id("CLM_123", state=state)

    assert selected == "CLM_123"
    assert state["selected_claim_id"] == "CLM_123"
    assert state["review_claim_id"] == "CLM_123"
    assert streamlit_app.get_selected_claim_id(state=state) == "CLM_123"


def test_streamlit_app_exposes_graph_handoff_helpers() -> None:
    assert callable(streamlit_app.render_graph_svg)
    assert callable(streamlit_app.get_selected_claim_id)
    assert callable(streamlit_app.set_selected_claim_id)
    assert streamlit_app.SELECTED_CLAIM_STATE_KEY == "selected_claim_id"
    assert streamlit_app.REVIEW_CLAIM_WIDGET_KEY == "review_claim_id"


def test_review_relation_type_options_are_controlled_final_values() -> None:
    assert streamlit_app.RELATION_TYPE_OPTIONS == (
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


def test_review_tab_uses_relation_type_selectboxes(monkeypatch) -> None:
    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {}
            self.selectbox_calls: list[tuple[str, tuple[str, ...]]] = []

        def subheader(self, *_args, **_kwargs) -> None:
            return None

        def text_input(self, _label, value="", key=None, **_kwargs) -> str:
            if key is not None:
                self.session_state.setdefault(key, value)
                return self.session_state[key]
            return value

        def selectbox(self, label, options, index=0, **_kwargs) -> str:
            option_tuple = tuple(options)
            self.selectbox_calls.append((label, option_tuple))
            return option_tuple[index]

        def text_area(self, *_args, **_kwargs) -> str:
            return ""

        def button(self, *_args, **_kwargs) -> bool:
            return False

        def divider(self) -> None:
            return None

    fake_st = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    streamlit_app.render_review_tab()

    relation_type_calls = {
        label: options
        for label, options in fake_st.selectbox_calls
        if label in {"关系类型", "人工关系类型"}
    }
    assert relation_type_calls == {
        "关系类型": streamlit_app.RELATION_TYPE_OPTIONS,
        "人工关系类型": streamlit_app.RELATION_TYPE_OPTIONS,
    }


def test_review_detail_summary_includes_entity_names() -> None:
    summary = streamlit_app.format_relationship_detail_summary(
        {
            "claim_id": "CLM_1",
            "record_type": "relationship_claim",
            "from_entity_id": "ENT_A",
            "from_name": "ACME TRADING",
            "to_entity_id": "ENT_B",
            "to_name": "BETA FACTORY",
            "candidate_relation_type": "trading_partner_candidate",
            "confidence_level": "medium",
            "order_count": 2,
        }
    )

    assert "CLM_1" in summary
    assert "ACME TRADING (ENT_A) -> BETA FACTORY (ENT_B)" in summary
    assert "trading_partner_candidate" in summary
    assert "medium" in summary
    assert "2 orders" in summary


def test_manual_review_context_is_name_first_without_primary_entity_ids() -> None:
    summary = streamlit_app.format_manual_review_context(
        {
            "claim_id": "CLM_1",
            "from_entity_id": "ENT_A",
            "from_name": "ACME TRADING",
            "to_entity_id": "ENT_B",
            "to_name": "BETA FACTORY",
            "candidate_relation_type": "trading_partner_candidate",
            "relation_status": "history_conflict",
            "confidence_level": "medium",
            "confidence_score": 0.73,
            "order_count": 4,
            "total_teu": 12.5,
            "recommendation_reason": "历史拒绝但新订单证据增加",
            "history_context": {
                "history_relationship_id": "REL_OLD",
                "relation_type": "rejected_relation",
                "status": "rejected",
                "conflict_reason": "新证据与历史否定结论冲突",
                "history_relationship": {
                    "relationship_id": "REL_OLD",
                    "relation_type": "rejected_relation",
                    "relation_status": "rejected",
                    "verified_by": "alice",
                    "verified_at": "2026-05-20T09:30:00",
                    "decision_note": "旧证据不足",
                },
            },
        }
    )

    assert "主体 A：ACME TRADING" in summary
    assert "主体 B：BETA FACTORY" in summary
    assert "新候选关系：trading_partner_candidate" in summary
    assert "候选状态：history_conflict" in summary
    assert "置信度：medium / 0.73" in summary
    assert "订单证据：4 orders / 12.5 TEU" in summary
    assert "推荐理由：历史拒绝但新订单证据增加" in summary
    assert "历史结论：rejected_relation / rejected" in summary
    assert "历史审核人：alice" in summary
    assert "历史审核时间：2026-05-20T09:30:00" in summary
    assert "历史备注：旧证据不足" in summary
    assert "冲突原因：" in summary
    assert "ENT_A" not in summary
    assert "ENT_B" not in summary


def test_technical_identifier_summary_keeps_ids_secondary() -> None:
    summary = streamlit_app.format_technical_identifier_summary(
        {
            "claim_id": "CLM_1",
            "from_entity_id": "ENT_A",
            "to_entity_id": "ENT_B",
            "history_context": {
                "history_relationship_id": "REL_OLD",
            },
        }
    )

    assert "CLM_1" in summary
    assert "ENT_A" in summary
    assert "ENT_B" in summary
    assert "REL_OLD" in summary


def test_entity_reference_summary_includes_name_when_available() -> None:
    assert (
        streamlit_app.format_entity_reference(
            {"entity_id": "ENT_A", "canonical_name": "ACME TRADING"}
        )
        == "ACME TRADING (ENT_A)"
    )
    assert streamlit_app.format_entity_reference(None, fallback_id="ENT_MISSING") == (
        "未找到企业：ENT_MISSING"
    )
