"""Relationship candidate and curated relationship operations."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection
from trade_entity_graph.importers.entity_loader import find_entity_id_by_name
from trade_entity_graph.services.history_reuse_service import get_history_context_for_claim
from trade_entity_graph.utils.ids import new_id
from trade_entity_graph.utils.normalization import normalize_company_name

ORDER_ROLE_PAIRS = (
    ("customer_name", "customer", "shipper_name", "shipper", "customer_to_shipper"),
    ("customer_name", "customer", "consignee_name", "consignee", "customer_to_consignee"),
    ("customer_name", "customer", "notify_name", "notify", "customer_to_notify"),
    ("shipper_name", "shipper", "consignee_name", "consignee", "shipper_to_consignee"),
    ("shipper_name", "shipper", "notify_name", "notify", "shipper_to_notify"),
    ("consignee_name", "consignee", "notify_name", "notify", "consignee_to_notify"),
)

INVALID_ROLE_NAMES = {"", "SAME AS", "TO ORDER", "YQN", "YQN LOGISTICS"}
REVIEWABLE_DETAIL_CLAIM_STATUSES = (
    "candidate",
    "history_matched",
    "history_conflict",
    "pending_verify",
)
EXTERNAL_EVIDENCE_FIELDS = (
    "evidence_type",
    "source_title",
    "source_url",
    "source_name",
    "evidence_summary",
    "evidence_date",
    "confidence_level",
    "created_by",
)


def _is_invalid_role_name(value: str | None) -> bool:
    normalized = normalize_company_name(value)
    return normalized in INVALID_ROLE_NAMES or normalized.startswith("YQN ")


def generate_order_role_edges(
    *, db_path: str | Path | None = None, run_id: str | None = None
) -> dict[str, int]:
    """Generate P0 and P1 order-role evidence edges from imported order evidence."""

    with get_connection(db_path) as connection:
        if run_id:
            connection.execute("DELETE FROM order_role_edge WHERE run_id = ?", (run_id,))
            evidence_rows = connection.execute(
                "SELECT * FROM order_evidence WHERE run_id = ? ORDER BY order_id, source_row",
                (run_id,),
            ).fetchall()
        else:
            connection.execute("DELETE FROM order_role_edge")
            evidence_rows = connection.execute(
                "SELECT * FROM order_evidence ORDER BY order_id, source_row"
            ).fetchall()

        edge_count = 0
        skipped_count = 0
        for evidence in evidence_rows:
            for from_col, from_role, to_col, to_role, pair_type in ORDER_ROLE_PAIRS:
                from_name = evidence[from_col]
                to_name = evidence[to_col]
                if _is_invalid_role_name(from_name) or _is_invalid_role_name(to_name):
                    skipped_count += 1
                    continue

                from_entity_id = find_entity_id_by_name(connection, from_name)
                to_entity_id = find_entity_id_by_name(connection, to_name)
                if not from_entity_id or not to_entity_id or from_entity_id == to_entity_id:
                    skipped_count += 1
                    continue

                connection.execute(
                    """
                    INSERT INTO order_role_edge (
                        edge_id, evidence_id, order_id, from_entity_id, from_role,
                        to_entity_id, to_role, role_pair_type, teu, product_name,
                        function_category, destination_country, destination_port,
                        order_date, source_file, source_sheet, source_row, run_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("EDG"),
                        evidence["evidence_id"],
                        evidence["order_id"],
                        from_entity_id,
                        from_role,
                        to_entity_id,
                        to_role,
                        pair_type,
                        evidence["teu"],
                        evidence["product_name"],
                        evidence["function_category"],
                        evidence["destination_country"],
                        evidence["destination_port"],
                        evidence["order_date"],
                        evidence["source_file"],
                        evidence["source_sheet"],
                        evidence["source_row"],
                        evidence["run_id"],
                    ),
                )
                edge_count += 1

        connection.commit()
        return {"edge_count": edge_count, "skipped_count": skipped_count}


def _confidence(order_count: int, total_teu: float) -> tuple[str, float]:
    if order_count >= 5 or total_teu >= 20:
        return "high", 0.8
    if order_count >= 2 or total_teu >= 5:
        return "medium", 0.55
    return "low", 0.3


def _summary(counter: Counter[str] | set[str]) -> str:
    if isinstance(counter, Counter):
        return "; ".join(f"{key}:{counter[key]}" for key in sorted(counter))
    return "; ".join(sorted(value for value in counter if value))


