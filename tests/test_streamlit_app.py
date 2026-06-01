from pathlib import Path
from types import SimpleNamespace

import pytest

from trade_entity_graph.ui import streamlit_app


def test_streamlit_app_exposes_mvp_tab_renderers() -> None:
    assert callable(streamlit_app.main)
    assert callable(streamlit_app.render_intro)
    assert callable(streamlit_app.render_import_tab)
    assert callable(streamlit_app.render_search_tab)
    assert callable(streamlit_app.render_graph_tab)
    assert callable(streamlit_app.render_relationship_detail_tab)
    assert callable(streamlit_app.render_review_queue_tab)
    assert callable(streamlit_app.render_review_tab)
    assert callable(streamlit_app.render_export_tab)
    assert callable(streamlit_app.render_graph_svg)
    assert callable(streamlit_app.get_candidate_edges)
    assert callable(streamlit_app.get_selected_claim_id)
    assert callable(streamlit_app.set_selected_claim_id)
    assert callable(streamlit_app.localize_table_records)
    assert callable(streamlit_app.format_error_message)


def test_streamlit_app_uses_chinese_tab_labels() -> None:
    assert streamlit_app.TAB_LABELS == [
        "数据导入",
        "企业搜索",
        "关系图谱",
        "关系详情",
        "待审核队列",
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


def test_review_queue_item_label_includes_priority_context() -> None:
    label = streamlit_app.format_queue_item_label(
        {
            "claim_id": "CLM_QUEUE",
            "from_name": "ACME TRADING",
            "to_name": "BETA FACTORY",
            "relation_status": "history_conflict",
            "confidence_level": "high",
            "order_count": 8,
        }
    )

    assert label == "CLM_QUEUE | ACME TRADING -> BETA FACTORY | history_conflict | high | 8 orders"


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


def test_graph_relation_type_summary_deduplicates_by_record_and_relation_type() -> None:
    graph = {
        "edges": [
            {
                "record_type": "order_role_edge",
                "relation_type": "customer_to_shipper",
                "source_label": "ACME",
                "target_label": "BETA",
            },
            {
                "record_type": "order_role_edge",
                "relation_type": "customer_to_shipper",
                "source_label": "ACME",
                "target_label": "BETA",
            },
            {
                "record_type": "order_role_edge",
                "relation_type": "customer_to_consignee",
                "source_label": "ACME",
                "target_label": "OMEGA",
            },
            {
                "record_type": "relationship_claim",
                "relation_type": "trading_partner_candidate",
                "source_label": "ACME",
                "target_label": "BETA",
            },
            {
                "record_type": "relationship_claim",
                "relation_type": "trading_partner_candidate",
                "source_label": "ACME",
                "target_label": "OMEGA",
            },
        ]
    }

    count, rows = streamlit_app.graph_relation_type_summary(graph)

    assert count == 3
    assert rows == [
        {
            "record_type": "order_role_edge",
            "relation_type": "customer_to_consignee",
            "edge_count": 1,
            "entity_pair_count": 1,
            "entity_pairs": "ACME -> OMEGA",
        },
        {
            "record_type": "order_role_edge",
            "relation_type": "customer_to_shipper",
            "edge_count": 2,
            "entity_pair_count": 1,
            "entity_pairs": "ACME -> BETA",
        },
        {
            "record_type": "relationship_claim",
            "relation_type": "trading_partner_candidate",
            "edge_count": 2,
            "entity_pair_count": 2,
            "entity_pairs": "ACME -> BETA; ACME -> OMEGA",
        },
    ]


class GraphFakeColumn:
    def __init__(self, owner=None) -> None:
        self.owner = owner

    def metric(self, label, value, *_args, **_kwargs) -> None:
        if self.owner is not None:
            self.owner.metrics.append((label, value))
        return None


class GraphFakeExpander:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class GraphFakeStreamlit:
    def __init__(
        self,
        *,
        center_entity_id: str = "",
        depth: int = 1,
        max_nodes: int = 50,
        path_from: str = "",
        path_to: str = "",
        max_depth: int = 3,
        max_paths: int = 5,
        query_paths: bool = False,
    ) -> None:
        self.text_inputs = [center_entity_id, path_from, path_to]
        self.number_inputs = [depth, max_nodes, max_depth, max_paths]
        self.query_paths = query_paths
        self.frames: list[object] = []
        self.infos: list[str] = []
        self.errors: list[str] = []
        self.button_calls: list[tuple[str, dict]] = []
        self.metrics: list[tuple[str, object]] = []
        self.text_input_calls = 0
        self.number_input_calls = 0

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def text_input(self, *_args, **_kwargs) -> str:
        response = self.text_inputs[self.text_input_calls]
        self.text_input_calls += 1
        return response

    def checkbox(self, *_args, **_kwargs) -> bool:
        return False

    def number_input(self, *_args, **_kwargs) -> int:
        response = self.number_inputs[self.number_input_calls]
        self.number_input_calls += 1
        return response

    def columns(self, count: int):
        return [GraphFakeColumn(self) for _ in range(count)]

    def markdown(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, rows, **_kwargs) -> None:
        self.frames.append(rows)

    def info(self, message, **_kwargs) -> None:
        self.infos.append(str(message))

    def error(self, message, **_kwargs) -> None:
        self.errors.append(str(message))

    def json(self, *_args, **_kwargs) -> None:
        return None

    def selectbox(self, _label, options, **_kwargs):
        return list(options)[0]

    def button(self, label, **kwargs) -> bool:
        self.button_calls.append((str(label), kwargs))
        return self.query_paths and "\u8def\u5f84" in str(label)

    def success(self, *_args, **_kwargs) -> None:
        return None

    def expander(self, *_args, **_kwargs) -> GraphFakeExpander:
        return GraphFakeExpander()


def test_graph_tab_requests_depth_two_graph(monkeypatch) -> None:
    calls = []
    fake_st = GraphFakeStreamlit(center_entity_id="ENT_A", depth=2, max_nodes=25)
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app.components, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app,
        "get_ego_graph",
        lambda entity_id, **kwargs: calls.append((entity_id, kwargs))
        or {"nodes": [], "edges": [], "summary": {"node_count": 0, "edge_count": 0}},
    )

    streamlit_app.render_graph_tab()

    assert calls == [("ENT_A", {"include_rejected": False, "depth": 2, "max_nodes": 25})]


