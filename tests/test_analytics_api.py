import asyncio
import json
from urllib.parse import urlencode

from tests.test_opportunity_service import seed_m11_opportunity_graph


def _request(app, method: str, path: str, *, query=None):
    async def _call():
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
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


def test_analytics_api_returns_m11_opportunities(tmp_path, monkeypatch):
    db_path = seed_m11_opportunity_graph(tmp_path)
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))

    from trade_entity_graph.api.main import create_app

    status, payload = _request(
        create_app(),
        "GET",
        "/analytics/opportunities",
        query={"limit": 5},
    )

    assert status == 200
    assert payload["summary"]["entity_count"] == 4
    assert payload["relationship_opportunities"][0]["claim_id"] == "CLM_AB"
    assert payload["bridge_entities"][0]["entity_id"] == "ENT_B"


def test_analytics_api_enforces_query_bounds(tmp_path, monkeypatch):
    db_path = seed_m11_opportunity_graph(tmp_path)
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))

    from trade_entity_graph.api.main import create_app

    app = create_app()
    invalid_queries = [
        {"limit": 0},
        {"limit": 101},
        {"min_score": -0.01},
        {"min_score": 1.01},
    ]

    for query in invalid_queries:
        status, payload = _request(
            app,
            "GET",
            "/analytics/opportunities",
            query=query,
        )

        assert status == 422
        assert payload["detail"]


def test_analytics_api_applies_limit_to_each_opportunity_collection(tmp_path, monkeypatch):
    db_path = seed_m11_opportunity_graph(tmp_path)
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))

    from trade_entity_graph.api.main import create_app

    status, payload = _request(
        create_app(),
        "GET",
        "/analytics/opportunities",
        query={"limit": 1},
    )

    assert status == 200
    assert len(payload["relationship_opportunities"]) == 1
    assert len(payload["bridge_entities"]) == 1
    assert len(payload["customer_opportunities"]) == 1
    assert len(payload["clusters"]) == 1
    assert payload["summary"]["relationship_opportunity_count"] == 2
