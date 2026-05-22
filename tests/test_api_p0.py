import asyncio
import json
from urllib.parse import urlencode

import pandas as pd


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