def test_graph_tab_renders_relation_type_metric_and_detail(monkeypatch) -> None:
    fake_st = GraphFakeStreamlit(center_entity_id="ENT_A")
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app.components, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app,
        "get_ego_graph",
        lambda *_args, **_kwargs: {
            "nodes": [{"id": "ENT_A", "label": "ACME"}],
            "edges": [
                {
                    "record_type": "order_role_edge",
                    "edge_type": "order_role_edge",
                    "relation_type": "customer_to_shipper",
                    "source_label": "ACME",
                    "target_label": "BETA",
                },
                {
                    "record_type": "order_role_edge",
                    "edge_type": "order_role_edge",
                    "relation_type": "customer_to_shipper",
                    "source_label": "ACME",
                    "target_label": "BETA",
                },
                {
                    "record_type": "order_role_edge",
                    "edge_type": "order_role_edge",
                    "relation_type": "customer_to_consignee",
                    "source_label": "ACME",
                    "target_label": "OMEGA",
                },
            ],
            "summary": {"node_count": 1, "edge_count": 3},
        },
    )

    streamlit_app.render_graph_tab()

    assert ("关系类型数", 2) in fake_st.metrics
    relation_summary = fake_st.frames[0]
    assert [row["关系类型"] for row in relation_summary] == [
        "客户到收货人",
        "客户到发货人",
    ]
    assert [row["边记录数"] for row in relation_summary] == [1, 2]


def test_graph_tab_handoff_button_has_unique_key(monkeypatch) -> None:
    fake_st = GraphFakeStreamlit(center_entity_id="ENT_A")
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app.components, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app,
        "get_ego_graph",
        lambda *_args, **_kwargs: {
            "nodes": [{"id": "ENT_A", "label": "Alpha"}],
            "edges": [
                {
                    "id": "CLM_GRAPH",
                    "edge_type": "relationship_claim",
                    "record_type": "relationship_claim",
                    "source": "ENT_A",
                    "target": "ENT_B",
                    "relation_type": "trading_partner_candidate",
                    "confidence_level": "high",
                    "order_count": 1,
                }
            ],
            "summary": {},
        },
    )

    streamlit_app.render_graph_tab()

    assert any(
        kwargs.get("key") == "graph_to_review_button"
        for _label, kwargs in fake_st.button_calls
    )


def test_graph_tab_renders_entity_path_results(monkeypatch) -> None:
    calls = []
    fake_st = GraphFakeStreamlit(
        center_entity_id="ENT_A",
        path_from="ENT_A",
        path_to="ENT_C",
        query_paths=True,
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app.components, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app,
        "get_ego_graph",
        lambda *_args, **_kwargs: {"nodes": [], "edges": [], "summary": {}},
    )

    def fake_find_entity_paths(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "path_count": 1,
            "paths": [
                {
                    "edges": [
                        {
                            "source_label": "A",
                            "target_label": "B",
                            "relation_type": "customer_to_shipper",
                            "record_type": "order_role_edge",
                            "status": "evidence",
                            "evidence": "order ORD_1",
                        }
                    ]
                }
            ],
        }

    monkeypatch.setattr(streamlit_app, "find_entity_paths", fake_find_entity_paths)

    streamlit_app.render_graph_tab()

    assert calls == [
        (
            ("ENT_A", "ENT_C"),
            {"include_rejected": False, "max_depth": 3, "max_paths": 5},
        )
    ]
    assert fake_st.frames
    assert fake_st.frames[0][0]["step"] == 1
    assert fake_st.frames[0][0]["from_name"] == "A"
    assert fake_st.frames[0][0]["to_name"] == "B"
    assert fake_st.frames[0][0]["relation_type"] == "customer_to_shipper"
    assert fake_st.frames[0][0]["record_type"] == "order_role_edge"
    assert fake_st.frames[0][0]["status"] == "evidence"
    assert fake_st.frames[0][0]["evidence"] == "order ORD_1"


def test_graph_tab_renders_path_step_direction_from_path_metadata(monkeypatch) -> None:
    fake_st = GraphFakeStreamlit(
        center_entity_id="ENT_A",
        path_from="ENT_A",
        path_to="ENT_C",
        query_paths=True,
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app.components, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app,
        "get_ego_graph",
        lambda *_args, **_kwargs: {"nodes": [], "edges": [], "summary": {}},
    )
    monkeypatch.setattr(
        streamlit_app,
        "find_entity_paths",
        lambda *_args, **_kwargs: {
            "path_count": 1,
            "paths": [
                {
                    "nodes": [
                        {"id": "ENT_A", "label": "Alpha Trading"},
                        {"id": "ENT_B", "label": "Beta Factory"},
                    ],
                    "edges": [
                        {
                            "source": "ENT_B",
                            "target": "ENT_A",
                            "source_label": "Beta Factory",
                            "target_label": "Alpha Trading",
                            "path_from": "ENT_A",
                            "path_to": "ENT_B",
                            "relation_type": "customer_to_shipper",
                            "record_type": "order_role_edge",
                            "status": "evidence",
                        }
                    ],
                }
            ],
        },
    )

    streamlit_app.render_graph_tab()

    assert fake_st.frames[0][0]["from_name"] == "Alpha Trading"
    assert fake_st.frames[0][0]["to_name"] == "Beta Factory"


def test_graph_tab_renders_no_path_info(monkeypatch) -> None:
    fake_st = GraphFakeStreamlit(
        center_entity_id="ENT_A",
        path_from="ENT_A",
        path_to="ENT_Z",
        query_paths=True,
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app.components, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app,
        "get_ego_graph",
        lambda *_args, **_kwargs: {"nodes": [], "edges": [], "summary": {}},
    )
    monkeypatch.setattr(
        streamlit_app,
        "find_entity_paths",
        lambda *_args, **_kwargs: {"path_count": 0, "paths": []},
    )

    streamlit_app.render_graph_tab()

    assert any("No path" in message or "\u672a\u627e\u5230" in message for message in fake_st.infos)


def test_graph_tab_renders_path_query_error(monkeypatch) -> None:
    fake_st = GraphFakeStreamlit(
        center_entity_id="ENT_A",
        path_from="ENT_A",
        path_to="NO_SUCH",
        query_paths=True,
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app.components, "html", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        streamlit_app,
        "get_ego_graph",
        lambda *_args, **_kwargs: {"nodes": [], "edges": [], "summary": {}},
    )

    def raise_unknown_entity(*_args, **_kwargs):
        raise ValueError("Unknown entity: NO_SUCH")

    monkeypatch.setattr(streamlit_app, "find_entity_paths", raise_unknown_entity)

    streamlit_app.render_graph_tab()

    assert fake_st.errors
    assert "Unknown entity: NO_SUCH" in fake_st.errors[0]


def test_selected_claim_state_helpers_round_trip() -> None:
    state: dict[str, str] = {}

    selected = streamlit_app.set_selected_claim_id("CLM_123", state=state)

    assert selected == "CLM_123"
    assert state["selected_claim_id"] == "CLM_123"
    assert state["review_claim_id"] == "CLM_123"
    assert streamlit_app.get_selected_claim_id(state=state) == "CLM_123"