def aggregate_relationship_claims(
    *, db_path: str | Path | None = None, run_id: str | None = None
) -> dict[str, int]:
    """Aggregate order-role edges into explainable relationship candidates."""

    with get_connection(db_path) as connection:
        if run_id:
            connection.execute("DELETE FROM relationship_claim WHERE run_id = ?", (run_id,))
            edge_rows = connection.execute(
                "SELECT * FROM order_role_edge WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        else:
            connection.execute("DELETE FROM relationship_claim")
            edge_rows = connection.execute("SELECT * FROM order_role_edge").fetchall()

        groups: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {
                "orders": set(),
                "teu_by_order": {},
                "roles": Counter(),
                "destinations": set(),
                "products": set(),
            }
        )
        for edge in edge_rows:
            key = (edge["from_entity_id"], edge["to_entity_id"])
            group = groups[key]
            order_id = edge["order_id"] or edge["edge_id"]
            group["orders"].add(order_id)
            group["teu_by_order"][order_id] = max(
                float(group["teu_by_order"].get(order_id, 0) or 0),
                float(edge["teu"] or 0),
            )
            group["roles"][edge["role_pair_type"]] += 1
            if edge["destination_country"]:
                group["destinations"].add(edge["destination_country"])
            if edge["product_name"]:
                group["products"].add(edge["product_name"])

        claim_count = 0
        for (from_entity_id, to_entity_id), group in groups.items():
            order_count = len(group["orders"])
            total_teu = round(sum(group["teu_by_order"].values()), 2)
            confidence_level, confidence_score = _confidence(order_count, total_teu)
            role_pair_summary = _summary(group["roles"])
            destination_summary = _summary(group["destinations"])
            product_summary = _summary(group["products"])
            reason_parts = [f"{order_count} orders", f"{total_teu:g} TEU"]
            if role_pair_summary:
                reason_parts.append(f"roles: {role_pair_summary}")
            if destination_summary:
                reason_parts.append(f"destinations: {destination_summary}")
            if product_summary:
                reason_parts.append(f"products: {product_summary}")

            connection.execute(
                """
                INSERT INTO relationship_claim (
                    claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                    relation_status, confidence_level, confidence_score, order_count,
                    total_teu, role_pair_summary, destination_summary, product_summary,
                    recommendation_reason, run_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("CLM"),
                    from_entity_id,
                    to_entity_id,
                    "trading_partner_candidate",
                    "candidate",
                    confidence_level,
                    confidence_score,
                    order_count,
                    total_teu,
                    role_pair_summary,
                    destination_summary,
                    product_summary,
                    ", ".join(reason_parts),
                    run_id,
                ),
            )
            claim_count += 1

        connection.commit()
        return {"claim_count": claim_count}


def _has_final_review_artifacts(connection, claim_id: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM relationship_decision
        WHERE claim_id = ?
          AND action_type IN ('confirm', 'modify', 'reject', 'keep_history', 'supersede')
        UNION
        SELECT 1
        FROM curated_relationship
        WHERE decision_source = ?
        LIMIT 1
        """,
        (claim_id, claim_id),
    ).fetchone()
    return row is not None


def get_relationship_detail(
    relationship_id: str, *, db_path: str | Path | None = None
) -> dict[str, Any] | None:
    """Return one curated relationship or candidate relationship by id."""

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT cr.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name,
                   'curated_relationship' AS record_type
            FROM curated_relationship cr
            JOIN entity e1 ON e1.entity_id = cr.from_entity_id
            JOIN entity e2 ON e2.entity_id = cr.to_entity_id
            WHERE cr.relationship_id = ?
            """,
            (relationship_id,),
        ).fetchone()
        if row:
            detail = dict(row)
            detail["history_context"] = None
            return detail

        row = connection.execute(
            """
            SELECT rc.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name,
                   'relationship_claim' AS record_type
            FROM relationship_claim rc
            JOIN entity e1 ON e1.entity_id = rc.from_entity_id
            JOIN entity e2 ON e2.entity_id = rc.to_entity_id
            WHERE rc.claim_id = ?
            """,
            (relationship_id,),
        ).fetchone()
        if not row:
            return None
        detail = dict(row)
        detail["history_context"] = None
        if (
            detail["relation_status"] in REVIEWABLE_DETAIL_CLAIM_STATUSES
            and not _has_final_review_artifacts(connection, relationship_id)
        ):
            detail["history_context"] = get_history_context_for_claim(
                relationship_id, db_path=db_path
            )
        return detail


def get_relationship_evidence(
    relationship_id: str, *, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    """Return order-role and supplemental evidence for a relationship or candidate."""

    detail = get_relationship_detail(relationship_id, db_path=db_path)
    if not detail:
        return []

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM order_role_edge
            WHERE from_entity_id = ? AND to_entity_id = ?
            ORDER BY order_id, role_pair_type
            """,
            (detail["from_entity_id"], detail["to_entity_id"]),
        ).fetchall()
        order_evidence = [
            {**dict(row), "evidence_record_type": "order_role_edge"} for row in rows
        ]
    return order_evidence + list_external_evidence(relationship_id, db_path=db_path)


