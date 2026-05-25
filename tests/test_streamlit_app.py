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
