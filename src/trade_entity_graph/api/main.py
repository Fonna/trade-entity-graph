"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from trade_entity_graph.api.routers import entities, exports, imports, relationships, reviews
from trade_entity_graph.config import get_settings


def create_app() -> FastAPI:
    """Create the FastAPI app."""

    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    app.include_router(imports.router)
    app.include_router(entities.router)
    app.include_router(relationships.router)
    app.include_router(reviews.router)
    app.include_router(exports.router)

    return app


app = create_app()