def test_review_success_refresh_state_clears_reviewed_claim() -> None:
    state = {
        streamlit_app.SELECTED_CLAIM_STATE_KEY: "CLM_123",
        streamlit_app.REVIEW_CLAIM_WIDGET_KEY: "CLM_123",
    }

    streamlit_app.store_review_success_for_refresh(
        "CLM_123",
        {"relationship_id": "REL_123"},
        state=state,
    )
    flash = streamlit_app.consume_review_refresh_state(state=state)

    assert flash == {
        "claim_id": "CLM_123",
        "result": {"relationship_id": "REL_123"},
    }
    assert streamlit_app.SELECTED_CLAIM_STATE_KEY not in state
    assert streamlit_app.REVIEW_CLAIM_WIDGET_KEY not in state
    assert streamlit_app.REVIEW_CLEAR_CLAIM_STATE_KEY not in state
    assert streamlit_app.REVIEW_SUCCESS_FLASH_STATE_KEY not in state


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


def test_localize_table_records_renames_headers_and_common_values() -> None:
    rows = streamlit_app.localize_table_records(
        [
            {
                "entity_id": "ENT_1",
                "canonical_name": "APEX GLOBAL HOLDINGS",
                "country": "US",
                "entity_type": "group",
                "tags": None,
                "status": "active",
            },
            {
                "id": "CLM_1",
                "relation_type": "trading_partner_candidate",
                "status": "candidate",
                "confidence_level": "medium",
            },
        ]
    )

    assert rows == [
        {
            "企业ID": "ENT_1",
            "标准企业名称": "APEX GLOBAL HOLDINGS",
            "国家/地区": "US",
            "主体类型": "集团",
            "标签": "-",
            "状态": "有效",
        },
        {
            "记录ID": "CLM_1",
            "关系类型": "普通贸易伙伴（候选）",
            "状态": "候选",
            "置信等级": "中",
        },
    ]


def test_search_tab_displays_chinese_table_headers(monkeypatch) -> None:
    class FakeStreamlit:
        def __init__(self) -> None:
            self.frames: list[list[dict]] = []

        def subheader(self, *_args, **_kwargs) -> None:
            return None

        def text_input(self, label, **_kwargs) -> str:
            return "ape" if label == "企业名称或别名" else ""

        def dataframe(self, rows, **_kwargs) -> None:
            self.frames.append(rows)

    fake_st = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "search_entities",
        lambda _query: [
            {
                "entity_id": "ENT_1",
                "canonical_name": "APEX GLOBAL HOLDINGS",
                "country": "US",
                "entity_type": "subsidiary",
                "tags": None,
                "status": "active",
            }
        ],
    )

    streamlit_app.render_search_tab()

    assert fake_st.frames == [
        [
            {
                "企业ID": "ENT_1",
                "标准企业名称": "APEX GLOBAL HOLDINGS",
                "国家/地区": "US",
                "主体类型": "子公司/分支机构",
                "标签": "-",
                "状态": "有效",
            }
        ]
    ]


def test_format_error_message_translates_known_backend_errors() -> None:
    assert streamlit_app.format_error_message(
        ValueError("Claim already finalized by history review: CLM_1")
    ) == "该候选关系已被历史审核定稿：CLM_1"



def test_final_relation_type_for_candidate_maps_known_candidate_types() -> None:
    assert (
        streamlit_app.final_relation_type_for_candidate("trading_partner_candidate")
        == "trading_partner"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("factory_candidate")
        == "factory_node"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("sales_center_candidate")
        == "sales_center"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("same_group_candidate")
        == "same_group"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("subsidiary_candidate")
        == "subsidiary"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("logistics_service_candidate")
        == "logistics_service"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("same_entity_candidate")
        == "same_entity"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("co_order_role_candidate")
        == "co_order_role"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("unknown_candidate")
        == "unknown"
    )
    assert (
        streamlit_app.final_relation_type_for_candidate("unexpected_candidate")
        == streamlit_app.DEFAULT_RELATION_TYPE
    )


def test_import_tab_applies_history_reuse_after_generated_claims(monkeypatch) -> None:
    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class FakeStreamlit:
        def __init__(self) -> None:
            self.json_payloads: list[dict] = []

        def subheader(self, *_args, **_kwargs) -> None:
            return None

        def text_input(self, _label, value="", **_kwargs) -> str:
            return value

        def button(self, *_args, **_kwargs) -> bool:
            return True

        def checkbox(self, *_args, **_kwargs) -> bool:
            return False

        def success(self, *_args, **_kwargs) -> None:
            return None

        def info(self, *_args, **_kwargs) -> None:
            return None

        def markdown(self, *_args, **_kwargs) -> None:
            return None

        def expander(self, *_args, **_kwargs) -> FakeExpander:
            return FakeExpander()

        def download_button(self, *_args, **_kwargs) -> None:
            return None

        def dataframe(self, *_args, **_kwargs) -> None:
            return None

        def json(self, payload, **_kwargs) -> None:
            self.json_payloads.append(payload)

    calls: list[tuple[str, str]] = []
    fake_st = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "run_import",
        lambda _inputs: SimpleNamespace(
            run_id="RUN_STREAMLIT_IMPORT",
            entity_count=2,
            alias_count=0,
            evidence_count=1,
            claim_count=0,
            skipped_rows=[],
            archived_files=[],
            import_errors=[],
            warning_count=0,
            error_count=0,
            quality_summary={
                "blocking_error_count": 0,
                "warning_count": 0,
                "error_count_by_type": {},
            },
        ),
    )

    def fake_generate_order_role_edges(*, run_id):
        calls.append(("generate", run_id))
        return {"edge_count": 1, "skipped_count": 0}

    def fake_aggregate_relationship_claims(*, run_id):
        calls.append(("aggregate", run_id))
        return {"claim_count": 1}

    def fake_apply_history_reuse_to_claims(*, run_id):
        calls.append(("history", run_id))
        return {"history_matched": 0, "history_conflict": 1, "unchanged": 0}

    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        fake_generate_order_role_edges,
    )
    monkeypatch.setattr(
        streamlit_app,
        "aggregate_relationship_claims",
        fake_aggregate_relationship_claims,
    )
    monkeypatch.setattr(
        streamlit_app,
        "apply_history_reuse_to_claims",
        fake_apply_history_reuse_to_claims,
        raising=False,
    )
    monkeypatch.setattr(
        streamlit_app,
        "list_import_batches",
        lambda **_kwargs: {"items": []},
    )

    streamlit_app.render_import_tab()

    assert calls == [
        ("generate", "RUN_STREAMLIT_IMPORT"),
        ("aggregate", "RUN_STREAMLIT_IMPORT"),
        ("history", "RUN_STREAMLIT_IMPORT"),
    ]
    assert fake_st.json_payloads[0]["history_reuse"] == {
        "history_matched": 0,
        "history_conflict": 1,
        "unchanged": 0,
    }


