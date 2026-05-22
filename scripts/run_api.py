"""Run the FastAPI development server."""

from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run("trade_entity_graph.api.main:app", host="127.0.0.1", port=8000, reload=True)
