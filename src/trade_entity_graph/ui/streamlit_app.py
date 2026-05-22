"""Streamlit MVP workbench."""

from __future__ import annotations

from pathlib import Path

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


def render_import_tab() -> None:
    """Render the import workflow."""

    st.subheader("Import Excel/CSV")
    entities_path = st.text_input("Entity cleaning file path")
    orders_path = st.text_input("Order detail file path")
    relationships_path = st.text_input("Existing relationship candidate file path")
    imported_by = st.text_input("Imported by", value="local_user")
    if st.button("Run import"):
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
        st.success(f"Imported run {result.run_id}")
        st.json({**result.__dict__, **edge_result, **claim_result})


def render_search_tab() -> None:
    """Render entity search."""

    st.subheader("Entity Search")
    query = st.text_input("Company name or alias")
    if query:
        matches = search_entities(query)
        st.dataframe(matches)
        selected = st.text_input("Entity ID for detail")
        if selected:
            st.json(get_entity_detail(selected))


def render_graph_tab() -> None:
    """Render one-hop graph JSON."""

    st.subheader("One-Hop Graph")
    center_entity_id = st.text_input("Center entity ID")
    include_rejected = st.checkbox("Include rejected curated relationships")
    if center_entity_id:
        graph = get_ego_graph(center_entity_id, include_rejected=include_rejected)
        st.metric("Nodes", graph["summary"]["node_count"])
        st.metric("Edges", graph["summary"]["edge_count"])
        st.dataframe(graph["nodes"])
        st.dataframe(graph["edges"])


def render_relationship_detail_tab() -> None:
    """Render relationship details and evidence."""

    st.subheader("Relationship Detail")
    relationship_id = st.text_input("Relationship or claim ID")
    if relationship_id:
        st.json(get_relationship_detail(relationship_id))
        st.dataframe(get_relationship_evidence(relationship_id))


def render_review_tab() -> None:
    """Render manual review actions."""

    st.subheader("Review")
    claim_id = st.text_input("Claim ID")
    action_type = st.selectbox("Action", ["confirm", "reject", "modify"])
    relation_type = st.text_input("Relation type", value="trading_partner")
    reason = st.text_area("Reason")
    operator = st.text_input("Operator", value="local_user")
    if st.button("Submit decision") and claim_id:
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
    st.subheader("Manual Relationship")
    from_entity_id = st.text_input("From entity ID")
    to_entity_id = st.text_input("To entity ID")
    manual_relation_type = st.text_input("Manual relation type", value="trading_partner")
    manual_reason = st.text_area("Manual reason")
    if st.button("Create manual relationship") and from_entity_id and to_entity_id:
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

    st.subheader("Export Relationships")
    center_entity_id = st.text_input("Center entity ID for export")
    include_rejected = st.checkbox("Include rejected relationships in export")
    if center_entity_id:
        rows = export_relationship_rows(center_entity_id, include_rejected=include_rejected)
        st.dataframe(rows)
        st.download_button(
            "Download JSON",
            data=str(rows),
            file_name=f"{center_entity_id}_relationships.txt",
        )


def main() -> None:
    st.set_page_config(page_title="Trade Entity Graph", layout="wide")
    st.title("Trade Entity Graph")
    st.caption("MVP P0 workbench: import, search, graph, review, and export flows.")
    tabs = st.tabs(["Import", "Search", "Graph", "Relationship Detail", "Review", "Export"])
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