class ImportQualityFakeStreamlit:
    def __init__(
        self,
        *,
        selected_run_id: str = "",
        buttons: dict[str, bool] | None = None,
        checkboxes: dict[str, bool] | None = None,
        text_inputs: list[str] | dict[str, str] | None = None,
    ) -> None:
        self.selected_run_id = selected_run_id
        self.buttons = buttons or {}
        self.checkboxes = checkboxes or {}
        self.text_inputs = text_inputs
        self.text_input_calls = 0
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.successes: list[str] = []
        self.warnings: list[str] = []
        self.frames: list[object] = []
        self.downloads: list[dict[str, object]] = []
        self.json_payloads: list[object] = []

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def text_input(self, label, value="", **_kwargs) -> str:
        if isinstance(self.text_inputs, dict):
            return self.text_inputs.get(str(label), value)
        if self.text_inputs is not None:
            response = self.text_inputs[self.text_input_calls]
            self.text_input_calls += 1
            return response
        if "run_id" in str(label):
            return self.selected_run_id
        return value

    def button(self, label, **_kwargs) -> bool:
        return self.buttons.get(str(label), False)

    def checkbox(self, label, **_kwargs) -> bool:
        label_text = str(label)
        return any(
            checked for expected, checked in self.checkboxes.items() if expected in label_text
        )

    def success(self, message, **_kwargs) -> None:
        self.successes.append(str(message))

    def info(self, message, **_kwargs) -> None:
        self.infos.append(str(message))

    def warning(self, message, **_kwargs) -> None:
        self.warnings.append(str(message))

    def error(self, message, **_kwargs) -> None:
        self.errors.append(str(message))

    def markdown(self, *_args, **_kwargs) -> None:
        return None

    def dataframe(self, records, **_kwargs) -> None:
        self.frames.append(records)

    def json(self, payload, **_kwargs) -> None:
        self.json_payloads.append(payload)

    def download_button(self, label, **kwargs) -> None:
        self.downloads.append({"label": label, **kwargs})


def test_import_tab_warns_and_skips_duplicate_import_without_confirmation(
    monkeypatch,
) -> None:
    calls: list[object] = []
    fake_st = ImportQualityFakeStreamlit(
        buttons={"\u5f00\u59cb\u5bfc\u5165": True},
        checkboxes={"\u786e\u8ba4\u91cd\u590d\u5bfc\u5165": False},
        text_inputs=[
            "data/entities.csv",
            "data/orders.csv",
            "",
            "",
            "local_user",
            "",
        ],
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    def fake_find_duplicate_import(sources):
        calls.append(("duplicate", sources))
        return {
            "run_id": "RUN_DUP",
            "imported_at": "2026-05-31T09:00:00Z",
            "imported_by": "tester",
            "source_files": [],
        }

    def fail_if_called(*_args, **_kwargs):
        calls.append("unexpected")
        raise AssertionError("duplicate imports should require explicit confirmation")

    monkeypatch.setattr(
        streamlit_app,
        "find_duplicate_import",
        fake_find_duplicate_import,
        raising=False,
    )
    monkeypatch.setattr(streamlit_app, "run_import", fail_if_called)
    monkeypatch.setattr(streamlit_app, "generate_order_role_edges", fail_if_called)
    monkeypatch.setattr(streamlit_app, "aggregate_relationship_claims", fail_if_called)
    monkeypatch.setattr(streamlit_app, "apply_history_reuse_to_claims", fail_if_called)
    monkeypatch.setattr(
        streamlit_app,
        "list_import_batches",
        lambda **_kwargs: calls.append("history") or {"items": [{"run_id": "RUN_DUP"}]},
    )

    streamlit_app.render_import_tab()

    assert calls == [
        (
            "duplicate",
            [("entities", Path("data/entities.csv")), ("orders", Path("data/orders.csv"))],
        ),
        "history",
    ]
    assert len(fake_st.warnings) == 1
    assert "RUN_DUP" in fake_st.warnings[0]
    assert "2026-05-31T09:00:00Z" in fake_st.warnings[0]
    assert "tester" in fake_st.warnings[0]
    assert len(fake_st.frames) == 1


def test_import_tab_allows_duplicate_import_with_confirmation(monkeypatch) -> None:
    calls: list[str] = []
    fake_st = ImportQualityFakeStreamlit(
        buttons={"\u5f00\u59cb\u5bfc\u5165": True},
        checkboxes={"\u786e\u8ba4\u91cd\u590d\u5bfc\u5165": True},
        text_inputs=[
            "data/entities.csv",
            "data/orders.csv",
            "data/relationships.csv",
            "",
            "local_user",
            "",
        ],
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "find_duplicate_import",
        lambda _sources: {
            "run_id": "RUN_DUP",
            "imported_at": "2026-05-31T09:00:00Z",
            "imported_by": "tester",
        },
        raising=False,
    )
    monkeypatch.setattr(streamlit_app, "run_import", lambda _inputs: _successful_import_result())
    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        lambda *, run_id: calls.append(f"generate:{run_id}") or {"edge_count": 1},
    )
    monkeypatch.setattr(
        streamlit_app,
        "aggregate_relationship_claims",
        lambda *, run_id: calls.append(f"aggregate:{run_id}") or {"claim_count": 1},
    )
    monkeypatch.setattr(
        streamlit_app,
        "apply_history_reuse_to_claims",
        lambda *, run_id: calls.append(f"history_reuse:{run_id}")
        or {"history_matched": 0, "history_conflict": 0, "unchanged": 1},
    )
    monkeypatch.setattr(
        streamlit_app,
        "list_import_batches",
        lambda **_kwargs: calls.append("history") or {"items": []},
    )

    streamlit_app.render_import_tab()

    assert calls == [
        "generate:RUN_STREAMLIT_IMPORT",
        "aggregate:RUN_STREAMLIT_IMPORT",
        "history_reuse:RUN_STREAMLIT_IMPORT",
        "history",
    ]
    assert len(fake_st.successes) == 1
    assert fake_st.json_payloads[0]["run_id"] == "RUN_STREAMLIT_IMPORT"


