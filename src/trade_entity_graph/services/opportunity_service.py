"""M11 graph analytics and opportunity discovery service."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.services.graph_service import (
    PENDING_CLAIM_STATUSES,
    _aggregate_order_path_edges,
    _all_visible_edges,
)

CUSTOMER_ENTITY_TYPES = {"customer", "buyer", "group"}
OVERSEAS_NODE_ENTITY_TYPES = {
    "factory",
    "shipper",
    "consignee",
    "subsidiary",
    "sales_center",
}


def _clamp(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _confidence_value(level: Any, score: Any) -> float:
    if score is not None:
        return _clamp(_safe_float(score))
    if level == "high":
        return 0.8
    if level == "medium":
        return 0.55
    if level == "low":
        return 0.3
    return 0.0


def _edge_total_teu(edge: dict[str, Any]) -> float:
    raw_teu = edge.get("total_teu") if edge.get("total_teu") is not None else edge.get("teu")
    return _safe_float(raw_teu)


def _edge_order_count(edge: dict[str, Any]) -> int:
    raw_count = edge.get("order_count")
    if raw_count is None:
        return 1 if edge.get("record_type") == "order_role_edge" else 0
    return int(_safe_float(raw_count))


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _fetch_entities(connection: Any, entity_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not entity_ids:
        return {}
    sorted_ids = sorted(entity_ids)
    placeholders = ", ".join("?" for _ in sorted_ids)
    rows = connection.execute(
        f"""
        SELECT entity_id, canonical_name, country, entity_type, tags, status
        FROM entity
        WHERE entity_id IN ({placeholders})
        """,
        tuple(sorted_ids),
    ).fetchall()
    return {row["entity_id"]: _row_dict(row) for row in rows}


def _build_graph(
    entities: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> nx.Graph:
    graph = nx.Graph()
    for entity_id, entity in entities.items():
        graph.add_node(entity_id, **entity)

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        if source not in graph:
            graph.add_node(source, entity_id=source, canonical_name=source)
        if target not in graph:
            graph.add_node(target, entity_id=target, canonical_name=target)
        if graph.has_edge(source, target):
            graph[source][target]["records"].append(edge)
        else:
            graph.add_edge(source, target, records=[edge])
    return graph


def _records_for_edges(graph: nx.Graph, node_ids: set[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source, target, data in graph.edges(data=True):
        if source in node_ids and target in node_ids:
            records.extend(data.get("records") or [])
    return records


def _record_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidate_edge_count": sum(
            record.get("record_type") == "relationship_claim" for record in records
        ),
        "curated_edge_count": sum(
            record.get("record_type") == "curated_relationship" for record in records
        ),
        "order_edge_count": sum(
            record.get("record_type") == "order_role_edge" for record in records
        ),
        "verified_relationship_count": sum(
            record.get("record_type") == "curated_relationship"
            and record.get("status") == "verified"
            for record in records
        ),
    }


def _top_entities_for_component(
    graph: nx.Graph,
    node_ids: set[str],
    entities: dict[str, dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    subgraph = graph.subgraph(node_ids)
    ranked_ids = sorted(
        node_ids,
        key=lambda entity_id: (
            -subgraph.degree(entity_id),
            entities.get(entity_id, {}).get("canonical_name") or entity_id,
        ),
    )
    rows = []
    for entity_id in ranked_ids[:limit]:
        entity = entities.get(entity_id, {})
        rows.append(
            {
                "entity_id": entity_id,
                "canonical_name": entity.get("canonical_name") or entity_id,
                "entity_type": entity.get("entity_type"),
                "country": entity.get("country"),
                "degree": subgraph.degree(entity_id),
            }
        )
    return rows


def _component_clusters(
    graph: nx.Graph,
    entities: dict[str, dict[str, Any]],
    *,
    min_score: float,
) -> list[dict[str, Any]]:
    clusters = []
    components = [set(component) for component in nx.connected_components(graph)]
    components.sort(
        key=lambda node_ids: (
            -len(node_ids),
            min(
                entities.get(entity_id, {}).get("canonical_name") or entity_id
                for entity_id in node_ids
            ),
        )
    )
    for index, node_ids in enumerate(components, start=1):
        records = _records_for_edges(graph, node_ids)
        counts = _record_counts(records)
        countries = sorted(
            {
                str(entities.get(entity_id, {}).get("country"))
                for entity_id in node_ids
                if entities.get(entity_id, {}).get("country")
            }
        )
        total_teu = round(sum(_edge_total_teu(record) for record in records), 2)
        opportunity_score = round(
            _clamp(
                0.04 * len(node_ids)
                + 0.08 * counts["candidate_edge_count"]
                + 0.10 * counts["verified_relationship_count"]
                + 0.04 * len(countries)
                + min(total_teu / 150.0, 0.28)
            ),
            4,
        )
        if opportunity_score < min_score:
            continue
        clusters.append(
            {
                "cluster_id": f"CLS_{index:03d}",
                "entity_count": len(node_ids),
                "edge_count": len(records),
                **counts,
                "country_count": len(countries),
                "countries": "; ".join(countries),
                "total_teu": total_teu,
                "top_entities": _top_entities_for_component(graph, node_ids, entities),
                "opportunity_score": opportunity_score,
                "recommendation_reason": (
                    "关系密集且存在待审核候选，适合做客户网络梳理和机会复核。"
                    if counts["candidate_edge_count"]
                    else "已有关系网络较集中，可用于客户分层或 BI 看板。"
                ),
            }
        )
    return sorted(
        clusters,
        key=lambda row: (-row["opportunity_score"], -row["entity_count"], row["cluster_id"]),
    )


def _bridge_entities(
    graph: nx.Graph,
    entities: dict[str, dict[str, Any]],
    *,
    min_score: float,
) -> list[dict[str, Any]]:
    if graph.number_of_nodes() < 3:
        return []

    centrality = nx.betweenness_centrality(graph, normalized=True)
    articulation_points = set(nx.articulation_points(graph))
    rows = []
    for entity_id in graph.nodes:
        degree = graph.degree(entity_id)
        node_centrality = centrality.get(entity_id, 0.0)
        if degree < 2 and node_centrality == 0:
            continue

        adjacent_records: list[dict[str, Any]] = []
        neighbor_countries = set()
        for neighbor_id in graph.neighbors(entity_id):
            adjacent_records.extend(graph[entity_id][neighbor_id].get("records") or [])
            country = entities.get(neighbor_id, {}).get("country")
            if country:
                neighbor_countries.add(str(country))
        counts = _record_counts(adjacent_records)
        total_teu = round(sum(_edge_total_teu(record) for record in adjacent_records), 2)
        is_articulation = entity_id in articulation_points
        opportunity_score = round(
            _clamp(
                node_centrality * 0.65
                + min(degree / 10.0, 0.25)
                + (0.15 if is_articulation else 0.0)
                + min(counts["candidate_edge_count"] / 8.0, 0.15)
                + min(len(neighbor_countries) / 8.0, 0.10)
                + min(total_teu / 200.0, 0.10)
            ),
            4,
        )
        if opportunity_score < min_score:
            continue
        entity = entities.get(entity_id, {})
        rows.append(
            {
                "entity_id": entity_id,
                "canonical_name": entity.get("canonical_name") or entity_id,
                "entity_type": entity.get("entity_type"),
                "country": entity.get("country"),
                "degree": degree,
                "betweenness": round(node_centrality, 4),
                "is_articulation_point": is_articulation,
                "neighbor_country_count": len(neighbor_countries),
                "neighbor_countries": "; ".join(sorted(neighbor_countries)),
                **counts,
                "total_teu": total_teu,
                "opportunity_score": opportunity_score,
                "recommendation_reason": (
                    "该主体是关系网络桥接点，优先确认其集团、工厂或贸易伙伴角色。"
                    if is_articulation
                    else "该主体连接多个关系对象，可作为销售触达或关系补证入口。"
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -row["opportunity_score"],
            -row["degree"],
            row["canonical_name"],
        ),
    )


def _is_customer_like(entity: dict[str, Any]) -> bool:
    entity_type = str(entity.get("entity_type") or "").lower()
    tags = str(entity.get("tags") or "").lower()
    return entity_type in CUSTOMER_ENTITY_TYPES or "customer" in tags or "key_customer" in tags


def _is_overseas_node(
    customer: dict[str, Any],
    entity: dict[str, Any],
) -> bool:
    entity_country = entity.get("country")
    customer_country = customer.get("country")
    if entity_country and customer_country and entity_country != customer_country:
        return True
    if entity_country and not customer_country:
        return True
    entity_type = str(entity.get("entity_type") or "").lower()
    return entity_type in OVERSEAS_NODE_ENTITY_TYPES


def _customer_opportunities(
    graph: nx.Graph,
    entities: dict[str, dict[str, Any]],
    *,
    min_score: float,
) -> list[dict[str, Any]]:
    rows = []
    for entity_id, entity in entities.items():
        if not _is_customer_like(entity):
            continue
        path_lengths = nx.single_source_shortest_path_length(graph, entity_id, cutoff=2)
        reachable_ids = {node_id for node_id, distance in path_lengths.items() if distance > 0}
        if not reachable_ids:
            continue

        direct_ids = {node_id for node_id, distance in path_lengths.items() if distance == 1}
        second_hop_ids = {node_id for node_id, distance in path_lengths.items() if distance == 2}
        scoped_ids = reachable_ids | {entity_id}
        records = _records_for_edges(graph, scoped_ids)
        counts = _record_counts(records)
        total_teu = round(sum(_edge_total_teu(record) for record in records), 2)
        overseas_ids = {
            node_id
            for node_id in reachable_ids
            if _is_overseas_node(entity, entities.get(node_id, {}))
        }
        countries = sorted(
            {
                str(entities.get(node_id, {}).get("country"))
                for node_id in overseas_ids
                if entities.get(node_id, {}).get("country")
            }
        )
        opportunity_score = round(
            _clamp(
                0.08 * len(direct_ids)
                + 0.05 * len(second_hop_ids)
                + 0.10 * len(overseas_ids)
                + 0.12 * counts["candidate_edge_count"]
                + min(total_teu / 150.0, 0.25)
            ),
            4,
        )
        if opportunity_score < min_score:
            continue
        rows.append(
            {
                "entity_id": entity_id,
                "canonical_name": entity.get("canonical_name") or entity_id,
                "country": entity.get("country"),
                "direct_neighbor_count": len(direct_ids),
                "second_hop_entity_count": len(second_hop_ids),
                "overseas_node_count": len(overseas_ids),
                "overseas_countries": "; ".join(countries),
                **counts,
                "total_teu": total_teu,
                "opportunity_score": opportunity_score,
                "recommendation_reason": (
                    "该客户存在多层海外节点和待审核关系，适合输出销售机会清单。"
                    if counts["candidate_edge_count"]
                    else "该客户已有海外关系网络，可用于客户分层和持续监控。"
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-row["opportunity_score"], row["canonical_name"]),
    )


def _relationship_opportunity_score(row: dict[str, Any]) -> float:
    confidence = _confidence_value(row.get("confidence_level"), row.get("confidence_score"))
    order_count = _safe_float(row.get("order_count"))
    total_teu = _safe_float(row.get("total_teu"))
    status_bonus = 0.08 if row.get("relation_status") == "history_conflict" else 0.0
    return round(
        _clamp(
            confidence
            + min(order_count / 20.0, 0.18)
            + min(total_teu / 120.0, 0.18)
            + status_bonus
        ),
        4,
    )


def _relationship_opportunities(
    connection: Any,
    *,
    min_score: float,
) -> list[dict[str, Any]]:
    status_placeholders = ", ".join("?" for _ in PENDING_CLAIM_STATUSES)
    rows = connection.execute(
        f"""
        SELECT
            rc.*,
            e1.canonical_name AS from_name,
            e1.country AS from_country,
            e1.entity_type AS from_entity_type,
            e2.canonical_name AS to_name,
            e2.country AS to_country,
            e2.entity_type AS to_entity_type
        FROM relationship_claim rc
        JOIN entity e1 ON e1.entity_id = rc.from_entity_id
        JOIN entity e2 ON e2.entity_id = rc.to_entity_id
        WHERE rc.relation_status IN ({status_placeholders})
          AND NOT EXISTS (
              SELECT 1
              FROM curated_relationship cr
              WHERE cr.decision_source = rc.claim_id
          )
        ORDER BY rc.confidence_score DESC, rc.order_count DESC, rc.total_teu DESC, rc.created_at
        """,
        PENDING_CLAIM_STATUSES,
    ).fetchall()

    opportunities = []
    for row in rows:
        item = _row_dict(row)
        score = _relationship_opportunity_score(item)
        if score < min_score:
            continue
        item["opportunity_score"] = score
        item["opportunity_type"] = "relationship_review"
        item["recommendation_reason"] = (
            item.get("recommendation_reason")
            or "该候选关系具备订单、置信度或历史冲突信号，建议优先审核。"
        )
        opportunities.append(item)
    return sorted(
        opportunities,
        key=lambda row: (
            -row["opportunity_score"],
            -(row.get("order_count") or 0),
            -(row.get("total_teu") or 0),
            row.get("claim_id") or "",
        ),
    )


def analyze_graph_opportunities(
    *,
    db_path: str | Path | None = None,
    include_rejected: bool = False,
    limit: int = 20,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """Return M11 graph-analysis and opportunity-discovery results."""

    if limit < 1:
        raise ValueError("limit must be positive")
    if min_score < 0 or min_score > 1:
        raise ValueError("min_score must be between 0 and 1")

    with get_connection(db_path) as connection:
        edges = _aggregate_order_path_edges(
            _all_visible_edges(connection, include_rejected=include_rejected)
        )
        entity_ids = {
            str(edge[endpoint])
            for edge in edges
            for endpoint in ("source", "target")
            if edge.get(endpoint)
        }
        entities = _fetch_entities(connection, entity_ids)
        graph = _build_graph(entities, edges)

        clusters = _component_clusters(graph, entities, min_score=min_score)
        bridge_entities = _bridge_entities(graph, entities, min_score=min_score)
        customer_opportunities = _customer_opportunities(graph, entities, min_score=min_score)
        relationship_opportunities = _relationship_opportunities(
            connection,
            min_score=min_score,
        )

    max_scores = [
        *(row["opportunity_score"] for row in clusters),
        *(row["opportunity_score"] for row in bridge_entities),
        *(row["opportunity_score"] for row in customer_opportunities),
        *(row["opportunity_score"] for row in relationship_opportunities),
    ]
    countries = Counter(
        str(entity.get("country"))
        for entity in entities.values()
        if entity.get("country")
    )
    return {
        "summary": {
            "entity_count": len(entities),
            "edge_count": len(edges),
            "cluster_count": len(clusters),
            "bridge_entity_count": len(bridge_entities),
            "customer_opportunity_count": len(customer_opportunities),
            "relationship_opportunity_count": len(relationship_opportunities),
            "country_count": len(countries),
            "max_opportunity_score": round(max(max_scores), 4) if max_scores else 0.0,
            "include_rejected": include_rejected,
            "min_score": min_score,
        },
        "clusters": clusters[:limit],
        "bridge_entities": bridge_entities[:limit],
        "customer_opportunities": customer_opportunities[:limit],
        "relationship_opportunities": relationship_opportunities[:limit],
    }
