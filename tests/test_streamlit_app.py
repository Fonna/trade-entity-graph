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