def test_import_tab_passes_confirmed_relationships_path(monkeypatch) -> None:
    calls: list[object] = []
    captured_inputs = []
    fake_st = ImportQualityFakeStreamlit(
        buttons={"\u5f00\u59cb\u5bfc\u5165": True},
        text_inputs=[
            "",
            "",
            "",
            "data/confirmed_relationships.csv",
            "curator",
            "",
        ],
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    def fake_find_duplicate_import(sources):
        calls.append(("duplicate", sources))
        return None

    def fake_run_import(inputs):
        captured_inputs.append(inputs)
        return _successful_import_result(curated_relationship_count=2)

    def fail_if_aggregated(*_args, **_kwargs):
        calls.append("aggregate")
        raise AssertionError("confirmed-only import should not aggregate claims")

    monkeypatch.setattr(streamlit_app, "find_duplicate_import", fake_find_duplicate_import)
    monkeypatch.setattr(streamlit_app, "run_import", fake_run_import)
    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        lambda *, run_id: calls.append(f"generate:{run_id}") or {"edge_count": 0},
    )
    monkeypatch.setattr(streamlit_app, "aggregate_relationship_claims", fail_if_aggregated)
    monkeypatch.setattr(
        streamlit_app,
        "apply_history_reuse_to_claims",
        lambda *_args, **_kwargs: calls.append("history_reuse"),
    )
    monkeypatch.setattr(
        streamlit_app,
        "list_import_batches",
        lambda **_kwargs: calls.append("history") or {"items": []},
    )

    streamlit_app.render_import_tab()

    assert captured_inputs[0].confirmed_relationships_path == Path(
        "data/confirmed_relationships.csv"
    )
    assert captured_inputs[0].imported_by == "curator"
    assert calls == [
        (
            "duplicate",
            [("confirmed_relationships", Path("data/confirmed_relationships.csv"))],
        ),
        "generate:RUN_STREAMLIT_IMPORT",
        "history",
    ]
    assert fake_st.json_payloads[0]["curated_relationship_count"] == 2


def test_import_tab_warns_on_duplicate_confirmed_relationship_file(monkeypatch) -> None:
    calls: list[object] = []
    fake_st = ImportQualityFakeStreamlit(
        buttons={"\u5f00\u59cb\u5bfc\u5165": True},
        checkboxes={"\u786e\u8ba4\u91cd\u590d\u5bfc\u5165": False},
        text_inputs=[
            "",
            "",
            "",
            "data/confirmed_relationships.csv",
            "local_user",
            "",
        ],
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    def fake_find_duplicate_import(sources):
        calls.append(("duplicate", sources))
        return {
            "run_id": "RUN_CONFIRMED_DUP",
            "imported_at": "2026-06-01T09:00:00Z",
            "imported_by": "curator",
            "source_files": [],
        }

    def fail_if_called(*_args, **_kwargs):
        calls.append("unexpected")
        raise AssertionError("duplicate confirmed imports should require confirmation")

    monkeypatch.setattr(streamlit_app, "find_duplicate_import", fake_find_duplicate_import)
    monkeypatch.setattr(streamlit_app, "run_import", fail_if_called)
    monkeypatch.setattr(streamlit_app, "generate_order_role_edges", fail_if_called)
    monkeypatch.setattr(streamlit_app, "aggregate_relationship_claims", fail_if_called)
    monkeypatch.setattr(streamlit_app, "apply_history_reuse_to_claims", fail_if_called)
    monkeypatch.setattr(
        streamlit_app,
        "list_import_batches",
        lambda **_kwargs: calls.append("history") or {"items": []},
    )

    streamlit_app.render_import_tab()

    assert calls == [
        (
            "duplicate",
            [("confirmed_relationships", Path("data/confirmed_relationships.csv"))],
        ),
        "history",
    ]
    assert len(fake_st.warnings) == 1
    assert "RUN_CONFIRMED_DUP" in fake_st.warnings[0]


def test_import_tab_reports_run_import_failure_and_skips_derived_steps(
    monkeypatch,
) -> None:
    calls: list[str] = []
    fake_st = ImportQualityFakeStreamlit(buttons={"\u5f00\u59cb\u5bfc\u5165": True})
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    def raise_missing_file(_inputs):
        calls.append("run_import")
        raise FileNotFoundError("missing.csv")

    def fail_if_called(*_args, **_kwargs):
        calls.append("derived")
        raise AssertionError("derived import steps should be skipped")

    def fake_list_import_batches(**_kwargs):
        calls.append("history")
        return {"items": []}

    monkeypatch.setattr(streamlit_app, "run_import", raise_missing_file)
    monkeypatch.setattr(streamlit_app, "generate_order_role_edges", fail_if_called)
    monkeypatch.setattr(streamlit_app, "aggregate_relationship_claims", fail_if_called)
    monkeypatch.setattr(streamlit_app, "apply_history_reuse_to_claims", fail_if_called)
    monkeypatch.setattr(streamlit_app, "list_import_batches", fake_list_import_batches)

    streamlit_app.render_import_tab()

    assert any("missing.csv" in message for message in fake_st.errors)
    assert calls == ["run_import", "history"]


def test_import_tab_reports_edge_generation_failure_without_crashing(
    monkeypatch,
) -> None:
    calls: list[str] = []
    fake_st = ImportQualityFakeStreamlit(buttons={"\u5f00\u59cb\u5bfc\u5165": True})
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "run_import",
        lambda _inputs: SimpleNamespace(
            run_id="RUN_STREAMLIT_IMPORT",
            entity_count=2,
            alias_count=0,
            evidence_count=1,
            claim_count=0,
            skipped_rows=[],
            archived_files=[],
            import_errors=[],
            warning_count=0,
            error_count=0,
            quality_summary={},
        ),
    )

    def raise_edge_generation_failed(*, run_id):
        calls.append(f"generate:{run_id}")
        raise RuntimeError("edge generation failed")

    def fail_if_called(*_args, **_kwargs):
        calls.append("downstream")
        raise AssertionError("downstream import steps should be skipped")

    def fake_list_import_batches(**_kwargs):
        calls.append("history")
        return {"items": []}

    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        raise_edge_generation_failed,
    )
    monkeypatch.setattr(streamlit_app, "aggregate_relationship_claims", fail_if_called)
    monkeypatch.setattr(streamlit_app, "apply_history_reuse_to_claims", fail_if_called)
    monkeypatch.setattr(streamlit_app, "list_import_batches", fake_list_import_batches)

    streamlit_app.render_import_tab()

    assert any("edge generation failed" in message for message in fake_st.errors)
    assert calls == ["generate:RUN_STREAMLIT_IMPORT", "history"]



def _successful_import_result(
    *, claim_count: int = 0, curated_relationship_count: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        run_id="RUN_STREAMLIT_IMPORT",
        entity_count=2,
        alias_count=0,
        evidence_count=1,
        claim_count=claim_count,
        curated_relationship_count=curated_relationship_count,
        skipped_rows=[],
        archived_files=[],
        import_errors=[],
        warning_count=0,
        error_count=0,
        quality_summary={},
    )


