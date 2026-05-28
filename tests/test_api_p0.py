import asyncio
import json
from urllib.parse import urlencode

import pandas as pd

from trade_entity_graph.api.routers.imports import ImportRunRequest, run_import_endpoint
from trade_entity_graph.db.connection import get_connection, initialize_database


def _request(app, method: str, path: str, *, query=None, json_body=None):
    async def _call():
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": urlencode(query or {}).encode("utf-8"),
            "headers": [(b"content-type", b"application/json")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        await app(scope, receive, send)
        status = next(
            message["status"]
            for message in messages
            if message["type"] == "http.response.start"
        )
        content = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        return status, json.loads(content.decode("utf-8")) if content else None

    return asyncio.run(_call())


def test_api_p0_import_search_review_graph_export(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "api.db"
    entities_path = tmp_path / "entities.csv"
    orders_path = tmp_path / "orders.csv"
    archive_root = tmp_path / "archives"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("TEG_IMPORT_ARCHIVE_ROOT", str(archive_root))

    pd.DataFrame(
        {
            "标准名": ["ACME TRADING", "BETA FACTORY", "OMEGA BUYER"],
            "原始名": ["Acme Trading Ltd", "Beta Factory Inc", "Omega Buyer LLC"],
            "清洗名": ["ACME TRADING LTD", "BETA FACTORY INC", "OMEGA BUYER LLC"],
        }
    ).to_csv(entities_path, index=False)
    pd.DataFrame(
        {
            "订单号": ["SO-1", "SO-2"],
            "下单客户": ["Acme Trading Ltd", "Acme Trading Ltd"],
            "发货人": ["Beta Factory Inc", "Beta Factory Inc"],
            "收货人": ["Omega Buyer LLC", "Omega Buyer LLC"],
            "通知人": ["Omega Buyer LLC", "SAME AS"],
            "TEU": [3.5, 4.0],
            "产品名称": ["Widget", "Widget"],
            "目的国": ["MX", "MX"],
        }
    ).to_csv(orders_path, index=False)

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, import_payload = _request(
        app,
        "POST",
        "/imports/run",
        json_body={
            "entities_path": str(entities_path),
            "orders_path": str(orders_path),
            "imported_by": "tester",
        },
    )
    assert status == 200
    assert import_payload["edge_count"] == 7
    assert import_payload["claim_count"] == 3
    assert import_payload["history_reuse"] == {
        "history_matched": 0,
        "history_conflict": 0,
        "unchanged": 3,
    }
    assert len(import_payload["archived_files"]) == 2
    assert {item["source_role"] for item in import_payload["archived_files"]} == {
        "entities",
        "orders",
    }

    status, search_payload = _request(app, "GET", "/entities/search", query={"q": "acme"})
    assert status == 200
    acme = search_payload[0]

    status, detail_payload = _request(app, "GET", f"/entities/{acme['entity_id']}")
    assert status == 200
    assert detail_payload["canonical_name"] == "ACME TRADING"

    status, graph_payload = _request(app, "GET", f"/entities/{acme['entity_id']}/ego-graph")
    assert status == 200
    assert graph_payload["summary"]["edge_count"] >= 5

    status, claims_payload = _request(app, "GET", f"/entities/{acme['entity_id']}/neighbors")
    assert status == 200
    claim_id = claims_payload["claims"][0]["claim_id"]

    status, relationship_payload = _request(app, "GET", f"/relationships/{claim_id}")
    assert status == 200
    assert relationship_payload["record_type"] == "relationship_claim"
    assert relationship_payload["from_name"] == "ACME TRADING"
    assert relationship_payload["to_name"]
    assert "history_context" in relationship_payload

    status, decision_payload = _request(
        app,
        "POST",
        f"/relationships/{claim_id}/decision",
        json_body={
            "action_type": "confirm",
            "relation_type": "trading_partner",
            "reason": "Confirmed by API test",
            "operator": "tester",
        },
    )
    assert status == 200
    relationship_id = decision_payload["relationship_id"]

    status, evidence_payload = _request(app, "GET", f"/relationships/{relationship_id}/evidence")
    assert status == 200
    assert evidence_payload

    status, export_payload = _request(
        app,
        "POST",
        "/exports/relationships",
        json_body={"center_entity_id": acme["entity_id"]},
    )
    assert status == 200
    assert export_payload["rows"][0]["relationship_id"] == relationship_id


def test_relationship_api_returns_history_context_and_keeps_history(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-history.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_HISTORY', 'api-history.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (
                'REL_HISTORY', 'ENT_API_FROM', 'ENT_API_TO', 'trading_partner',
                'rejected', 'manual', 'Historical rejection', 'reviewer',
                CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_CONFLICT', 'ENT_API_FROM', 'ENT_API_TO',
                'trading_partner_candidate', 'history_conflict', 'high', 0.88,
                5, 21.5, '5 orders, 21.5 TEU', 'RUN_API_HISTORY'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, relationship_payload = _request(app, "GET", "/relationships/CLM_CONFLICT")
    assert status == 200
    assert relationship_payload["from_name"] == "ACME TRADING"
    assert relationship_payload["to_name"] == "BETA FACTORY"
    assert relationship_payload["history_context"]["history_relationship"][
        "relationship_id"
    ] == "REL_HISTORY"

    status, decision_payload = _request(
        app,
        "POST",
        "/relationships/CLM_CONFLICT/decision",
        json_body={
            "action_type": "keep_history",
            "reason": "Keep reviewed history",
            "operator": "tester",
        },
    )
    assert status == 200
    assert decision_payload["relation_status"] == "history_matched"

    status, finalized_payload = _request(app, "GET", "/relationships/CLM_CONFLICT")
    assert status == 200
    assert finalized_payload["relation_status"] == "history_matched"
    assert finalized_payload["history_context"] is None

    status, duplicate_payload = _request(
        app,
        "POST",
        "/relationships/CLM_CONFLICT/decision",
        json_body={
            "action_type": "keep_history",
            "reason": "Duplicate keep history",
            "operator": "tester",
        },
    )
    assert 400 <= status < 500
    assert duplicate_payload["detail"]


def test_relationship_api_keeps_history_matched_claim(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "api-history-matched.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_HISTORY_MATCHED', 'api-history-matched.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_MATCHED_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_MATCHED_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (
                'REL_API_MATCHED_HISTORY', 'ENT_API_MATCHED_FROM',
                'ENT_API_MATCHED_TO', 'trading_partner', 'verified', 'manual',
                'Historical verified relationship', 'reviewer', CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_API_MATCHED', 'ENT_API_MATCHED_FROM', 'ENT_API_MATCHED_TO',
                'trading_partner_candidate', 'history_matched', 'high', 0.88,
                5, 21.5, 'history reuse: compatible historical relationship',
                'RUN_API_HISTORY_MATCHED'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, relationship_payload = _request(app, "GET", "/relationships/CLM_API_MATCHED")
    assert status == 200
    assert relationship_payload["relation_status"] == "history_matched"
    assert relationship_payload["history_context"]["history_relationship"][
        "relationship_id"
    ] == "REL_API_MATCHED_HISTORY"

    status, decision_payload = _request(
        app,
        "POST",
        "/relationships/CLM_API_MATCHED/decision",
        json_body={
            "action_type": "keep_history",
            "reason": "Keep compatible history",
            "operator": "tester",
        },
    )
    assert status == 200
    assert decision_payload["relation_status"] == "history_matched"
    assert decision_payload["history_relationship_id"] == "REL_API_MATCHED_HISTORY"

    with get_connection(db_path) as connection:
        decisions = connection.execute(
            """
            SELECT action_type, relationship_id
            FROM relationship_decision
            WHERE claim_id = 'CLM_API_MATCHED'
            """
        ).fetchall()
        relationship_count = connection.execute(
            "SELECT COUNT(*) AS count FROM curated_relationship"
        ).fetchone()

    assert [dict(decision) for decision in decisions] == [
        {"action_type": "keep_history", "relationship_id": "REL_API_MATCHED_HISTORY"}
    ]
    assert relationship_count["count"] == 1


def test_relationship_api_confirm_rejects_history_conflict_claim(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-history-confirm.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_HISTORY_CONFIRM', 'api-history-confirm.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_CONFIRM_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_CONFIRM_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (
                'REL_API_CONFIRM_HISTORY', 'ENT_API_CONFIRM_FROM',
                'ENT_API_CONFIRM_TO', 'trading_partner', 'rejected', 'manual',
                'Historical rejection', 'reviewer', CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_API_CONFIRM_CONFLICT', 'ENT_API_CONFIRM_FROM',
                'ENT_API_CONFIRM_TO', 'trading_partner_candidate',
                'history_conflict', 'high', 0.88, 5, 21.5,
                '5 orders, 21.5 TEU', 'RUN_API_HISTORY_CONFIRM'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_API_CONFIRM_CONFLICT/decision",
        json_body={
            "action_type": "confirm",
            "relation_type": "trading_partner",
            "reason": "Ordinary confirm should not bypass supersede",
            "operator": "tester",
        },
    )

    assert 400 <= status < 500
    assert payload["detail"]
    with get_connection(db_path) as connection:
        claim_relationship_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM curated_relationship
            WHERE decision_source = 'CLM_API_CONFIRM_CONFLICT'
            """
        ).fetchone()["count"]
    assert claim_relationship_count == 0


def test_relationship_api_confirm_rejects_candidate_with_unapplied_history(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-candidate-history-confirm.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_CANDIDATE_HISTORY', 'api-candidate-history.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_CANDIDATE_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_API_CANDIDATE_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (
                'REL_API_CANDIDATE_HISTORY', 'ENT_API_CANDIDATE_FROM',
                'ENT_API_CANDIDATE_TO', 'trading_partner', 'rejected', 'manual',
                'Historical rejection', 'reviewer', CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_API_CANDIDATE_WITH_HISTORY', 'ENT_API_CANDIDATE_FROM',
                'ENT_API_CANDIDATE_TO', 'trading_partner_candidate',
                'candidate', 'high', 0.88, 5, 21.5,
                '5 orders, 21.5 TEU', 'RUN_API_CANDIDATE_HISTORY'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_API_CANDIDATE_WITH_HISTORY/decision",
        json_body={
            "action_type": "confirm",
            "relation_type": "trading_partner",
            "reason": "Ordinary confirm should not bypass unapplied history",
            "operator": "tester",
        },
    )

    assert 400 <= status < 500
    assert "请使用历史关系相关的审核动作" in payload["detail"]
    with get_connection(db_path) as connection:
        claim_relationship_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM curated_relationship
            WHERE decision_source = 'CLM_API_CANDIDATE_WITH_HISTORY'
            """
        ).fetchone()["count"]
        old_relationship = connection.execute(
            """
            SELECT relation_status, valid_to
            FROM curated_relationship
            WHERE relationship_id = 'REL_API_CANDIDATE_HISTORY'
            """
        ).fetchone()

    assert claim_relationship_count == 0
    assert dict(old_relationship) == {"relation_status": "rejected", "valid_to": None}


def test_relationship_api_invalid_action_type_returns_json_4xx(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-invalid-action.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_INVALID', 'api-invalid.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_BAD_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_BAD_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_BAD_ACTION', 'ENT_BAD_FROM', 'ENT_BAD_TO',
                'trading_partner_candidate', 'candidate', 'medium', 0.55,
                3, 12.5, '3 orders, 12.5 TEU', 'RUN_API_INVALID'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_BAD_ACTION/decision",
        json_body={
            "action_type": "not_supported",
            "relation_type": "trading_partner",
            "reason": "Invalid action",
            "operator": "tester",
        },
    )
    assert 400 <= status < 500
    assert "不支持的审核动作" in payload["detail"]


def test_relationship_api_supersede_history_requires_relation_type(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-supersede-validation.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_SUPERSEDE', 'api-supersede.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_SUP_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_SUP_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_NEEDS_TYPE', 'ENT_SUP_FROM', 'ENT_SUP_TO',
                'trading_partner_candidate', 'history_conflict', 'high', 0.88,
                5, 21.5, '5 orders, 21.5 TEU', 'RUN_API_SUPERSEDE'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_NEEDS_TYPE/decision",
        json_body={
            "action_type": "supersede_history",
            "reason": "Missing relation type",
            "operator": "tester",
        },
    )
    assert status == 422
    assert payload["detail"] == "关系类型为必填项"


def test_relationship_api_mark_pending_verify_updates_claim(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "api-mark-pending.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_PENDING', 'api-pending.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_PENDING_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_PENDING_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_PENDING_ROUTE', 'ENT_PENDING_FROM', 'ENT_PENDING_TO',
                'trading_partner_candidate', 'candidate', 'medium', 0.55,
                3, 12.5, '3 orders, 12.5 TEU', 'RUN_API_PENDING'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_PENDING_ROUTE/decision",
        json_body={
            "action_type": "mark_pending_verify",
            "reason": "Needs manual verification",
            "operator": "tester",
        },
    )
    assert status == 200
    assert payload["relation_status"] == "pending_verify"

    with get_connection(db_path) as connection:
        stored_status = connection.execute(
            "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
            ("CLM_PENDING_ROUTE",),
        ).fetchone()["relation_status"]
    assert stored_status == "pending_verify"


def test_relationship_api_supersede_history_deprecates_old_relationship(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-supersede-success.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_SUPERSEDE_OK', 'api-supersede-ok.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_SUP_OK_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_SUP_OK_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (
                'REL_SUPERSEDED_ROUTE', 'ENT_SUP_OK_FROM', 'ENT_SUP_OK_TO',
                'trading_partner', 'rejected', 'manual', 'Historical rejection',
                'reviewer', CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_SUPERSEDE_ROUTE', 'ENT_SUP_OK_FROM', 'ENT_SUP_OK_TO',
                'trading_partner_candidate', 'history_conflict', 'high', 0.88,
                5, 21.5, '5 orders, 21.5 TEU', 'RUN_API_SUPERSEDE_OK'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_SUPERSEDE_ROUTE/decision",
        json_body={
            "action_type": "supersede_history",
            "old_relationship_id": "REL_SUPERSEDED_ROUTE",
            "relation_type": "trading_partner",
            "reason": "New evidence supersedes history",
            "operator": "tester",
        },
    )
    assert status == 200
    assert payload["relation_status"] == "verified"
    assert payload["supersedes_relationship_id"] == "REL_SUPERSEDED_ROUTE"

    with get_connection(db_path) as connection:
        old_relationship = connection.execute(
            """
            SELECT relation_status, valid_to
            FROM curated_relationship
            WHERE relationship_id = ?
            """,
            ("REL_SUPERSEDED_ROUTE",),
        ).fetchone()
    assert old_relationship["relation_status"] == "deprecated"
    assert old_relationship["valid_to"] is not None


def test_relationship_api_supersede_history_accepts_history_matched_claim(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-supersede-history-matched.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_SUPERSEDE_MATCHED', 'api-supersede-matched.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_SUP_MATCHED_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_SUP_MATCHED_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (
                'REL_SUPERSEDED_MATCHED_ROUTE',
                'ENT_SUP_MATCHED_FROM',
                'ENT_SUP_MATCHED_TO',
                'trading_partner',
                'verified',
                'manual',
                'Historical relationship',
                'reviewer',
                CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_SUPERSEDE_MATCHED_ROUTE',
                'ENT_SUP_MATCHED_FROM',
                'ENT_SUP_MATCHED_TO',
                'trading_partner_candidate',
                'history_matched',
                'high',
                0.88,
                5,
                21.5,
                'History matched',
                'RUN_API_SUPERSEDE_MATCHED'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_SUPERSEDE_MATCHED_ROUTE/decision",
        json_body={
            "action_type": "supersede_history",
            "old_relationship_id": "REL_SUPERSEDED_MATCHED_ROUTE",
            "relation_type": "trading_partner",
            "reason": "New import corrects the matched history",
            "operator": "tester",
        },
    )
    assert status == 200
    assert payload["relation_status"] == "verified"
    assert payload["supersedes_relationship_id"] == "REL_SUPERSEDED_MATCHED_ROUTE"

    with get_connection(db_path) as connection:
        old_relationship = connection.execute(
            """
            SELECT relation_status, valid_to
            FROM curated_relationship
            WHERE relationship_id = ?
            """,
            ("REL_SUPERSEDED_MATCHED_ROUTE",),
        ).fetchone()
    assert old_relationship["relation_status"] == "deprecated"
    assert old_relationship["valid_to"] is not None


def test_relationship_api_ordinary_decision_requires_relation_type(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "api-confirm-validation.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_CONFIRM_VALIDATION', 'api-confirm.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_CONFIRM_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_CONFIRM_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_CONFIRM_NEEDS_TYPE', 'ENT_CONFIRM_FROM', 'ENT_CONFIRM_TO',
                'trading_partner_candidate', 'candidate', 'medium', 0.55,
                3, 12.5, '3 orders, 12.5 TEU', 'RUN_API_CONFIRM_VALIDATION'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "POST",
        "/relationships/CLM_CONFIRM_NEEDS_TYPE/decision",
        json_body={
            "action_type": "confirm",
            "reason": "Missing relation type",
            "operator": "tester",
        },
    )
    assert status == 422
    assert payload["detail"] == "关系类型为必填项"


def test_reviews_queue_api_lists_pending_claims(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "api-review-queue.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO import_batch (run_id, source_file, imported_by)
            VALUES ('RUN_API_QUEUE', 'api-queue.csv', 'tester')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_QUEUE_FROM', 'ACME TRADING', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO entity (entity_id, canonical_name, entity_type)
            VALUES ('ENT_QUEUE_TO', 'BETA FACTORY', 'company')
            """
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (
                'CLM_API_QUEUE', 'ENT_QUEUE_FROM', 'ENT_QUEUE_TO',
                'trading_partner_candidate', 'history_conflict', 'high', 0.91,
                8, 32.5, '8 orders, 32.5 TEU', 'RUN_API_QUEUE'
            )
            """
        )
        connection.commit()

    from trade_entity_graph.api.main import create_app

    app = create_app()

    status, payload = _request(
        app,
        "GET",
        "/reviews/queue",
        query={
            "status": "history_conflict,candidate",
            "confidence_level": "high",
            "q": "acme",
        },
    )

    assert status == 200
    assert payload["summary"]["total_count"] == 1
    assert payload["items"][0]["claim_id"] == "CLM_API_QUEUE"
    assert payload["items"][0]["from_name"] == "ACME TRADING"


def test_import_endpoint_applies_history_reuse_to_imported_claims_without_aggregation(
    monkeypatch,
) -> None:
    class ImportResult:
        run_id = "RUN_IMPORTED_CLAIMS"
        entity_count = 2
        alias_count = 0
        evidence_count = 0
        claim_count = 1
        skipped_rows = []
        archived_files = []

    calls = []

    def fake_apply_history_reuse_to_claims(*, run_id):
        calls.append(run_id)
        return {"history_matched": 1, "history_conflict": 0, "unchanged": 0}

    monkeypatch.setattr(
        "trade_entity_graph.api.routers.imports.run_import",
        lambda inputs: ImportResult(),
    )
    monkeypatch.setattr(
        "trade_entity_graph.api.routers.imports.apply_history_reuse_to_claims",
        fake_apply_history_reuse_to_claims,
    )

    payload = run_import_endpoint(
        ImportRunRequest(
            relationships_path="relationships.csv",
            generate_edges=False,
            aggregate_claims=False,
        )
    )

    assert payload["claim_count"] == 1
    assert payload["history_reuse"] == {
        "history_matched": 1,
        "history_conflict": 0,
        "unchanged": 0,
    }
    assert calls == ["RUN_IMPORTED_CLAIMS"]


def test_import_endpoint_default_preserves_imported_claims_without_edges(
    monkeypatch,
) -> None:
    class ImportResult:
        run_id = "RUN_IMPORTED_CLAIMS_DEFAULT"
        entity_count = 2
        alias_count = 0
        evidence_count = 0
        claim_count = 1
        skipped_rows = []
        archived_files = []

    calls = []

    def fail_if_aggregated(*, run_id):
        raise AssertionError(f"should not aggregate imported claims without edges: {run_id}")

    def fake_apply_history_reuse_to_claims(*, run_id):
        calls.append(run_id)
        return {"history_matched": 1, "history_conflict": 0, "unchanged": 0}

    monkeypatch.setattr(
        "trade_entity_graph.api.routers.imports.run_import",
        lambda inputs: ImportResult(),
    )
    monkeypatch.setattr(
        "trade_entity_graph.api.routers.imports.generate_order_role_edges",
        lambda *, run_id: {"edge_count": 0},
    )
    monkeypatch.setattr(
        "trade_entity_graph.api.routers.imports.aggregate_relationship_claims",
        fail_if_aggregated,
    )
    monkeypatch.setattr(
        "trade_entity_graph.api.routers.imports.apply_history_reuse_to_claims",
        fake_apply_history_reuse_to_claims,
    )

    payload = run_import_endpoint(
        ImportRunRequest(
            relationships_path="relationships.csv",
        )
    )

    assert payload["claim_count"] == 1
    assert payload["history_reuse"] == {
        "history_matched": 1,
        "history_conflict": 0,
        "unchanged": 0,
    }
    assert calls == ["RUN_IMPORTED_CLAIMS_DEFAULT"]