def list_relationship_claims_for_entity(
    entity_id: str, *, db_path: str | Path | None = None
) -> list[dict[str, Any]]:
    """Return relationship candidates touching an entity."""

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM relationship_claim
            WHERE from_entity_id = ? OR to_entity_id = ?
            ORDER BY confidence_score DESC, order_count DESC
            """,
            (entity_id, entity_id),
        ).fetchall()
        return [dict(row) for row in rows]


def _clean_evidence_value(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _has_external_evidence_content(evidence: dict[str, Any] | None) -> bool:
    if not evidence:
        return False
    return any(_clean_evidence_value(evidence.get(field)) for field in EXTERNAL_EVIDENCE_FIELDS)


def _normalize_external_evidence(
    evidence: dict[str, Any],
    *,
    created_by: str | None = None,
) -> dict[str, str | None]:
    normalized = {
        field: _clean_evidence_value(evidence.get(field)) for field in EXTERNAL_EVIDENCE_FIELDS
    }
    if created_by and not normalized["created_by"]:
        normalized["created_by"] = created_by
    if not normalized["evidence_type"]:
        normalized["evidence_type"] = "manual_note"
    if not normalized["evidence_summary"]:
        raise ValueError("补充证据摘要为必填项")
    if not normalized["created_by"]:
        raise ValueError("补充证据创建人为必填项")
    return normalized


def add_external_evidence_record(
    connection,
    *,
    relationship_id: str | None = None,
    claim_id: str | None = None,
    evidence: dict[str, Any] | None,
    created_by: str | None = None,
) -> dict[str, Any] | None:
    """Insert optional structured supplemental evidence using an existing connection."""

    if not _has_external_evidence_content(evidence):
        return None
    if not relationship_id and not claim_id:
        raise ValueError("补充证据必须绑定最终关系或候选关系")

    normalized = _normalize_external_evidence(evidence or {}, created_by=created_by)
    external_evidence_id = new_id("EEV")
    connection.execute(
        """
        INSERT INTO relationship_external_evidence (
            external_evidence_id, relationship_id, claim_id, evidence_type,
            source_title, source_url, source_name, evidence_summary, evidence_date,
            confidence_level, created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            external_evidence_id,
            relationship_id,
            claim_id,
            normalized["evidence_type"],
            normalized["source_title"],
            normalized["source_url"],
            normalized["source_name"],
            normalized["evidence_summary"],
            normalized["evidence_date"],
            normalized["confidence_level"],
            normalized["created_by"],
        ),
    )
    row = connection.execute(
        """
        SELECT *
        FROM relationship_external_evidence
        WHERE external_evidence_id = ?
        """,
        (external_evidence_id,),
    ).fetchone()
    return dict(row)


def create_external_evidence(
    target_id: str,
    evidence: dict[str, Any],
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Attach structured supplemental evidence to a relationship or claim."""

    detail = get_relationship_detail(target_id, db_path=db_path)
    if not detail:
        raise ValueError(f"未找到关系或候选关系：{target_id}")

    relationship_id = (
        detail["relationship_id"] if detail["record_type"] == "curated_relationship" else None
    )
    claim_id = detail["claim_id"] if detail["record_type"] == "relationship_claim" else None
    with get_connection(db_path) as connection:
        created = add_external_evidence_record(
            connection,
            relationship_id=relationship_id,
            claim_id=claim_id,
            evidence=evidence,
        )
        connection.commit()
    if created is None:
        raise ValueError("补充证据内容不能为空")
    return created


def list_external_evidence(
    target_id: str,
    *,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return structured supplemental evidence for a relationship or claim."""

    detail = get_relationship_detail(target_id, db_path=db_path)
    if not detail:
        return []

    relationship_id = None
    claim_id = None
    if detail["record_type"] == "curated_relationship":
        relationship_id = detail["relationship_id"]
        claim_id = detail.get("decision_source")
    else:
        claim_id = detail["claim_id"]

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM relationship_external_evidence
            WHERE relationship_id = ?
               OR claim_id = ?
            ORDER BY created_at, external_evidence_id
            """,
            (relationship_id, claim_id),
        ).fetchall()
    return [{**dict(row), "evidence_record_type": "external_evidence"} for row in rows]