def test_import_tab_reports_claim_aggregation_failure_and_renders_history(
    monkeypatch,
) -> None:
    calls: list[str] = []
    fake_st = ImportQualityFakeStreamlit(buttons={"\u5f00\u59cb\u5bfc\u5165": True})
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "run_import", lambda _inputs: _successful_import_result())
    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        lambda *, run_id: {"edge_count": 1, "skipped_count": 0},
    )

    def raise_aggregation_failed(*, run_id):
        calls.append(f"aggregate:{run_id}")
        raise RuntimeError("claim aggregation failed")

    def fail_history_reuse(*_args, **_kwargs):
        calls.append("history_reuse")
        raise AssertionError("history reuse should be skipped")

    def fake_list_import_batches(**_kwargs):
        calls.append("history")
        return {"items": []}

    monkeypatch.setattr(streamlit_app, "aggregate_relationship_claims", raise_aggregation_failed)
    monkeypatch.setattr(streamlit_app, "apply_history_reuse_to_claims", fail_history_reuse)
    monkeypatch.setattr(streamlit_app, "list_import_batches", fake_list_import_batches)

    streamlit_app.render_import_tab()

    assert any("claim aggregation failed" in message for message in fake_st.errors)
    assert fake_st.successes == []
    assert fake_st.json_payloads == []
    assert calls == ["aggregate:RUN_STREAMLIT_IMPORT", "history"]


def test_import_tab_reports_history_reuse_failure_after_generated_edges(
    monkeypatch,
) -> None:
    calls: list[str] = []
    fake_st = ImportQualityFakeStreamlit(buttons={"\u5f00\u59cb\u5bfc\u5165": True})
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "run_import", lambda _inputs: _successful_import_result())
    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        lambda *, run_id: {"edge_count": 1, "skipped_count": 0},
    )
    monkeypatch.setattr(
        streamlit_app,
        "aggregate_relationship_claims",
        lambda *, run_id: {"claim_count": 1},
    )

    def raise_history_reuse_failed(*, run_id):
        calls.append(f"history_reuse:{run_id}")
        raise RuntimeError("history reuse failed after edges")

    monkeypatch.setattr(streamlit_app, "apply_history_reuse_to_claims", raise_history_reuse_failed)
    monkeypatch.setattr(
        streamlit_app,
        "list_import_batches",
        lambda **_kwargs: calls.append("history") or {"items": []},
    )

    streamlit_app.render_import_tab()

    assert any("history reuse failed after edges" in message for message in fake_st.errors)
    assert fake_st.successes == []
    assert fake_st.json_payloads == []
    assert calls == ["history_reuse:RUN_STREAMLIT_IMPORT", "history"]


def test_import_tab_reports_history_reuse_failure_after_imported_claims(
    monkeypatch,
) -> None:
    calls: list[str] = []
    fake_st = ImportQualityFakeStreamlit(buttons={"\u5f00\u59cb\u5bfc\u5165": True})
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "run_import",
        lambda _inputs: _successful_import_result(claim_count=2),
    )
    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        lambda *, run_id: {"edge_count": 0, "skipped_count": 0},
    )

    def fail_aggregate(*_args, **_kwargs):
        calls.append("aggregate")
        raise AssertionError("aggregate should be skipped when no edges were generated")

    def raise_history_reuse_failed(*, run_id):
        calls.append(f"history_reuse:{run_id}")
        raise RuntimeError("history reuse failed after imported claims")

    monkeypatch.setattr(streamlit_app, "aggregate_relationship_claims", fail_aggregate)
    monkeypatch.setattr(streamlit_app, "apply_history_reuse_to_claims", raise_history_reuse_failed)
    monkeypatch.setattr(
        streamlit_app,
        "list_import_batches",
        lambda **_kwargs: calls.append("history") or {"items": []},
    )

    streamlit_app.render_import_tab()

    assert any(
        "history reuse failed after imported claims" in message for message in fake_st.errors
    )
    assert fake_st.successes == []
    assert fake_st.json_payloads == []
    assert calls == ["history_reuse:RUN_STREAMLIT_IMPORT", "history"]


def test_import_tab_display_json_failure_is_not_reported_as_operation_error(
    monkeypatch,
) -> None:
    fake_st = ImportQualityFakeStreamlit(buttons={"\u5f00\u59cb\u5bfc\u5165": True})
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "run_import", lambda _inputs: _successful_import_result())
    monkeypatch.setattr(
        streamlit_app,
        "generate_order_role_edges",
        lambda *, run_id: {"edge_count": 1, "skipped_count": 0},
    )
    monkeypatch.setattr(
        streamlit_app,
        "aggregate_relationship_claims",
        lambda *, run_id: {"claim_count": 1},
    )
    monkeypatch.setattr(
        streamlit_app,
        "apply_history_reuse_to_claims",
        lambda *, run_id: {"history_matched": 0, "history_conflict": 0, "unchanged": 1},
    )
    monkeypatch.setattr(streamlit_app, "list_import_batches", lambda **_kwargs: {"items": []})

    def raise_json_failed(_payload, **_kwargs):
        raise RuntimeError("json display failed")

    monkeypatch.setattr(fake_st, "json", raise_json_failed)

    with pytest.raises(RuntimeError, match="json display failed"):
        streamlit_app.render_import_tab()

    assert fake_st.errors == []
    assert len(fake_st.successes) == 1


def test_import_tab_handles_recent_batch_lookup_errors(monkeypatch) -> None:
    fake_st = ImportQualityFakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)

    def raise_missing_table(**_kwargs):
        raise RuntimeError("no such table: import_batch")

    monkeypatch.setattr(streamlit_app, "list_import_batches", raise_missing_table)

    streamlit_app.render_import_tab()

    assert fake_st.errors == ["no such table: import_batch"]


