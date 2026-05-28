from types import SimpleNamespace

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
    ) -> None:
        self.selected_run_id = selected_run_id
        self.buttons = buttons or {}
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.warnings: list[str] = []
        self.frames: list[object] = []
        self.downloads: list[dict[str, object]] = []
        self.json_payloads: list[object] = []

    def subheader(self, *_args, **_kwargs) -> None:
        return None

    def text_input(self, label, value="", **_kwargs) -> str:
        if "run_id" in str(label):
            return self.selected_run_id
        return value

    def button(self, label, **_kwargs) -> bool:
        return self.buttons.get(str(label), False)

    def success(self, *_args, **_kwargs) -> None:
        return None

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

        def button(self, label, **_kwargs) -> bool:
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