def test_import_tab_detail_does_not_export_without_explicit_click(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    fake_st = ImportQualityFakeStreamlit(
        selected_run_id="RUN_DETAIL",
        buttons={"\u5f00\u59cb\u5bfc\u5165": False},
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "list_import_batches", lambda **_kwargs: {"items": []})

    def fake_get_detail(run_id: str):
        calls.append(("detail", run_id))
        return {"quality_summary": {}, "archived_files": [], "counts": {"orders": 2}}

    def fake_list_errors(run_id: str, **_kwargs):
        calls.append(("errors", run_id))
        return {"items": [{"row_number": 3, "error_type": "missing_entity"}]}

    def fail_export(_run_id: str):
        raise AssertionError("export_import_errors should wait for an explicit click")

    monkeypatch.setattr(streamlit_app, "get_import_batch_detail", fake_get_detail)
    monkeypatch.setattr(streamlit_app, "list_import_errors", fake_list_errors)
    monkeypatch.setattr(streamlit_app, "export_import_errors", fail_export)

    streamlit_app.render_import_tab()

    assert calls == [("detail", "RUN_DETAIL"), ("errors", "RUN_DETAIL")]
    assert fake_st.downloads == []


def test_import_tab_selected_run_detail_failure_reports_error(monkeypatch) -> None:
    fake_st = ImportQualityFakeStreamlit(
        selected_run_id="RUN_MISSING",
        buttons={"\u5f00\u59cb\u5bfc\u5165": False},
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "list_import_batches", lambda **_kwargs: {"items": []})

    def raise_unknown_batch(run_id: str):
        raise ValueError(f"Unknown import batch: {run_id}")

    monkeypatch.setattr(streamlit_app, "get_import_batch_detail", raise_unknown_batch)

    streamlit_app.render_import_tab()

    assert any("Unknown import batch" in message for message in fake_st.errors)


def test_import_tab_selected_run_error_list_failure_reports_error(monkeypatch) -> None:
    fake_st = ImportQualityFakeStreamlit(
        selected_run_id="RUN_DETAIL",
        buttons={"\u5f00\u59cb\u5bfc\u5165": False},
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "list_import_batches", lambda **_kwargs: {"items": []})
    monkeypatch.setattr(
        streamlit_app,
        "get_import_batch_detail",
        lambda run_id: {"quality_summary": {}, "archived_files": [], "counts": {"orders": 2}},
    )

    def raise_error_list_failed(run_id: str, **_kwargs):
        raise RuntimeError("error list failed")

    monkeypatch.setattr(streamlit_app, "list_import_errors", raise_error_list_failed)

    streamlit_app.render_import_tab()

    assert any("error list failed" in message for message in fake_st.errors)


def test_import_tab_detail_exports_after_explicit_click(monkeypatch, tmp_path) -> None:
    export_path = tmp_path / "RUN_DETAIL_import_errors.csv"
    export_path.write_text("row_number,error_type\n3,missing_entity\n", encoding="utf-8")
    calls: list[tuple[str, str]] = []
    fake_st = ImportQualityFakeStreamlit(
        selected_run_id="RUN_DETAIL",
        buttons={"\u5f00\u59cb\u5bfc\u5165": False, "\u751f\u6210\u5f02\u5e38 CSV": True},
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "list_import_batches", lambda **_kwargs: {"items": []})
    monkeypatch.setattr(
        streamlit_app,
        "get_import_batch_detail",
        lambda run_id: {"quality_summary": {}, "archived_files": [], "counts": {"orders": 2}},
    )
    monkeypatch.setattr(
        streamlit_app,
        "list_import_errors",
        lambda run_id, **_kwargs: {"items": [{"row_number": 3, "error_type": "missing_entity"}]},
    )

    def fake_export(run_id: str):
        calls.append(("export", run_id))
        return {"path": str(export_path)}

    monkeypatch.setattr(streamlit_app, "export_import_errors", fake_export)

    streamlit_app.render_import_tab()

    assert calls == [("export", "RUN_DETAIL")]
    assert fake_st.downloads[0]["file_name"] == "RUN_DETAIL_import_errors.csv"
    assert fake_st.downloads[0]["data"] == export_path.read_bytes()


def test_import_tab_export_failure_after_explicit_click_reports_error(monkeypatch) -> None:
    fake_st = ImportQualityFakeStreamlit(
        selected_run_id="RUN_DETAIL",
        buttons={"\u5f00\u59cb\u5bfc\u5165": False, "\u751f\u6210\u5f02\u5e38 CSV": True},
    )
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(streamlit_app, "list_import_batches", lambda **_kwargs: {"items": []})
    monkeypatch.setattr(
        streamlit_app,
        "get_import_batch_detail",
        lambda run_id: {"quality_summary": {}, "archived_files": [], "counts": {"orders": 2}},
    )
    monkeypatch.setattr(
        streamlit_app,
        "list_import_errors",
        lambda run_id, **_kwargs: {"items": [{"row_number": 3, "error_type": "missing_entity"}]},
    )

    def raise_export_failed(run_id: str):
        raise RuntimeError("export failed")

    monkeypatch.setattr(streamlit_app, "export_import_errors", raise_export_failed)

    streamlit_app.render_import_tab()

    assert any("export failed" in message for message in fake_st.errors)


def test_review_queue_tab_displays_queue_and_sets_selected_claim(monkeypatch) -> None:
    class FakeColumn:
        def metric(self, *_args, **_kwargs) -> None:
            return None

    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state: dict[str, str] = {}
            self.frames: list[list[dict]] = []
            self.success_messages: list[str] = []
            self.button_calls: list[tuple[str, dict]] = []

        def subheader(self, *_args, **_kwargs) -> None:
            return None

        def caption(self, *_args, **_kwargs) -> None:
            return None

        def multiselect(self, label, options, default=None, **_kwargs):
            if label == "关系状态":
                return list(default or options)
            return []

        def text_input(self, *_args, **_kwargs) -> str:
            return ""

        def number_input(self, *_args, value=100, **_kwargs) -> int:
            return value

        def warning(self, *_args, **_kwargs) -> None:
            return None

        def columns(self, count: int):
            return [FakeColumn() for _ in range(count)]

        def info(self, *_args, **_kwargs) -> None:
            return None

        def dataframe(self, rows, **_kwargs) -> None:
            self.frames.append(rows)

        def selectbox(self, _label, options, **_kwargs) -> str:
            return list(options)[0]

        def markdown(self, *_args, **_kwargs) -> None:
            return None

        def expander(self, *_args, **_kwargs) -> FakeExpander:
            return FakeExpander()

        def button(self, label, **kwargs) -> bool:
            self.button_calls.append((str(label), kwargs))
            return label == "带到人工审核 tab"

        def success(self, message: str) -> None:
            self.success_messages.append(message)

    fake_st = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "list_review_queue",
        lambda **_kwargs: {
            "summary": {
                "total_count": 1,
                "status_counts": {
                    "history_conflict": 1,
                    "history_matched": 0,
                    "candidate": 0,
                    "pending_verify": 0,
                },
            },
            "items": [
                {
                    "claim_id": "CLM_QUEUE",
                    "from_name": "ACME TRADING",
                    "to_name": "BETA FACTORY",
                    "relation_status": "history_conflict",
                    "confidence_level": "high",
                    "order_count": 8,
                }
            ],
        },
    )
    monkeypatch.setattr(
        streamlit_app,
        "get_relationship_detail",
        lambda _claim_id: {
            "claim_id": "CLM_QUEUE",
            "from_name": "ACME TRADING",
            "to_name": "BETA FACTORY",
            "candidate_relation_type": "trading_partner_candidate",
            "relation_status": "history_conflict",
        },
    )
    monkeypatch.setattr(streamlit_app, "get_relationship_evidence", lambda _claim_id: [])

    streamlit_app.render_review_queue_tab()

    assert fake_st.frames
    assert fake_st.session_state[streamlit_app.SELECTED_CLAIM_STATE_KEY] == "CLM_QUEUE"
    assert fake_st.session_state[streamlit_app.REVIEW_CLAIM_WIDGET_KEY] == "CLM_QUEUE"
    assert fake_st.success_messages
    assert any(
        kwargs.get("key") == "review_queue_to_review_button"
        for _label, kwargs in fake_st.button_calls
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



def test_review_tab_defaults_relation_type_from_candidate_type(monkeypatch) -> None:
    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {streamlit_app.REVIEW_CLAIM_WIDGET_KEY: "CLM_1"}
            self.selectbox_calls: list[tuple[str, tuple[str, ...], int]] = []

        def subheader(self, *_args, **_kwargs) -> None:
            return None

        def text_input(self, _label, value="", key=None, **_kwargs) -> str:
            if key == streamlit_app.REVIEW_CLAIM_WIDGET_KEY:
                return "CLM_1"
            return value

        def markdown(self, *_args, **_kwargs) -> None:
            return None

        def expander(self, *_args, **_kwargs) -> FakeExpander:
            return FakeExpander()

        def json(self, *_args, **_kwargs) -> None:
            return None

        def selectbox(self, label, options, index=0, **_kwargs) -> str:
            option_tuple = tuple(options)
            self.selectbox_calls.append((label, option_tuple, index))
            return option_tuple[index]

        def text_area(self, *_args, **_kwargs) -> str:
            return ""

        def button(self, *_args, **_kwargs) -> bool:
            return False

        def divider(self) -> None:
            return None

    fake_st = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "get_relationship_detail",
        lambda _claim_id: {
            "claim_id": "CLM_1",
            "from_name": "ACME TRADING",
            "to_name": "BETA FACTORY",
            "candidate_relation_type": "factory_candidate",
            "history_context": None,
        },
    )

    streamlit_app.render_review_tab()

    relation_type_calls = [
        call
        for call in fake_st.selectbox_calls
        if call[0] == "\u5173\u7cfb\u7c7b\u578b"
    ]
    assert relation_type_calls
    _label, options, index = relation_type_calls[0]
    assert options[index] == "factory_node"


def test_review_submit_value_error_displays_error(monkeypatch) -> None:
    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {streamlit_app.REVIEW_CLAIM_WIDGET_KEY: "CLM_1"}
            self.errors: list[str] = []

        def subheader(self, *_args, **_kwargs) -> None:
            return None

        def text_input(self, _label, value="", key=None, **_kwargs) -> str:
            if key == streamlit_app.REVIEW_CLAIM_WIDGET_KEY:
                return "CLM_1"
            return value

        def markdown(self, *_args, **_kwargs) -> None:
            return None

        def expander(self, *_args, **_kwargs) -> FakeExpander:
            return FakeExpander()

        def json(self, *_args, **_kwargs) -> None:
            return None

        def selectbox(self, _label, options, index=0, **_kwargs) -> str:
            return tuple(options)[index]

        def text_area(self, *_args, **_kwargs) -> str:
            return "reason"

        def button(self, label, **_kwargs) -> bool:
            return label == "\u63d0\u4ea4\u5ba1\u6838"

        def error(self, message: str) -> None:
            self.errors.append(message)

        def divider(self) -> None:
            return None

    def raise_value_error(*_args, **_kwargs):
        raise ValueError("claim already finalized")

    fake_st = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "get_relationship_detail",
        lambda _claim_id: {
            "claim_id": "CLM_1",
            "from_name": "ACME TRADING",
            "to_name": "BETA FACTORY",
            "candidate_relation_type": "trading_partner_candidate",
            "history_context": None,
        },
    )
    monkeypatch.setattr(streamlit_app, "decide_relationship", raise_value_error)

    streamlit_app.render_review_tab()

    assert fake_st.errors == ["claim already finalized"]


def test_review_submit_success_stores_flash_and_requests_rerun(monkeypatch) -> None:
    class FakeExpander:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class FakeStreamlit:
        def __init__(self) -> None:
            self.session_state = {streamlit_app.REVIEW_CLAIM_WIDGET_KEY: "CLM_1"}
            self.rerun_count = 0

        def subheader(self, *_args, **_kwargs) -> None:
            return None

        def text_input(self, label, value="", key=None, **_kwargs) -> str:
            if key == streamlit_app.REVIEW_CLAIM_WIDGET_KEY:
                return "CLM_1"
            if label == "\u64cd\u4f5c\u4eba":
                return "tester"
            return value

        def markdown(self, *_args, **_kwargs) -> None:
            return None

        def expander(self, *_args, **_kwargs) -> FakeExpander:
            return FakeExpander()

        def json(self, *_args, **_kwargs) -> None:
            return None

        def selectbox(self, _label, options, index=0, **_kwargs) -> str:
            return tuple(options)[index]

        def text_area(self, *_args, **_kwargs) -> str:
            return "review reason"

        def button(self, label, **_kwargs) -> bool:
            return label == "\u63d0\u4ea4\u5ba1\u6838"

        def error(self, *_args, **_kwargs) -> None:
            return None

        def divider(self) -> None:
            return None

        def rerun(self) -> None:
            self.rerun_count += 1

    fake_st = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake_st)
    monkeypatch.setattr(
        streamlit_app,
        "get_relationship_detail",
        lambda _claim_id: {
            "claim_id": "CLM_1",
            "from_name": "ACME TRADING",
            "to_name": "BETA FACTORY",
            "candidate_relation_type": "trading_partner_candidate",
            "relation_status": "candidate",
            "history_context": None,
        },
    )
    monkeypatch.setattr(
        streamlit_app,
        "decide_relationship",
        lambda *_args, **_kwargs: {"relationship_id": "REL_1"},
    )

    streamlit_app.render_review_tab()

    assert fake_st.rerun_count == 1
    assert fake_st.session_state[streamlit_app.REVIEW_CLEAR_CLAIM_STATE_KEY] is True
    assert fake_st.session_state[streamlit_app.REVIEW_SUCCESS_FLASH_STATE_KEY] == {
        "claim_id": "CLM_1",
        "result": {"relationship_id": "REL_1"},
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

def test_import_quality_status_label_distinguishes_errors_and_warnings() -> None:
    assert (
        streamlit_app.format_import_quality_status(
            {"blocking_error_count": 0, "warning_count": 0}
        )
        == "无异常"
    )
    assert (
        streamlit_app.format_import_quality_status(
            {"blocking_error_count": 0, "warning_count": 2}
        )
        == "仅警告：2 条"
    )
    assert (
        streamlit_app.format_import_quality_status(
            {"blocking_error_count": 3, "warning_count": 2}
        )
        == "阻断异常：3 条，警告：2 条"
    )


def test_import_error_export_filename_uses_run_id() -> None:
    assert streamlit_app.import_error_export_filename("RUN_ABC") == "RUN_ABC_import_errors.csv"
